"""Composition editing, fixed prompt previews and immutable generation queuing."""

from datetime import UTC, datetime
from uuid import uuid4

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from werkzeug.exceptions import BadRequest, Conflict, NotFound, ServiceUnavailable

from image_studio.api import get_row, images_for, serial, transaction, validate_style
from image_studio.feedback import generation_record, model_tallies, validate_feedback
from image_studio.image_client import prepare_reference
from image_studio.jobs import defer
from image_studio.prompting import assemble, reference_view
from image_studio.requests import formats, snapshot
from image_studio.schema import (
    asset_images,
    assets,
    composition_assets,
    compositions,
    generations,
    image_models,
    output_feedback,
    projects,
    stored_files,
    variants,
)
from image_studio.sequence import EXTENSIONS, slug, stream_sequence

generation_api = Blueprint("generation", __name__, url_prefix="/api")


def body(allowed, required=()):
    value = request.get_json()
    if (
        not isinstance(value, dict)
        or value.keys() - set(allowed)
        or set(required) - value.keys()
    ):
        raise BadRequest("Supply a JSON object with fields: " + ", ".join(allowed))
    return value


def text_fields(value, fields):
    for key in fields:
        if key in value and not isinstance(value[key], str):
            raise BadRequest(f"{key} must be text")
    if "name" in value and not value["name"].strip():
        raise BadRequest("name must not be empty")
    return value


def composition(connection, identifier):
    row = get_row(connection, compositions, identifier)
    if row["deleted_at"] is not None:
        raise NotFound("Composition not found")
    return row


def selected_assets(connection, comp):
    rows = connection.execute(
        select(composition_assets)
        .where(
            composition_assets.c.composition_id == comp["id"],
            composition_assets.c.active.is_(True),
        )
        .order_by(composition_assets.c.position, composition_assets.c.id)
    ).mappings()
    result = []
    style = effective_style(connection, comp)
    if style:
        result.append(
            (
                style,
                {
                    "role": "style reference",
                    "style": True,
                    "deselected_images": comp["style_deselected_images"],
                },
                images_for(connection, style["id"]),
            )
        )
    for selection in rows:
        asset = get_row(connection, assets, selection["asset_id"])
        if asset["type"] == "style":
            raise BadRequest("A Style asset cannot be a pack subject")
        result.append((asset, selection, images_for(connection, asset["id"])))
    return result


def live_variant(connection, identifier):
    row = get_row(connection, variants, identifier)
    if row["deleted_at"] is not None:
        raise NotFound("Frame not found")
    composition(connection, row["composition_id"])
    return row


def lock_composition(connection, identifier):
    connection.execute(
        select(compositions.c.id)
        .where(compositions.c.id == identifier)
        .with_for_update()
    )
    return composition(connection, identifier)


def live_frames(connection, identifier):
    return list(
        connection.execute(
            select(variants)
            .where(
                variants.c.composition_id == identifier,
                variants.c.deleted_at.is_(None),
            )
            .order_by(variants.c.position, variants.c.id)
        ).mappings()
    )


def selected_final(connection, variant):
    if variant["final_generation_id"] is None:
        return None
    row = get_row(connection, generations, variant["final_generation_id"])
    return {
        "generation_id": row["id"],
        "output": variant["final_output"],
        "hash": row["outputs"][variant["final_output"]],
    }


def variant_preview(connection, identifier):
    variant = live_variant(connection, identifier)
    comp = composition(connection, variant["composition_id"])
    project = composition_project(connection, comp)
    return assemble(project, comp, selected_assets(connection, comp), variant)


def detail(connection, identifier):
    comp = composition(connection, identifier)
    result = serial(comp)
    style = effective_style(connection, comp)
    result["style"] = (
        {**serial(style), "images": images_for(connection, style["id"])}
        if style
        else None
    )
    # Keep stale selections visible so the user can remove them after asset changes.
    result["assets"] = []
    for selection in connection.execute(
        select(composition_assets)
        .where(
            composition_assets.c.composition_id == identifier,
            composition_assets.c.active.is_(True),
        )
        .order_by(composition_assets.c.position, composition_assets.c.id)
    ).mappings():
        asset = serial(get_row(connection, assets, selection["asset_id"], deleted=True))
        asset["images"] = images_for(connection, asset["id"])
        result["assets"].append({**serial(selection), "asset": asset})
    result["variants"] = [
        {**serial(r), "final": selected_final(connection, r)}
        for r in live_frames(connection, identifier)
    ]
    return result


def model_list(connection):
    try:
        models = current_app.extensions["image_client"].models()
    except ServiceUnavailable:
        models = [
            {"model_name": r["name"], "model_info": r["info"]}
            for r in connection.execute(
                select(image_models)
                .where(image_models.c.listed.is_(True))
                .order_by(image_models.c.name)
            ).mappings()
        ]
        if not models:
            raise
        return models
    connection.execute(update(image_models).values(listed=False))
    for model in models:
        connection.execute(
            pg_insert(image_models)
            .values(name=model["model_name"], info=model["model_info"], listed=True)
            .on_conflict_do_update(
                index_elements=["name"],
                set_={
                    "info": model["model_info"],
                    "read_at": func.now(),
                    "listed": True,
                },
            )
        )
    return models


@generation_api.get("/models")
@transaction
def models(connection):
    return jsonify(model_list(connection))


def composition_project(connection, comp):
    return (
        get_row(connection, projects, comp["project_id"])
        if comp["project_id"] is not None
        else None
    )


def effective_style(connection, comp):
    project = composition_project(connection, comp)
    identifier = comp["style_asset_id"] or (
        project["style_asset_id"] if project else None
    )
    if identifier is None:
        return None
    asset = get_row(connection, assets, identifier, deleted=True)
    return asset if asset["deleted_at"] is None and asset["type"] == "style" else None


def image_ids(value, available, field):
    if (
        not isinstance(value, list)
        or any(type(i) is not int or i not in available for i in value)
        or len(value) != len(set(value))
    ):
        raise BadRequest(f"{field} must contain unique available image IDs")


def composition_fields(connection, value):
    validate_style(connection, value)
    text_fields(value, ["name", "brief"])
    if "kind" in value and value["kind"] not in ("single", "storyboard"):
        raise BadRequest("kind must be single or storyboard")
    if "project_id" in value and value["project_id"] is not None:
        identifier = value["project_id"]
        if type(identifier) is not int or not 1 <= identifier <= 2147483647:
            raise BadRequest("project_id must be a positive integer or null")
        get_row(connection, projects, identifier)
    return value


def summaries(connection, project_id=None, *, filtered=False):
    query = select(compositions).where(compositions.c.deleted_at.is_(None))
    if filtered:
        query = query.where(compositions.c.project_id == project_id)
    result = []
    for row in connection.execute(query).mappings():
        frames = live_frames(connection, row["id"])
        finals = [selected_final(connection, frame) for frame in frames]
        runs = list(
            connection.execute(
                select(generations)
                .where(generations.c.variant_id.in_([f["id"] for f in frames]))
                .order_by(generations.c.id.desc())
            ).mappings()
        )
        thumbnail = next((f["hash"] for f in finals if f), None)
        if thumbnail is None:
            thumbnail = next((g["outputs"][-1] for g in runs if g["outputs"]), None)
        activity = max(
            [row["created_at"]]
            + [g["finished_at"] or g["started_at"] or g["created_at"] for g in runs]
        )
        project = composition_project(connection, row)
        result.append(
            {
                **serial(row),
                "project": serial(project) if project else None,
                "thumbnail": thumbnail,
                "last_activity": activity.isoformat(),
            }
        )
    return sorted(result, key=lambda r: (r["last_activity"], r["id"]), reverse=True)


def new_composition(connection, value):
    if "style_deselected_images" in value:
        style = effective_style(
            connection, {"style_asset_id": None, "project_id": None, **value}
        )
        image_ids(
            value["style_deselected_images"],
            {i["id"] for i in images_for(connection, style["id"])} if style else set(),
            "style_deselected_images",
        )
    identifier = connection.execute(
        insert(compositions).values(**value).returning(compositions.c.id)
    ).scalar_one()
    connection.execute(insert(variants).values(composition_id=identifier))
    return jsonify(detail(connection, identifier)), 201


@generation_api.route("/compositions", methods=["GET", "POST"])
@transaction
def all_compositions(connection):
    if request.method == "POST":
        value = composition_fields(
            connection,
            body(
                [
                    "name",
                    "brief",
                    "kind",
                    "project_id",
                    "style_asset_id",
                    "style_deselected_images",
                ],
                ["name", "kind"],
            ),
        )
        return new_composition(connection, value)
    if "project_id" not in request.args:
        return jsonify(summaries(connection))
    supplied = request.args["project_id"]
    if supplied == "none":
        identifier = None
    elif (
        supplied.isascii() and supplied.isdecimal() and 1 <= int(supplied) <= 2147483647
    ):
        identifier = int(supplied)
        get_row(connection, projects, identifier)
    else:
        raise BadRequest("project_id must be a positive integer or none")
    return jsonify(summaries(connection, identifier, filtered=True))


@generation_api.route(
    "/projects/<int:project_id>/compositions", methods=["GET", "POST"]
)
@transaction
def project_compositions(connection, project_id):
    get_row(connection, projects, project_id)
    if request.method == "GET":
        return jsonify(summaries(connection, project_id, filtered=True))
    value = composition_fields(
        connection,
        body(["name", "brief", "kind", "style_asset_id"], ["name"]),
    )
    return new_composition(connection, {**value, "project_id": project_id})


@generation_api.post("/compositions/<int:identifier>/duplicate")
@transaction
def duplicate_composition(connection, identifier):
    original = lock_composition(connection, identifier)
    values = {
        k: original[k]
        for k in (
            "name",
            "project_id",
            "kind",
            "brief",
            "style_asset_id",
            "style_deselected_images",
        )
    }
    values["name"] += " (copy)"
    copied = connection.execute(
        insert(compositions).values(**values).returning(compositions.c.id)
    ).scalar_one()
    for selection in connection.execute(
        select(composition_assets)
        .where(composition_assets.c.composition_id == identifier)
        .order_by(composition_assets.c.position, composition_assets.c.id)
    ).mappings():
        connection.execute(
            insert(composition_assets).values(
                composition_id=copied,
                **{
                    k: selection[k]
                    for k in (
                        "asset_id",
                        "role",
                        "position",
                        "deselected_images",
                        "selected_originals",
                        "active",
                    )
                },
            )
        )
    for frame in live_frames(connection, identifier):
        connection.execute(
            insert(variants).values(
                composition_id=copied,
                **{
                    k: frame[k]
                    for k in (
                        "name",
                        "instructions",
                        "position",
                        "deselected_images",
                        "selected_originals",
                    )
                },
            )
        )
    return jsonify(detail(connection, copied)), 201


@generation_api.route(
    "/compositions/<int:identifier>", methods=["GET", "PATCH", "DELETE"]
)
@transaction
def edit_composition(connection, identifier):
    lock_composition(connection, identifier)
    if request.method == "DELETE":
        connection.execute(
            update(compositions)
            .where(compositions.c.id == identifier)
            .values(deleted_at=datetime.now().astimezone())
        )
        return jsonify(deleted=True)
    if request.method == "PATCH":
        value = composition_fields(
            connection,
            body(
                [
                    "name",
                    "brief",
                    "kind",
                    "project_id",
                    "style_asset_id",
                    "style_deselected_images",
                ]
            ),
        )
        if "style_deselected_images" in value:
            candidate = {**composition(connection, identifier), **value}
            style = effective_style(connection, candidate)
            image_ids(
                value["style_deselected_images"],
                {i["id"] for i in images_for(connection, style["id"])}
                if style
                else set(),
                "style_deselected_images",
            )
        if (
            value.get("kind") == "single"
            and len(live_frames(connection, identifier)) != 1
        ):
            raise Conflict("A single composition must have exactly one live frame")
        if value:
            connection.execute(
                update(compositions)
                .where(compositions.c.id == identifier)
                .values(**value)
            )
    return jsonify(detail(connection, identifier))


@generation_api.put("/compositions/<int:identifier>/assets/<int:asset_id>")
@transaction
def select_asset(connection, identifier, asset_id):
    composition(connection, identifier)
    asset = get_row(connection, assets, asset_id)
    if asset["type"] == "style":
        raise BadRequest("A Style asset cannot be a pack subject")
    value = text_fields(
        body(["role", "deselected_images", "selected_originals"], ["role"]), ["role"]
    )
    images = images_for(connection, asset_id)
    image_ids(
        value.get("selected_originals", []),
        {i["id"] for i in images if i["source"] == "uploaded" and not i["rejected"]},
        "selected_originals",
    )
    value.setdefault("selected_originals", [])
    if not value["role"].strip():
        raise BadRequest("role must not be empty")
    deselected = value.get("deselected_images", [])
    available_ids = {i["id"] for i in images_for(connection, asset_id)}
    if not isinstance(deselected, list) or any(
        type(i) is not int or i not in available_ids for i in deselected
    ):
        raise BadRequest(
            "deselected_images must contain image IDs belonging to the asset"
        )
    value["deselected_images"] = deselected
    # Positions only establish request order; this slice exposes no reordering.
    position = connection.execute(
        select(composition_assets.c.id).where(
            composition_assets.c.composition_id == identifier
        )
    ).all()
    connection.execute(
        pg_insert(composition_assets)
        .values(
            composition_id=identifier,
            asset_id=asset_id,
            position=len(position),
            **value,
        )
        .on_conflict_do_update(
            constraint="one_asset_per_composition", set_={**value, "active": True}
        )
    )
    return jsonify(detail(connection, identifier))


@generation_api.delete("/compositions/<int:identifier>/assets/<int:asset_id>")
@transaction
def remove_asset(connection, identifier, asset_id):
    composition(connection, identifier)
    connection.execute(
        update(composition_assets)
        .where(
            composition_assets.c.composition_id == identifier,
            composition_assets.c.asset_id == asset_id,
        )
        .values(active=False)
    )
    return jsonify(detail(connection, identifier))


@generation_api.post("/compositions/<int:identifier>/variants")
@transaction
def add_frame(connection, identifier):
    comp = lock_composition(connection, identifier)
    if comp["kind"] != "storyboard":
        raise Conflict(
            "Turn this single composition into a storyboard before adding frames"
        )
    value = text_fields(body(["name", "instructions"]), ["name", "instructions"])
    rows = list(
        connection.execute(
            select(variants).where(variants.c.composition_id == identifier)
        ).mappings()
    )
    value.setdefault("name", f"Frame {len(rows) + 1}")
    row_id = connection.execute(
        insert(variants)
        .values(
            composition_id=identifier,
            position=max((r["position"] for r in rows), default=-1) + 1,
            **value,
        )
        .returning(variants.c.id)
    ).scalar_one()
    return jsonify(serial(get_row(connection, variants, row_id))), 201


@generation_api.put("/compositions/<int:identifier>/frame-order")
@transaction
def reorder_frames(connection, identifier):
    lock_composition(connection, identifier)
    ids = body(["ids"], ["ids"])["ids"]
    expected = {r["id"] for r in live_frames(connection, identifier)}
    if (
        not isinstance(ids, list)
        or any(type(i) is not int for i in ids)
        or len(ids) != len(expected)
        or set(ids) != expected
    ):
        raise BadRequest("ids must contain every live frame exactly once")
    for position, row_id in enumerate(ids):
        connection.execute(
            update(variants).where(variants.c.id == row_id).values(position=position)
        )
    return jsonify(detail(connection, identifier))


@generation_api.route("/variants/<int:identifier>", methods=["GET", "PATCH", "DELETE"])
@transaction
def edit_variant(connection, identifier):
    original = get_row(connection, variants, identifier)
    if request.method == "GET":
        return jsonify(serial(original))
    lock_composition(connection, original["composition_id"])
    variant = live_variant(connection, identifier)
    if request.method == "DELETE":
        if len(live_frames(connection, variant["composition_id"])) <= 1:
            raise Conflict("A composition must keep at least one live frame")
        connection.execute(
            update(variants)
            .where(variants.c.id == identifier)
            .values(deleted_at=datetime.now().astimezone())
        )
        return jsonify(deleted=True)
    value = text_fields(
        body(["name", "instructions", "deselected_images", "selected_originals"]),
        ["name", "instructions"],
    )
    if {"deselected_images", "selected_originals"} & value.keys():
        selections = selected_assets(
            connection, composition(connection, variant["composition_id"])
        )
        available = {
            image["id"]
            for _, selection, images in selections
            for image in images
            if not image["rejected"]
            and image["id"] not in selection["deselected_images"]
            and (image["approved"] or image["source"] == "uploaded")
        }
        if "deselected_images" in value:
            image_ids(value["deselected_images"], available, "deselected_images")
        if "selected_originals" in value:
            originals = {
                i["id"]
                for _, selection, images in selections
                if not selection.get("style")
                for i in images
                if i["source"] == "uploaded" and not i["rejected"]
            }
            image_ids(value["selected_originals"], originals, "selected_originals")
    if value:
        connection.execute(
            update(variants).where(variants.c.id == identifier).values(**value)
        )
    return jsonify(serial(get_row(connection, variants, identifier)))


def sequence_detail(connection, identifier):
    comp = composition(connection, identifier)
    entries, skipped = [], []
    for frame in live_frames(connection, identifier):
        final = selected_final(connection, frame)
        if final is None:
            skipped.append({"id": frame["id"], "name": frame["name"]})
            continue
        file = (
            connection.execute(
                select(stored_files).where(stored_files.c.hash == final["hash"])
            )
            .mappings()
            .one()
        )
        entries.append(
            {
                "frame_id": frame["id"],
                "name": frame["name"],
                "hash": final["hash"],
                "filename": (
                    f"{len(entries) + 1:02d}-{slug(frame['name'])}."
                    f"{EXTENSIONS[file['media_type']]}"
                ),
            }
        )
    return {
        "filename": slug(comp["name"]) + ".zip",
        "entries": entries,
        "skipped": skipped,
    }


@generation_api.get("/compositions/<int:identifier>/sequence")
@transaction
def sequence_manifest(connection, identifier):
    return jsonify(sequence_detail(connection, identifier))


@generation_api.get("/compositions/<int:identifier>/sequence.zip")
@transaction
def export_sequence(connection, identifier):
    manifest = sequence_detail(connection, identifier)
    return Response(
        stream_sequence(current_app.config["STUDIO_FILES"], manifest["entries"]),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={manifest['filename']}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@generation_api.route("/variants/<int:identifier>/preview", methods=["GET", "POST"])
@transaction
def preview(connection, identifier):
    if request.method == "GET":
        return jsonify(variant_preview(connection, identifier))
    value = text_fields(
        body(["brief", "instructions"], ["brief", "instructions"]),
        ["brief", "instructions"],
    )
    variant = dict(live_variant(connection, identifier))
    comp = dict(composition(connection, variant["composition_id"]))
    comp["brief"] = value["brief"]
    variant["instructions"] = value["instructions"]
    return jsonify(
        assemble(
            composition_project(connection, comp),
            comp,
            selected_assets(connection, comp),
            variant,
        )
    )


def reference_snapshot(refs, info):
    root = current_app.config["STUDIO_FILES"]
    return [{**ref, "sent_size": prepare_reference(root, ref, info)[2]} for ref in refs]


def snapshot_references(values, info):
    values["references"] = reference_snapshot(values["references"], info)
    sizes = {r["hash"]: r["sent_size"] for r in values["references"]}
    values["shared_references"] = [
        {**r, "sent_size": sizes[r["hash"]]} for r in values["shared_references"]
    ]


def queue(connection, preview, kind, **owner):
    value = body(["model", "count", "prompt", "settings"], ["model", "count"])
    if not isinstance(value["model"], str):
        raise BadRequest("model must be text")
    if type(value["count"]) is not int or not 1 <= value["count"] <= 4:
        raise BadRequest("count must be between 1 and 4")
    model = next(
        (m for m in model_list(connection) if m["model_name"] == value["model"]), None
    )
    if model is None:
        raise BadRequest("Choose an available image model")
    info = model["model_info"]
    values = snapshot(
        value["model"],
        preview["prompt"],
        preview["references"],
        info,
        value["count"],
        value.get("settings"),
        value.get("prompt"),
    )
    snapshot_references(values, info)
    identifier = connection.execute(
        insert(generations)
        .values(
            kind=kind,
            **owner,
            model=value["model"],
            model_info=info,
            **values,
            placeholder=info["placeholder"],
            count=value["count"],
        )
        .returning(generations.c.id)
    ).scalar_one()
    defer(connection, identifier)
    return jsonify(
        generation_record(connection, get_row(connection, generations, identifier))
    ), 201


@generation_api.route("/variants/<int:identifier>/generations", methods=["GET", "POST"])
@transaction
def variant_generations(connection, identifier):
    if request.method == "POST":
        return queue(
            connection,
            variant_preview(connection, identifier),
            "composition",
            variant_id=identifier,
        )
    get_row(connection, variants, identifier)
    return history(connection, generations.c.variant_id == identifier)


@generation_api.route("/assets/<int:identifier>/generations", methods=["GET", "POST"])
@transaction
def asset_generations(connection, identifier):
    asset = get_row(connection, assets, identifier)
    if request.method == "POST":
        return queue(
            connection,
            reference_view(asset, images_for(connection, identifier)),
            "asset_reference",
            asset_id=identifier,
        )
    return history(connection, generations.c.asset_id == identifier)


@generation_api.get("/assets/<int:identifier>/reference-preview")
@transaction
def asset_preview(connection, identifier):
    return jsonify(
        reference_view(
            get_row(connection, assets, identifier), images_for(connection, identifier)
        )
    )


def history(connection, condition):
    return jsonify(
        [
            generation_record(connection, r)
            for r in connection.execute(
                select(generations).where(condition).order_by(generations.c.id.desc())
            ).mappings()
        ]
    )


@generation_api.get("/generations/<int:identifier>")
@transaction
def generation(connection, identifier):
    return jsonify(
        generation_record(connection, get_row(connection, generations, identifier))
    )


def run_choices(value):
    choices = value.get("models")
    if not isinstance(choices, list) or not 1 <= len(choices) <= 3:
        raise BadRequest("Choose one to three models")
    names = set()
    for choice in choices:
        if (
            not isinstance(choice, dict)
            or set(choice) - {"model", "count", "prompt", "settings"}
            or not {"model", "count"} <= set(choice)
            or not isinstance(choice["model"], str)
            or type(choice["count"]) is not int
            or not 1 <= choice["count"] <= 4
        ):
            raise BadRequest("Each model needs a name and a count between 1 and 4")
        if choice["model"] in names:
            raise BadRequest("Choose each model only once")
        names.add(choice["model"])
    return choices


def draft_references(connection, supplied):
    if not isinstance(supplied, list):
        raise BadRequest("references must be an ordered list")
    result = []
    for ref in supplied:
        if (
            not isinstance(ref, dict)
            or not isinstance(ref.get("hash"), str)
            or type(ref.get("asset_id")) is not int
            or not 1 <= ref["asset_id"] <= 2147483647
            or not isinstance(ref.get("role"), str)
        ):
            raise BadRequest("Each reference needs a stored hash, asset_id and role")
        row = (
            connection.execute(
                select(assets, stored_files)
                .join(asset_images, asset_images.c.asset_id == assets.c.id)
                .join(stored_files, stored_files.c.hash == asset_images.c.file_hash)
                .where(
                    assets.c.id == ref["asset_id"],
                    stored_files.c.hash == ref["hash"],
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise BadRequest("Reference hash must belong to an attached asset image")
        # Never use client-supplied file metadata or asset descriptions.
        result.append(
            {
                "hash": row["hash"],
                "media_type": row["media_type"],
                "asset_id": row["id"],
                "asset_name": row["name"],
                "description": row["description"],
                "type_tag": row["type_tag"],
                "type": row["type"],
                "preserve": row["preserve"],
                "role": ref["role"],
            }
        )
    return result


def run_detail(connection, variant_id, run_id):
    rows = [
        generation_record(connection, r)
        for r in connection.execute(
            select(generations)
            .where(
                generations.c.variant_id == variant_id, generations.c.run_id == run_id
            )
            .order_by(generations.c.id)
        ).mappings()
    ]
    if not rows:
        raise NotFound("Run not found")
    first = rows[0]
    return {
        "run_id": run_id,
        "created_at": first["created_at"],
        "prompt": first["prompt"],
        "edited": first["edited"],
        "references": first["shared_references"]
        if first["shared_references"] is not None
        else first["references"],
        "generations": rows,
    }


@generation_api.route("/variants/<int:identifier>/runs", methods=["GET", "POST"])
@transaction
def variant_runs(connection, identifier):
    variant = get_row(connection, variants, identifier)
    composition(connection, variant["composition_id"])
    if request.method == "GET":
        run_ids = connection.execute(
            select(generations.c.run_id, func.min(generations.c.id).label("first_id"))
            .where(generations.c.variant_id == identifier)
            .group_by(generations.c.run_id)
            .order_by(func.min(generations.c.id).desc())
        ).all()
        return jsonify([run_detail(connection, identifier, r.run_id) for r in run_ids])
    live_variant(connection, identifier)
    value = body(["models", "prompt", "references", "content", "format"], ["models"])
    choices = run_choices(value)
    if "references" in value:
        refs = draft_references(connection, value["references"])
        content = value.get("content", value.get("prompt"))
    else:
        preview = variant_preview(connection, identifier)
        refs, content = preview["references"], preview["prompt"]
    if not isinstance(content, str) or not content.strip():
        raise BadRequest("content must be nonempty text")
    available = {m["model_name"]: m["model_info"] for m in model_list(connection)}
    prepared = []
    ratio = value.get("format")
    for choice in choices:
        info = available.get(choice["model"])
        if info is None:
            raise BadRequest("Choose an available image model")
        if ratio is None:
            supported = [
                set(formats(available[c["model"]]))
                for c in choices
                if c["model"] in available
            ]
            common = set.intersection(*supported)
            if all(supported) and not common:
                raise BadRequest("Chosen models have no common format")
            ratio = "1:1" if "1:1" in common else next(iter(sorted(common)), None)
        values = snapshot(
            choice["model"],
            content,
            refs,
            info,
            choice["count"],
            choice.get("settings"),
            choice.get("prompt", value.get("prompt")),
            ratio,
        )
        snapshot_references(values, info)
        prepared.append((choice, info, values))
    run_id = str(uuid4())
    for choice, info, values in prepared:
        row_id = connection.execute(
            insert(generations)
            .values(
                run_id=run_id,
                kind="composition",
                variant_id=identifier,
                model=choice["model"],
                model_info=info,
                count=choice["count"],
                placeholder=info["placeholder"],
                **values,
            )
            .returning(generations.c.id)
        ).scalar_one()
        defer(connection, row_id)
    return jsonify(run_detail(connection, identifier, run_id)), 201


@generation_api.post("/generations/<int:identifier>/retry")
@transaction
def retry_generation(connection, identifier):
    original = get_row(connection, generations, identifier)
    if original["state"] != "failed":
        raise Conflict("Only failed generations can be retried")
    if original["variant_id"] is not None:
        variant = live_variant(connection, original["variant_id"])
        composition(connection, variant["composition_id"])
    if original["model"] not in {m["model_name"] for m in model_list(connection)}:
        raise BadRequest(
            "This image model is no longer listed; choose an available model"
        )
    keys = (
        "kind",
        "variant_id",
        "asset_id",
        "run_id",
        "model",
        "model_info",
        "prompt",
        "assembled_prompt",
        "edited",
        "references",
        "placeholder",
        "count",
        "prompt_family",
        "shared_references",
        "rendered_prompt",
        "settings",
        "request_fields",
        "estimated_cost",
    )
    row_id = connection.execute(
        insert(generations)
        .values(**{k: original[k] for k in keys}, retry_of=identifier)
        .returning(generations.c.id)
    ).scalar_one()
    defer(connection, row_id)
    return jsonify(
        generation_record(connection, get_row(connection, generations, row_id))
    ), 201


@generation_api.route(
    "/variants/<int:identifier>/final", methods=["GET", "PUT", "DELETE"]
)
@transaction
def final_image(connection, identifier):
    variant = get_row(connection, variants, identifier)
    composition(connection, variant["composition_id"])
    if request.method != "GET":
        live_variant(connection, identifier)
    if request.method == "DELETE":
        connection.execute(
            update(variants)
            .where(variants.c.id == identifier)
            .values(final_generation_id=None, final_output=None)
        )
    elif request.method == "PUT":
        value = body(["generation_id", "output"], ["generation_id", "output"])
        if type(value["generation_id"]) is not int or type(value["output"]) is not int:
            raise BadRequest("generation_id and output must be integers")
        row = get_row(connection, generations, value["generation_id"])
        if (
            row["variant_id"] != identifier
            or row["state"] != "done"
            or not 0 <= value["output"] < len(row["outputs"])
        ):
            raise BadRequest(
                "Choose an output of a done generation belonging to this variant"
            )
        connection.execute(
            update(variants)
            .where(variants.c.id == identifier)
            .values(final_generation_id=row["id"], final_output=value["output"])
        )
    variant = get_row(connection, variants, identifier)
    if variant["final_generation_id"] is None:
        return jsonify(None)
    row = get_row(connection, generations, variant["final_generation_id"])
    return jsonify(
        generation_id=row["id"],
        output=variant["final_output"],
        hash=row["outputs"][variant["final_output"]],
    )


@generation_api.get("/spend")
@transaction
def spend(connection):
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    total = connection.scalar(
        select(func.coalesce(func.sum(generations.c.estimated_cost), 0)).where(
            generations.c.created_at >= start, generations.c.created_at < end
        )
    )
    return jsonify(estimated_spend=float(total), month=start.isoformat())


@generation_api.post("/render")
@transaction
def render_preview(connection):
    value = body(
        ["content", "references", "models", "format"],
        ["content", "references", "models"],
    )
    if not isinstance(value["content"], str):
        raise BadRequest("content must be text")
    refs = draft_references(connection, value["references"])
    available = {m["model_name"]: m["model_info"] for m in model_list(connection)}
    result = []
    for choice in run_choices(value):
        info = available.get(choice["model"])
        if info is None:
            raise BadRequest("Choose an available image model")
        result.append(
            {
                "model": choice["model"],
                **snapshot(
                    choice["model"],
                    value["content"],
                    refs,
                    info,
                    choice["count"],
                    choice.get("settings"),
                    choice.get("prompt"),
                    value.get("format"),
                ),
            }
        )
    return jsonify(result)


@generation_api.patch("/generations/<int:identifier>/outputs/<int:output>/feedback")
@transaction
def edit_output_feedback(connection, identifier, output):
    row = get_row(connection, generations, identifier)
    if output >= len(row["outputs"]):
        raise NotFound("Output not found")
    value = validate_feedback(
        body(["verdict", "asset_ratings", "note"]), row["references"]
    )
    if not value:
        raise BadRequest("Supply at least one feedback field")
    connection.execute(
        pg_insert(output_feedback)
        .values(generation_id=identifier, output_index=output, **value)
        .on_conflict_do_update(
            index_elements=["generation_id", "output_index"],
            set_={**value, "updated_at": func.now()},
        )
    )
    return jsonify(generation_record(connection, row)["feedback"][output])


@generation_api.get("/variants/<int:identifier>/feedback-tally")
@transaction
def feedback_tally(connection, identifier):
    get_row(connection, variants, identifier)
    rows = [
        generation_record(connection, row)
        for row in connection.execute(
            select(generations).where(generations.c.variant_id == identifier)
        ).mappings()
    ]
    return jsonify(model_tallies(rows))

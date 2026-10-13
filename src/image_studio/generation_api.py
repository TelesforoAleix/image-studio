"""Composition editing, fixed prompt previews and immutable generation queuing."""

from datetime import datetime
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from werkzeug.exceptions import BadRequest, Conflict, NotFound, ServiceUnavailable

from image_studio.api import get_row, images_for, serial, transaction
from image_studio.jobs import defer
from image_studio.prompting import assemble, reference_view
from image_studio.schema import (
    asset_images,
    assets,
    composition_assets,
    compositions,
    generations,
    image_models,
    projects,
    stored_files,
    variants,
)

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
    for selection in rows:
        asset = get_row(connection, assets, selection["asset_id"])
        if asset["project_id"] not in (None, comp["project_id"]):
            raise Conflict(
                f"Asset {asset['name']} is no longer visible to this project; remove it"
            )
        result.append((asset, selection, images_for(connection, asset["id"])))
    return result


def variant_preview(connection, identifier):
    variant = get_row(connection, variants, identifier)
    comp = composition(connection, variant["composition_id"])
    project = get_row(connection, projects, comp["project_id"])
    return assemble(project, comp, selected_assets(connection, comp), variant)


def detail(connection, identifier):
    comp = composition(connection, identifier)
    result = serial(comp)
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
        serial(r)
        for r in connection.execute(
            select(variants)
            .where(variants.c.composition_id == identifier)
            .order_by(variants.c.position, variants.c.id)
        ).mappings()
    ]
    return result


def model_list(connection):
    try:
        models = current_app.extensions["image_client"].models()
    except ServiceUnavailable:
        models = [
            {"model_name": r["name"], "model_info": r["info"]}
            for r in connection.execute(
                select(image_models).order_by(image_models.c.name)
            ).mappings()
        ]
        if not models:
            raise
        return models
    for model in models:
        connection.execute(
            pg_insert(image_models)
            .values(name=model["model_name"], info=model["model_info"])
            .on_conflict_do_update(
                index_elements=["name"],
                set_={"info": model["model_info"], "read_at": func.now()},
            )
        )
    return models


@generation_api.get("/models")
@transaction
def models(connection):
    return jsonify(model_list(connection))


@generation_api.route(
    "/projects/<int:project_id>/compositions", methods=["GET", "POST"]
)
@transaction
def project_compositions(connection, project_id):
    get_row(connection, projects, project_id)
    if request.method == "GET":
        return jsonify(
            [
                serial(r)
                for r in connection.execute(
                    select(compositions)
                    .where(
                        compositions.c.project_id == project_id,
                        compositions.c.deleted_at.is_(None),
                    )
                    .order_by(compositions.c.id)
                ).mappings()
            ]
        )
    value = text_fields(body(["name", "scene"], ["name"]), ["name", "scene"])
    identifier = connection.execute(
        insert(compositions)
        .values(project_id=project_id, **value)
        .returning(compositions.c.id)
    ).scalar_one()
    connection.execute(insert(variants).values(composition_id=identifier))
    return jsonify(detail(connection, identifier)), 201


@generation_api.route(
    "/compositions/<int:identifier>", methods=["GET", "PATCH", "DELETE"]
)
@transaction
def edit_composition(connection, identifier):
    composition(connection, identifier)
    if request.method == "DELETE":
        connection.execute(
            update(compositions)
            .where(compositions.c.id == identifier)
            .values(deleted_at=datetime.now().astimezone())
        )
        return jsonify(deleted=True)
    if request.method == "PATCH":
        value = text_fields(body(["name", "scene"]), ["name", "scene"])
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
    comp = composition(connection, identifier)
    asset = get_row(connection, assets, asset_id)
    if asset["project_id"] not in (None, comp["project_id"]):
        raise BadRequest("Asset is not visible to this project")
    value = text_fields(body(["role", "deselected_images"], ["role"]), ["role"])
    if not value["role"].strip():
        raise BadRequest("role must not be empty")
    deselected = value.get("deselected_images", [])
    image_ids = {i["id"] for i in images_for(connection, asset_id)}
    if not isinstance(deselected, list) or any(
        type(i) is not int or i not in image_ids for i in deselected
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


@generation_api.patch("/variants/<int:identifier>")
@transaction
def edit_variant(connection, identifier):
    variant = get_row(connection, variants, identifier)
    composition(connection, variant["composition_id"])
    value = text_fields(body(["instructions"], ["instructions"]), ["instructions"])
    connection.execute(
        update(variants).where(variants.c.id == identifier).values(**value)
    )
    return jsonify(serial(get_row(connection, variants, identifier)))


@generation_api.route("/variants/<int:identifier>/preview", methods=["GET", "POST"])
@transaction
def preview(connection, identifier):
    if request.method == "GET":
        return jsonify(variant_preview(connection, identifier))
    value = text_fields(
        body(["scene", "instructions"], ["scene", "instructions"]),
        ["scene", "instructions"],
    )
    variant = dict(get_row(connection, variants, identifier))
    comp = dict(composition(connection, variant["composition_id"]))
    comp["scene"] = value["scene"]
    variant["instructions"] = value["instructions"]
    return jsonify(
        assemble(
            get_row(connection, projects, comp["project_id"]),
            comp,
            selected_assets(connection, comp),
            variant,
        )
    )


def queue(connection, preview, kind, **owner):
    value = body(["model", "count", "prompt"], ["model", "count"])
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
    count = len(preview["references"])
    if count > info["max_references"]:
        raise BadRequest(
            f"Selected {count} references; {model['model_name']} accepts at most "
            f"{info['max_references']}. Adjust your selection."
        )
    prompt = value.get("prompt", preview["prompt"])
    if not isinstance(prompt, str) or not prompt.strip():
        raise BadRequest("prompt must be nonempty text")
    identifier = connection.execute(
        insert(generations)
        .values(
            kind=kind,
            **owner,
            model=value["model"],
            model_info=info,
            prompt=prompt,
            assembled_prompt=preview["prompt"],
            edited=prompt != preview["prompt"],
            references=preview["references"],
            placeholder=info["placeholder"],
            count=value["count"],
        )
        .returning(generations.c.id)
    ).scalar_one()
    defer(connection, identifier)
    return jsonify(serial(get_row(connection, generations, identifier))), 201


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
            serial(r)
            for r in connection.execute(
                select(generations).where(condition).order_by(generations.c.id.desc())
            ).mappings()
        ]
    )


@generation_api.get("/generations/<int:identifier>")
@transaction
def generation(connection, identifier):
    return jsonify(serial(get_row(connection, generations, identifier)))


def run_choices(value):
    choices = value.get("models")
    if not isinstance(choices, list) or not 1 <= len(choices) <= 3:
        raise BadRequest("Choose one to three models")
    names = set()
    for choice in choices:
        if (
            not isinstance(choice, dict)
            or set(choice) != {"model", "count"}
            or not isinstance(choice["model"], str)
            or type(choice["count"]) is not int
            or not 1 <= choice["count"] <= 4
        ):
            raise BadRequest("Each model needs a name and a count between 1 and 4")
        if choice["model"] in names:
            raise BadRequest("Choose each model only once")
        names.add(choice["model"])
    return choices


def draft_references(connection, project_id, supplied):
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
                    or_(
                        assets.c.project_id.is_(None), assets.c.project_id == project_id
                    ),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise BadRequest(
                "Reference hash must belong to an asset visible to this project"
            )
        # Never use client-supplied file metadata or asset descriptions.
        result.append(
            {
                "hash": row["hash"],
                "media_type": row["media_type"],
                "asset_id": row["id"],
                "asset_name": row["name"],
                "description": row["description"],
                "type_tag": row["type_tag"],
                "role": ref["role"],
            }
        )
    return result


def run_detail(connection, variant_id, run_id):
    rows = [
        serial(r)
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
        "references": first["references"],
        "generations": rows,
    }


@generation_api.route("/variants/<int:identifier>/runs", methods=["GET", "POST"])
@transaction
def variant_runs(connection, identifier):
    variant = get_row(connection, variants, identifier)
    comp = composition(connection, variant["composition_id"])
    if request.method == "GET":
        run_ids = connection.execute(
            select(generations.c.run_id, func.min(generations.c.id).label("first_id"))
            .where(generations.c.variant_id == identifier)
            .group_by(generations.c.run_id)
            .order_by(func.min(generations.c.id).desc())
        ).all()
        return jsonify([run_detail(connection, identifier, r.run_id) for r in run_ids])
    value = body(["models", "prompt", "references"], ["models"])
    choices = run_choices(value)
    # Pinned drafts must work even if the current pack cannot be assembled.
    if "references" in value:
        refs = draft_references(connection, comp["project_id"], value["references"])
        prompt = value.get("prompt")
        assembled = prompt
        edited = True
    else:
        preview = variant_preview(connection, identifier)
        refs = preview["references"]
        assembled = preview["prompt"]
        prompt = value.get("prompt", assembled)
        edited = prompt != assembled
    if not isinstance(prompt, str) or not prompt.strip():
        raise BadRequest("prompt must be nonempty text")
    available = {m["model_name"]: m["model_info"] for m in model_list(connection)}
    for choice in choices:
        info = available.get(choice["model"])
        if info is None:
            raise BadRequest("Choose an available image model")
        if len(refs) > info["max_references"]:
            raise BadRequest(
                f"{choice['model']}: selected {len(refs)} references; "
                f"accepts at most {info['max_references']}. Adjust your selection."
            )
    run_id = str(uuid4())
    for choice in choices:
        info = available[choice["model"]]
        row_id = connection.execute(
            insert(generations)
            .values(
                run_id=run_id,
                kind="composition",
                variant_id=identifier,
                model=choice["model"],
                model_info=info,
                count=choice["count"],
                prompt=prompt,
                assembled_prompt=assembled,
                edited=edited,
                references=refs,
                placeholder=info["placeholder"],
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
        variant = get_row(connection, variants, original["variant_id"])
        composition(connection, variant["composition_id"])
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
    )
    row_id = connection.execute(
        insert(generations)
        .values(**{k: original[k] for k in keys}, retry_of=identifier)
        .returning(generations.c.id)
    ).scalar_one()
    defer(connection, row_id)
    return jsonify(serial(get_row(connection, generations, row_id))), 201


@generation_api.route(
    "/variants/<int:identifier>/final", methods=["GET", "PUT", "DELETE"]
)
@transaction
def final_image(connection, identifier):
    variant = get_row(connection, variants, identifier)
    composition(connection, variant["composition_id"])
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

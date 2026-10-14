"""Read-only portable packages and deduplicated storage accounting."""

import json
from datetime import UTC, datetime
from functools import wraps
from zipfile import ZIP_STORED, ZipFile

from flask import Blueprint, Response, current_app, jsonify
from sqlalchemy import select, text
from werkzeug.exceptions import ServiceUnavailable

from image_studio.api import get_row, images_for, serial
from image_studio.feedback import generation_record
from image_studio.generation_api import effective_style, selected_final
from image_studio.schema import (
    asset_images,
    assets,
    composition_assets,
    compositions,
    generations,
    projects,
    stored_files,
    variants,
)
from image_studio.sequence import EXTENSIONS, ZipSink, slug

portability_api = Blueprint("portability", __name__, url_prefix="/api")


def snapshot(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        engine = current_app.extensions["database"]
        if engine is None:
            raise ServiceUnavailable("Database is not configured")
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                return function(connection, *args, **kwargs)

    return wrapped


def manifest(kind):
    return {
        "format": f"image-studio-{kind}",
        "format_version": 4 if kind == "composition" else 2,
        "exported_at": datetime.now(UTC).isoformat(),
    }


def asset_record(connection, identifier, *, hashes=None, image_ids=()):
    record = serial(get_row(connection, assets, identifier, deleted=True))
    record["project_id"] = None
    record["images"] = [
        image
        for image in images_for(connection, identifier)
        if hashes is None or image["hash"] in hashes or image["id"] in image_ids
    ]
    record["originals"] = [i for i in record["images"] if i["source"] == "uploaded"]
    record["references"] = [
        i for i in record["images"] if i["approved"] and not i["rejected"]
    ]
    return record


def record_hashes(record):
    return {i["hash"] for i in record["images"]} | {
        ref["hash"]
        for image in record["images"]
        for ref in (image.get("lineage") or {}).get("originals", [])
    }


def file_records(connection, hashes):
    return [
        {
            **serial(row),
            "filename": f"files/{row['hash']}.{EXTENSIONS[row['media_type']]}",
        }
        for row in connection.execute(
            select(stored_files)
            .where(stored_files.c.hash.in_(hashes))
            .order_by(stored_files.c.hash)
        ).mappings()
    ]


def asset_manifest(connection, identifier):
    result = manifest("asset")
    result["asset"] = asset_record(connection, identifier)
    result["files"] = file_records(connection, record_hashes(result["asset"]))
    return result


def composition_manifest(connection, identifier):
    comp = get_row(connection, compositions, identifier)
    result = manifest("composition")
    result["project"] = (
        serial(get_row(connection, projects, comp["project_id"]))
        if comp["project_id"] is not None
        else None
    )
    result["composition"] = serial(comp)
    style = effective_style(connection, comp)
    result["style"] = asset_record(connection, style["id"]) if style else None
    result["frames"] = []
    hashes = record_hashes(result["style"]) if result["style"] else set()
    reference_hashes = {}
    deselected = set()
    for frame in connection.execute(
        select(variants)
        .where(variants.c.composition_id == identifier)
        .order_by(variants.c.position, variants.c.id)
    ).mappings():
        record = {
            **serial(frame),
            "deleted": frame["deleted_at"] is not None,
            "final": selected_final(connection, frame),
            "runs": [],
        }
        deselected.update(frame["deselected_images"])
        deselected.update(frame["selected_originals"])
        runs = {}
        for row in connection.execute(
            select(generations)
            .where(generations.c.variant_id == frame["id"])
            .order_by(generations.c.id)
        ).mappings():
            generation = generation_record(connection, row)
            runs.setdefault(row["run_id"], []).append(generation)
            hashes.update(row["outputs"])
            for ref in row["references"]:
                hashes.add(ref["hash"])
                reference_hashes.setdefault(ref["asset_id"], set()).add(ref["hash"])
        record["runs"] = [
            {"run_id": run_id, "generations": rows} for run_id, rows in runs.items()
        ]
        if record["final"]:
            hashes.add(record["final"]["hash"])
        result["frames"].append(record)
    result["asset_pack"] = []
    pack_ids = set()
    for selection in connection.execute(
        select(composition_assets)
        .where(composition_assets.c.composition_id == identifier)
        .order_by(composition_assets.c.position, composition_assets.c.id)
    ).mappings():
        asset_id = selection["asset_id"]
        pack_ids.add(asset_id)
        images = images_for(connection, asset_id)
        used = reference_hashes.get(asset_id, set()).copy()
        if selection["active"]:
            used.update(
                i["hash"] for i in images if i["approved"] and not i["rejected"]
            )
        record = asset_record(
            connection,
            asset_id,
            hashes=used,
            image_ids=deselected
            | set(selection["deselected_images"])
            | set(selection["selected_originals"]),
        )
        hashes.update(record_hashes(record))
        result["asset_pack"].append({**serial(selection), "asset": record})
    # Pinned drafts may refer to assets that have never belonged to this pack.
    result["referenced_assets"] = [
        asset_record(connection, asset_id, hashes=reference_hashes[asset_id])
        for asset_id in sorted(reference_hashes.keys() - pack_ids)
    ]
    for record in result["referenced_assets"]:
        hashes.update(record_hashes(record))
    result["files"] = file_records(connection, hashes)
    return result


def stream_package(root, package):
    sink = ZipSink()
    with ZipFile(sink, "w", compression=ZIP_STORED) as archive:
        archive.writestr(
            "manifest.json", json.dumps(package, ensure_ascii=False, indent=2)
        )
        yield sink.drain()
        for file in package["files"]:
            with archive.open(file["filename"], "w", force_zip64=True) as output:
                yield sink.drain()
                with (root / file["hash"]).open("rb") as image:
                    while chunk := image.read(64 * 1024):
                        output.write(chunk)
                        yield sink.drain()
            yield sink.drain()
    yield sink.drain()


def download(package, name):
    return Response(
        stream_package(current_app.config["STUDIO_FILES"], package),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={slug(name)}-package.zip",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@portability_api.get("/assets/<int:identifier>/export.zip")
@snapshot
def export_asset(connection, identifier):
    package = asset_manifest(connection, identifier)
    return download(package, package["asset"]["name"])


@portability_api.get("/compositions/<int:identifier>/export.zip")
@snapshot
def export_composition(connection, identifier):
    package = composition_manifest(connection, identifier)
    return download(package, package["composition"]["name"])


def storage_totals(files, uploaded, generated, placeholder):
    result = {
        key: {"bytes": 0, "file_count": 0}
        for key in ("total", "uploaded", "generated", "placeholder")
    }
    for file in files:
        digest = file["hash"]
        category = (
            "uploaded"
            if digest in uploaded
            else "generated"
            if digest in generated or digest not in placeholder
            else "placeholder"
        )
        for key in ("total", category):
            result[key]["bytes"] += file["size"]
            result[key]["file_count"] += 1
    return result


@portability_api.get("/storage")
@snapshot
def storage(connection):
    uploaded = set(
        connection.scalars(
            select(asset_images.c.file_hash).where(asset_images.c.source == "uploaded")
        )
    )
    generated, placeholder = set(), set()
    for row in connection.execute(
        select(generations.c.outputs, generations.c.placeholder)
    ).mappings():
        (placeholder if row["placeholder"] else generated).update(row["outputs"])
    return jsonify(
        storage_totals(
            connection.execute(
                select(stored_files.c.hash, stored_files.c.size)
            ).mappings(),
            uploaded,
            generated,
            placeholder,
        )
    )

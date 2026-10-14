"""Project and asset API, with transactions owned by SQLAlchemy."""

import re
from datetime import datetime
from functools import wraps

from flask import Blueprint, current_app, jsonify, request, send_file
from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from werkzeug.exceptions import BadRequest, Conflict, NotFound, ServiceUnavailable

from image_studio.files import decode_upload, publish_file
from image_studio.schema import (
    asset_images,
    assets,
    composition_assets,
    compositions,
    generations,
    projects,
    stored_files,
)

ASSET_TYPES = {
    "person": "Person",
    "garment_product": "Garment/Product",
    "object_vehicle": "Object/Vehicle",
    "environment": "Environment",
    "style": "Style",
    "other": "Other",
}


def validate_style(connection, value):
    identifier = value.get("style_asset_id")
    if identifier is not None:
        if type(identifier) is not int or not 1 <= identifier <= 2147483647:
            raise BadRequest("style_asset_id must be a positive integer or null")
        if get_row(connection, assets, identifier)["type"] != "style":
            raise BadRequest("Choose a live Style asset")


api = Blueprint("studio", __name__, url_prefix="/api")


def transaction(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        engine = current_app.extensions["database"]
        if engine is None:
            raise ServiceUnavailable("Database is not configured")
        with engine.begin() as connection:
            return function(connection, *args, **kwargs)

    return wrapped


def serial(row):
    return {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in row.items()
    }


def include_deleted():
    value = request.args.get("include_deleted", "false")
    if value not in ("true", "false"):
        raise BadRequest("include_deleted must be true or false")
    return value == "true"


def get_row(connection, table, identifier, *, deleted=False):
    query = select(table).where(table.c.id == identifier)
    if table is assets and not deleted:
        query = query.where(assets.c.deleted_at.is_(None))
    row = connection.execute(query).mappings().first()
    if row is None:
        raise NotFound(f"{table.name.rstrip('s').capitalize()} not found")
    return row


def images_for(connection, identifier):
    query = (
        select(asset_images, stored_files)
        .join(stored_files, asset_images.c.file_hash == stored_files.c.hash)
        .where(asset_images.c.asset_id == identifier)
        .order_by(asset_images.c.id)
    )
    images = [serial(row) for row in connection.execute(query).mappings()]
    # Read the earliest producing snapshot, also for duplicated attachments.
    for image in images:
        if image["source"] == "generated":
            generation = (
                connection.execute(
                    select(generations)
                    .where(
                        generations.c.kind == "asset_reference",
                        generations.c.outputs.contains([image["hash"]]),
                    )
                    .order_by(generations.c.id)
                )
                .mappings()
                .first()
            )
            image["lineage"] = (
                {
                    "generation_id": generation["id"],
                    "originals": generation["references"],
                }
                if generation
                else None
            )
    return images


def asset_detail(connection, identifier, *, deleted=False):
    body = serial(get_row(connection, assets, identifier, deleted=deleted))
    body["images"] = [
        image
        for image in images_for(connection, identifier)
        if not image["rejected"] or request.args.get("include_rejected") == "true"
    ]
    body["originals"] = [i for i in body["images"] if i["source"] == "uploaded"]
    body["references"] = [
        i for i in body["images"] if i["approved"] and not i["rejected"]
    ]
    return body


def payload(connection, *, asset=False, creating=False):
    body = request.get_json()
    if not isinstance(body, dict):
        raise BadRequest("Expected a JSON object")
    allowed = (
        {"name", "type", "type_tag", "description", "preserve"}
        if asset
        else {"name", "instructions", "style_asset_id"}
    )
    if body.keys() - allowed:
        raise BadRequest("Unknown fields: " + ", ".join(sorted(body.keys() - allowed)))
    if creating and "name" not in body:
        raise BadRequest("name is required")
    if not asset:
        validate_style(connection, body)
    if (
        asset
        and "type" in body
        and (not isinstance(body["type"], str) or body["type"] not in ASSET_TYPES)
    ):
        raise BadRequest("Choose a valid asset type")
    for key, value in list(body.items()):
        if key == "style_asset_id":
            continue
        if key == "type_tag" and value is None:
            continue
        elif not isinstance(value, str):
            raise BadRequest(f"{key} must be text")
        elif key == "name":
            if not value.strip():
                raise BadRequest("name must not be empty")
            body[key] = value.strip()
        elif key == "type_tag":
            body[key] = value.strip() or None
    return body


@api.get("/projects")
@transaction
def list_projects(connection):
    return jsonify(
        [
            serial(row)
            for row in connection.execute(
                select(projects).order_by(projects.c.id)
            ).mappings()
        ]
    )


@api.post("/projects")
@transaction
def create_project(connection):
    row = (
        connection.execute(
            insert(projects)
            .values(**payload(connection, creating=True))
            .returning(projects)
        )
        .mappings()
        .one()
    )
    return jsonify(serial(row)), 201


@api.get("/projects/<int:identifier>")
@transaction
def read_project(connection, identifier):
    return jsonify(serial(get_row(connection, projects, identifier)))


@api.patch("/projects/<int:identifier>")
@transaction
def update_project(connection, identifier):
    get_row(connection, projects, identifier)
    values = payload(connection)
    if values:
        connection.execute(
            update(projects).where(projects.c.id == identifier).values(**values)
        )
    return jsonify(serial(get_row(connection, projects, identifier)))


@api.get("/assets")
@transaction
def list_assets(connection):
    query = select(assets).order_by(assets.c.id)
    if not include_deleted():
        query = query.where(assets.c.deleted_at.is_(None))
    if "type" in request.args:
        if request.args["type"] not in ASSET_TYPES:
            raise BadRequest("Choose a valid asset type")
        query = query.where(assets.c.type == request.args["type"])
    if "type_tag" in request.args:
        query = query.where(assets.c.type_tag == request.args["type_tag"])
    if "used_by_project" in request.args:
        project = request.args["used_by_project"]
        if (
            not project.isascii()
            or not project.isdecimal()
            or not 1 <= int(project) <= 2147483647
        ):
            raise BadRequest("used_by_project must be a positive integer")
        get_row(connection, projects, int(project))
        used = (
            select(composition_assets.c.asset_id)
            .join(compositions)
            .where(
                compositions.c.project_id == int(project),
                compositions.c.deleted_at.is_(None),
                composition_assets.c.active.is_(True),
            )
        )
        query = query.where(assets.c.id.in_(used))
    if "project_id" in request.args:
        raise BadRequest("Assets are global; use used_by_project to filter by usage")
    return jsonify([serial(row) for row in connection.execute(query).mappings()])


@api.post("/assets")
@transaction
def create_asset(connection):
    identifier = connection.execute(
        insert(assets)
        .values(**payload(connection, asset=True, creating=True))
        .returning(assets.c.id)
    ).scalar_one()
    return jsonify(asset_detail(connection, identifier)), 201


@api.get("/assets/<int:identifier>")
@transaction
def read_asset(connection, identifier):
    return jsonify(asset_detail(connection, identifier, deleted=include_deleted()))


@api.patch("/assets/<int:identifier>")
@transaction
def update_asset(connection, identifier):
    get_row(connection, assets, identifier)
    values = payload(connection, asset=True)
    if "type" in values:
        if values["type"] == "style" and connection.scalar(
            select(composition_assets.c.id)
            .where(
                composition_assets.c.asset_id == identifier,
                composition_assets.c.active.is_(True),
            )
            .limit(1)
        ):
            raise Conflict(
                "Remove this asset from subject packs before changing it to Style"
            )
        if values["type"] != "style" and any(
            connection.scalar(
                select(table.c.id).where(table.c.style_asset_id == identifier).limit(1)
            )
            for table in (projects, compositions)
        ):
            raise Conflict(
                "Remove this asset from style choices before changing its type"
            )
    if values:
        connection.execute(
            update(assets).where(assets.c.id == identifier).values(**values)
        )
    return jsonify(asset_detail(connection, identifier))


@api.delete("/assets/<int:identifier>")
@transaction
def delete_asset(connection, identifier):
    get_row(connection, assets, identifier)
    connection.execute(
        update(assets)
        .where(assets.c.id == identifier)
        .values(deleted_at=datetime.now().astimezone())
    )
    return jsonify(deleted=True)


@api.post("/assets/<int:identifier>/duplicate")
@transaction
def duplicate_asset(connection, identifier):
    original = get_row(connection, assets, identifier)
    values = {
        key: original[key]
        for key in ("name", "type", "type_tag", "description", "preserve")
    }
    values["name"] += " (copy)"
    new_id = connection.execute(
        insert(assets).values(**values).returning(assets.c.id)
    ).scalar_one()
    for image in images_for(connection, identifier):
        connection.execute(
            insert(asset_images).values(
                asset_id=new_id,
                file_hash=image["file_hash"],
                approved=image["approved"],
                source=image["source"],
                rejected=image["rejected"],
            )
        )
    return jsonify(asset_detail(connection, new_id)), 201


@api.post("/assets/<int:identifier>/images")
@transaction
def upload_images(connection, identifier):
    get_row(connection, assets, identifier)
    uploads = request.files.getlist("files")
    if not uploads:
        raise BadRequest("Supply one or more images in the files field")
    # Validate the entire batch before persisting anything.
    decoded = [decode_upload(upload) for upload in uploads]
    for data, file in decoded:
        publish_file(current_app.config["STUDIO_FILES"], file["hash"], data)
        connection.execute(
            pg_insert(stored_files).values(**file).on_conflict_do_nothing()
        )
        connection.execute(
            pg_insert(asset_images)
            .values(asset_id=identifier, file_hash=file["hash"])
            .on_conflict_do_nothing()
        )
    return jsonify(asset_detail(connection, identifier)), 201


@api.patch("/assets/<int:identifier>/images/<int:image_id>")
@transaction
def approve_image(connection, identifier, image_id):
    get_row(connection, assets, identifier)
    body = request.get_json()
    if (
        not isinstance(body, dict)
        or set(body) not in ({"approved"}, {"rejected"})
        or any(type(value) is not bool for value in body.values())
    ):
        raise BadRequest("Supply approved or rejected as a JSON boolean")
    values = dict(body)
    if body.get("approved"):
        values["rejected"] = False
    if body.get("rejected"):
        values["approved"] = False
    result = connection.execute(
        update(asset_images)
        .where(asset_images.c.asset_id == identifier, asset_images.c.id == image_id)
        .values(**values)
        .returning(asset_images.c.id)
    ).first()
    if result is None:
        raise NotFound("Image not found on this asset")
    return jsonify(asset_detail(connection, identifier))


@api.get("/files/<digest>")
@transaction
def fetch_file(connection, digest):
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise NotFound("File not found")
    row = (
        connection.execute(select(stored_files).where(stored_files.c.hash == digest))
        .mappings()
        .first()
    )
    if row is None:
        raise NotFound("File not found")
    response = send_file(
        current_app.config["STUDIO_FILES"] / digest,
        mimetype=row["media_type"],
        etag=digest,
        max_age=31536000,
    )
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

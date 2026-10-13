"""Project and asset API, with transactions owned by SQLAlchemy."""

import re
from datetime import datetime
from functools import wraps

from flask import Blueprint, current_app, jsonify, request, send_file
from sqlalchemy import insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from werkzeug.exceptions import BadRequest, NotFound, ServiceUnavailable

from image_studio.files import decode_upload, publish_file
from image_studio.schema import asset_images, assets, projects, stored_files

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
    return [serial(row) for row in connection.execute(query).mappings()]


def asset_detail(connection, identifier, *, deleted=False):
    body = serial(get_row(connection, assets, identifier, deleted=deleted))
    body["images"] = [
        image
        for image in images_for(connection, identifier)
        if not image["rejected"] or request.args.get("include_rejected") == "true"
    ]
    return body


def payload(connection, *, asset=False, creating=False):
    body = request.get_json()
    if not isinstance(body, dict):
        raise BadRequest("Expected a JSON object")
    allowed = (
        {"name", "type_tag", "description", "project_id"}
        if asset
        else {"name", "instructions"}
    )
    if body.keys() - allowed:
        raise BadRequest("Unknown fields: " + ", ".join(sorted(body.keys() - allowed)))
    if creating and "name" not in body:
        raise BadRequest("name is required")
    for key, value in list(body.items()):
        if key == "project_id":
            if value is not None:
                if type(value) is not int or not 1 <= value <= 2147483647:
                    raise BadRequest("project_id must be a positive integer or null")
                get_row(connection, projects, value)
        elif key == "type_tag" and value is None:
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
    if "type_tag" in request.args:
        query = query.where(assets.c.type_tag == request.args["type_tag"])
    if "project_id" in request.args:
        project = request.args["project_id"]
        if project == "global":
            query = query.where(assets.c.project_id.is_(None))
        else:
            if (
                not project.isascii()
                or not project.isdecimal()
                or not 1 <= int(project) <= 2147483647
            ):
                raise BadRequest("project_id must be a positive integer or global")
            get_row(connection, projects, int(project))
            query = query.where(
                or_(assets.c.project_id.is_(None), assets.c.project_id == int(project))
            )
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
        key: original[key] for key in ("name", "type_tag", "description", "project_id")
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

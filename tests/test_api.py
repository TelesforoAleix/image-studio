"""Integration routes use an isolated schema on real Postgres, never SQLite."""

import io
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import func, inspect, select
from sqlalchemy.schema import CreateSchema, DropSchema
from test_files import image_bytes

from image_studio import create_app
from image_studio.database import database_engine
from image_studio.files import FILE_LIMIT, REQUEST_LIMIT
from image_studio.schema import asset_images, assets, metadata, stored_files


@pytest.fixture
def client(monkeypatch, tmp_path):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL is unset; integration tests require real Postgres"
        )
    admin = database_engine(url)
    schema = "test_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    test_url = admin.url.update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("DATABASE_URL", test_url.render_as_string(hide_password=False))
    monkeypatch.setenv("STUDIO_FILES", str(tmp_path))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        app = create_app()
        app.config["TESTING"] = True
        yield app.test_client(), app.extensions["database"], tmp_path
        app.extensions["database"].dispose()
    finally:
        # Only this test's freshly created, uniquely named schema is disposable.
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def new_asset(client, **fields):
    response = client.post("/api/assets", json={"name": "Synthetic asset", **fields})
    assert response.status_code == 201, response.json
    return response.json


def upload(client, identifier, *data):
    return client.post(
        f"/api/assets/{identifier}/images",
        data={"files": [(io.BytesIO(content), name) for content, name in data]},
        content_type="multipart/form-data",
    )


def test_migration_is_idempotent_and_matches_definitions(client):
    _, engine, _ = client
    assert set(inspect(engine).get_table_names()) == {
        "projects",
        "assets",
        "stored_files",
        "asset_images",
        "alembic_version",
    }
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []
        assert (
            connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
            == "0001"
        )


def test_project_routes(client):
    c, _, _ = client
    assert c.get("/api/projects").json == []
    result = c.post(
        "/api/projects",
        json={"name": " Synthetic project ", "instructions": "Synthetic direction"},
    )
    assert result.status_code == 201
    project = result.json
    assert project["name"] == "Synthetic project"
    assert c.get(f"/api/projects/{project['id']}").json == project
    edited = c.patch(
        f"/api/projects/{project['id']}",
        json={"name": "Edited", "instructions": "New direction"},
    )
    assert edited.status_code == 200
    assert edited.json["instructions"] == "New direction"
    assert c.get("/api/projects").json == [edited.json]
    assert c.get("/api/projects/99999").status_code == 404
    assert c.patch("/api/projects/99999", json={"name": "Missing"}).status_code == 404


def test_asset_routes_and_visibility(client):
    c, _, _ = client
    p1 = c.post("/api/projects", json={"name": "Project one"}).json["id"]
    p2 = c.post("/api/projects", json={"name": "Project two"}).json["id"]
    global_asset = new_asset(c, type_tag="garment", description="Synthetic description")
    own = new_asset(c, project_id=p1, type_tag="person")
    other = new_asset(c, project_id=p2)
    assert len(c.get("/api/assets").json) == 3
    assert {a["id"] for a in c.get(f"/api/assets?project_id={p1}").json} == {
        global_asset["id"],
        own["id"],
    }
    assert {a["id"] for a in c.get(f"/api/assets?project_id={p2}").json} == {
        global_asset["id"],
        other["id"],
    }
    assert [
        a["id"] for a in c.get("/api/assets?project_id=global&type_tag=garment").json
    ] == [global_asset["id"]]
    assert c.get(f"/api/assets/{own['id']}").json == own
    edited = c.patch(
        f"/api/assets/{own['id']}",
        json={
            "name": "Edited",
            "type_tag": "object",
            "description": "Changed",
            "project_id": None,
        },
    )
    assert edited.status_code == 200
    assert edited.json["project_id"] is None
    assert edited.json["description"] == "Changed"
    assert edited.json["type_tag"] == "object"
    assert c.get("/api/assets/99999").status_code == 404
    assert c.patch("/api/assets/99999", json={}).status_code == 404


def test_upload_duplicate_approvals_delete_and_files(client):
    c, engine, root = client
    asset = new_asset(c, type_tag="object", description="Synthetic description")
    identifier = asset["id"]
    png, jpeg = image_bytes(), image_bytes("JPEG", "blue")
    result = upload(
        c, identifier, (png, "wrong.txt"), (jpeg, "wrong.png"), (png, "again.png")
    )
    assert result.status_code == 201
    first, second = result.json["images"]
    assert first["media_type"] == "image/png"
    assert second["media_type"] == "image/jpeg"
    assert first["source"] == "uploaded"
    assert not first["approved"]
    timestamps = {p.name: p.stat().st_mtime_ns for p in root.iterdir()}
    assert upload(c, identifier, (png, "again.png")).status_code == 201
    assert timestamps == {p.name: p.stat().st_mtime_ns for p in root.iterdir()}
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(stored_files)) == 2
        assert connection.scalar(select(func.count()).select_from(asset_images)) == 2
    assert c.patch(
        f"/api/assets/{identifier}/images/{first['id']}", json={"approved": True}
    ).json["images"][0]["approved"]
    assert (
        c.patch(
            f"/api/assets/{identifier}/images/{second['id']}", json={"approved": True}
        ).status_code
        == 200
    )
    replacement = c.patch(
        f"/api/assets/{identifier}/images/{first['id']}", json={"approved": False}
    ).json
    assert [i["approved"] for i in replacement["images"]] == [False, True]
    copy_response = c.post(f"/api/assets/{identifier}/duplicate")
    assert copy_response.status_code == 201
    copy = copy_response.json
    assert copy["name"] == asset["name"] + " (copy)"
    for key in ("type_tag", "description", "project_id"):
        assert copy[key] == asset[key]
    assert [(i["hash"], i["approved"]) for i in copy["images"]] == [
        (i["hash"], i["approved"]) for i in replacement["images"]
    ]
    assert len(list(root.iterdir())) == 2
    assert c.delete(f"/api/assets/{identifier}").json == {"deleted": True}
    assert [a["id"] for a in c.get("/api/assets").json] == [copy["id"]]
    assert c.get(f"/api/assets/{identifier}").status_code == 404
    assert len(c.get("/api/assets?include_deleted=true").json) == 2
    assert c.get(f"/api/assets/{identifier}?include_deleted=true").json["deleted_at"]
    for image, expected in ((first, png), (second, jpeg)):
        response = c.get(f"/api/files/{image['hash']}")
        assert response.data == expected
        assert response.content_type == image["media_type"]
        assert (
            response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
        )
        assert (
            c.get(
                f"/api/files/{image['hash']}",
                headers={"If-None-Match": response.headers["ETag"]},
            ).status_code
            == 304
        )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(assets)) == 2
        assert connection.scalar(select(func.count()).select_from(asset_images)) == 4
        assert connection.scalar(select(func.count()).select_from(stored_files)) == 2
    for method, path, kwargs in [
        ("post", f"/api/assets/{identifier}/duplicate", {}),
        ("patch", f"/api/assets/{identifier}", {"json": {"name": "Gone"}}),
        ("post", f"/api/assets/{identifier}/images", {}),
        (
            "patch",
            f"/api/assets/{identifier}/images/{first['id']}",
            {"json": {"approved": True}},
        ),
    ]:
        assert getattr(c, method)(path, **kwargs).status_code == 404


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_accepted_upload_formats(client, format):
    c, _, _ = client
    identifier = new_asset(c)["id"]
    data = image_bytes(format)
    response = upload(c, identifier, (data, "synthetic.bin"))
    assert response.status_code == 201
    assert c.get("/api/files/" + response.json["images"][0]["hash"]).data == data


@pytest.mark.parametrize(
    "data,name",
    [
        (b"not an image", "synthetic.txt"),
        (b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32, "synthetic.heic"),
        (image_bytes("GIF"), "synthetic.gif"),
    ],
)
def test_bad_upload_batch_persists_nothing(client, data, name):
    c, engine, root = client
    identifier = new_asset(c)["id"]
    response = upload(c, identifier, (image_bytes(), "good.png"), (data, name))
    assert response.status_code == 400
    assert name in response.json["error"]
    assert "JPEG, PNG or WebP" in response.json["error"]
    assert list(root.iterdir()) == []
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(stored_files)) == 0


def test_limits_and_missing_upload(client):
    c, _, root = client
    identifier = new_asset(c)["id"]
    response = upload(c, identifier, (b"x" * (FILE_LIMIT + 1), "large.png"))
    assert response.status_code == 413
    assert "large.png" in response.json["error"]
    assert "25 MB" in response.json["error"]
    response = c.post(
        f"/api/assets/{identifier}/images",
        data=b"x",
        environ_overrides={"CONTENT_LENGTH": str(REQUEST_LIMIT + 1)},
        content_type="multipart/form-data",
    )
    assert response.status_code == 413
    assert "90 MB" in response.json["error"]
    assert c.post(f"/api/assets/{identifier}/images").status_code == 400
    assert list(root.iterdir()) == []


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/projects", {}),
        ("/api/projects", {"name": " "}),
        ("/api/projects", {"name": 5}),
        ("/api/projects", []),
        ("/api/projects", {"name": "OK", "instructions": None}),
        ("/api/assets", {"name": "OK", "unexpected": "value"}),
        ("/api/assets", {"name": "OK", "project_id": True}),
        ("/api/assets", {"name": "OK", "project_id": -1}),
        ("/api/assets", {"name": "OK", "description": None}),
        ("/api/assets", {"name": "OK", "type_tag": []}),
    ],
)
def test_validation_errors(client, path, body):
    c, _, _ = client
    response = c.post(path, json=body)
    assert response.status_code == 400
    assert response.json["error"]


def test_unknown_foreign_keys_images_filters_and_files(client):
    c, _, _ = client
    identifier = new_asset(c)["id"]
    assert (
        c.post("/api/assets", json={"name": "Missing", "project_id": 99999}).status_code
        == 404
    )
    assert (
        c.post(
            "/api/assets", data='{"name":', content_type="application/json"
        ).status_code
        == 400
    )
    for query in (
        "project_id=bad",
        "project_id=-1",
        "project_id=999999999999",
        "include_deleted=maybe",
    ):
        assert c.get(f"/api/assets?{query}").status_code == 400
    assert c.get("/api/assets?project_id=99999").status_code == 404
    assert c.get("/api/files/" + "0" * 64).status_code == 404
    assert c.get("/api/files/not-a-hash").status_code == 404
    assert (
        c.patch(
            f"/api/assets/{identifier}/images/99999", json={"approved": True}
        ).status_code
        == 404
    )
    for body in (
        {"approved": "true"},
        {"approved": 1},
        {},
        [],
        {"approved": True, "extra": 1},
    ):
        assert (
            c.patch(f"/api/assets/{identifier}/images/99999", json=body).status_code
            == 400
        )
    assert upload(c, 99999, (image_bytes(), "missing.png")).status_code == 404


def test_duplicate_keeps_project_visibility(client):
    c, _, _ = client
    project = c.post("/api/projects", json={"name": "Synthetic"}).json["id"]
    asset = new_asset(c, project_id=project)
    copy = c.post(f"/api/assets/{asset['id']}/duplicate").json
    assert copy["project_id"] == project

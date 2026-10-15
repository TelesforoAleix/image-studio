"""Postgres integration for curated projects and the V1 backfill."""

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from test_api import client as postgres_client
from test_api import new_asset, upload
from test_files import image_bytes
from test_portability import unpack

from image_studio.schema import project_assets
from scripts.check_project_assets_migration import main as migration_proof

client = postgres_client


def test_v1_backfill_twice_and_downgrade(client):
    command.downgrade(Config("alembic.ini"), "0010")
    migration_proof()


def test_curate_pack_remove_deleted_readd_and_export(client):
    c, engine, _ = client
    project = c.post("/api/projects", json={"name": "Synthetic folder"}).json
    subject = new_asset(c)
    comp = c.post(
        "/api/compositions",
        json={"name": "Synthetic", "kind": "single", "project_id": project["id"]},
    ).json
    members = f"/api/projects/{project['id']}/assets"
    member = members + f"/{subject['id']}"
    pack = f"/api/compositions/{comp['id']}/assets/{subject['id']}"
    assert c.get(members).json == []
    assert c.put(pack, json={"role": "Subject"}).status_code == 200
    first = c.get(members).json
    assert [a["id"] for a in first] == [subject["id"]]
    assert c.put(member).status_code == 200
    assert c.put(pack, json={"role": "Changed"}).status_code == 200
    assert c.get(members).json == first
    before = unpack(c.get(f"/api/compositions/{comp['id']}/export.zip").data)
    for _ in range(2):
        assert c.delete(member).status_code == 200
    assert c.get(members).json == []
    assert (
        c.get(f"/api/compositions/{comp['id']}").json["assets"][0]["role"] == "Changed"
    )
    with engine.connect() as connection:
        row = connection.execute(select(project_assets)).mappings().one()
        assert row["removed_at"] is not None
    # A subsequent pack selection revives the same retained membership.
    assert c.put(pack, json={"role": "Changed"}).status_code == 200
    assert len(c.get(members).json) == 1
    after = unpack(c.get(f"/api/compositions/{comp['id']}/export.zip").data)
    before.pop("exported_at")
    after.pop("exported_at")
    assert before == after and "project_assets" not in after
    c.delete(f"/api/assets/{subject['id']}")
    assert c.get(members).json[0]["deleted_at"]
    assert c.put(member).status_code == 404
    assert c.delete(member).status_code == 200
    assert c.get(members).json == []
    with engine.connect() as connection:
        assert len(connection.execute(select(project_assets)).all()) == 1
    assert c.get("/api/projects/999999/assets").status_code == 404
    assert c.put(members + "/999999").status_code == 404
    assert c.delete(members + "/999999").status_code == 404


def test_search_thumbnail_priority_and_standalone(client):
    c, _, _ = client
    subject = new_asset(c, name="Synthetic 100%_Subject")
    images = upload(
        c,
        subject["id"],
        (image_bytes(), "first.png"),
        (image_bytes("PNG", "blue"), "second.png"),
    ).json["images"]
    path = f"/api/assets/{subject['id']}"
    listing = "/api/assets?thumbnails=true&q=100%25_"
    assert c.get(listing).json[0]["thumbnail"] == images[0]["hash"]
    c.patch(path + f"/images/{images[1]['id']}", json={"approved": True})
    assert c.get(listing).json[0]["thumbnail"] == images[1]["hash"]
    assert c.get("/api/assets?q=absent").json == []
    comp = c.post(
        "/api/compositions", json={"name": "Synthetic 100%_single", "kind": "single"}
    ).json
    assert (
        c.put(
            f"/api/compositions/{comp['id']}/assets/{subject['id']}",
            json={"role": "Subject"},
        ).status_code
        == 200
    )
    listing = c.get("/api/compositions?q=100%25_").json
    assert len(listing) == 1 and listing[0]["frame_count"] == 1
    assert c.get("/api/compositions?q=absent").json == []


def test_style_choices_and_duplicate_pack_add_membership(client):
    c, _, _ = client
    style = new_asset(c, type="style")
    other_style = new_asset(c, type="style")
    subject = new_asset(c)
    project = c.post(
        "/api/projects",
        json={"name": "Synthetic styled", "style_asset_id": style["id"]},
    ).json
    path = f"/api/projects/{project['id']}/assets"
    assert [a["id"] for a in c.get(path).json] == [style["id"]]
    c.patch(
        f"/api/projects/{project['id']}", json={"style_asset_id": other_style["id"]}
    )
    assert {a["id"] for a in c.get(path).json} == {style["id"], other_style["id"]}
    c.delete(path + f"/{style['id']}")
    comp = c.post(
        "/api/compositions",
        json={
            "name": "Synthetic",
            "kind": "single",
            "project_id": project["id"],
            "style_asset_id": style["id"],
        },
    ).json
    comp_path = f"/api/compositions/{comp['id']}"
    assert {a["id"] for a in c.get(path).json} == {style["id"], other_style["id"]}
    c.put(comp_path + f"/assets/{subject['id']}", json={"role": "Subject"})
    c.delete(path + f"/{subject['id']}")
    c.delete(path + f"/{style['id']}")
    assert c.post(comp_path + "/duplicate").status_code == 201
    assert {a["id"] for a in c.get(path).json} == {
        subject["id"],
        style["id"],
        other_style["id"],
    }

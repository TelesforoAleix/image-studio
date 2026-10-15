"""Optional folders, global usage, exact snapshots, kind rules and duplication."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from test_api import client as postgres_client
from test_api import new_asset, upload
from test_files import image_bytes
from test_generation_api import generation_client as structure_client
from test_portability import unpack
from test_runs import complete

from image_studio.prompting import assemble
from image_studio.schema import composition_assets
from scripts.check_structure_migration import main as migration_proof

client = postgres_client
generation_client = structure_client


def create(c, **values):
    response = c.post(
        "/api/compositions",
        json={"name": "Synthetic structure", "kind": "single", **values},
    )
    assert response.status_code == 201, response.json
    return response.json


def test_template_order_and_empty_parts():
    frame = {"instructions": "Action"}
    comp = {"brief": "Direction\n\nScene"}
    assert assemble(None, comp, [], frame)["prompt"] == "Direction\n\nScene\n\nAction"
    assert assemble({"instructions": "Project"}, comp, [], frame)["prompt"] == (
        "Project\n\nDirection\n\nScene\n\nAction"
    )
    assert assemble(None, {"brief": ""}, [], frame)["prompt"] == "Action"


def test_s8_upgrade_twice_and_downgrade_with_rows(client):
    command.downgrade(Config("alembic.ini"), "0005")
    migration_proof()


def test_standalone_moves_listing_exports_and_snapshots(generation_client):
    c, _, root = generation_client
    comp = create(c, brief="Composition direction\n\nScene")
    frame = comp["variants"][0]["id"]
    path = f"/api/compositions/{comp['id']}"
    asset = new_asset(c)
    image = upload(c, asset["id"], (image_bytes(), "synthetic.png")).json["images"][0]
    c.patch(f"/api/assets/{asset['id']}/images/{image['id']}", json={"approved": True})
    assert (
        c.put(path + f"/assets/{asset['id']}", json={"role": "Subject"}).status_code
        == 200
    )
    preview = c.get(f"/api/variants/{frame}/preview").json
    assert preview["prompt"].startswith("Composition direction\n\nScene")
    run = c.post(
        f"/api/variants/{frame}/runs",
        json={"models": [{"model": "placeholder-a", "count": 1}]},
    ).json
    done = complete(c, root, run["generations"][0])
    assert c.get("/api/compositions").json[0]["thumbnail"] == done["outputs"][0]
    c.put(
        f"/api/variants/{frame}/final", json={"generation_id": done["id"], "output": 0}
    )
    package = unpack(c.get(path + "/export.zip").data)
    assert package["project"] is None and package["format_version"] == 5
    assert package["asset_pack"][0]["asset"]["project_id"] is None
    assert c.get(path + "/sequence.zip").status_code == 200
    folders = [
        c.post(
            "/api/projects",
            json={"name": f"Folder {i}", "instructions": f"Direction {i}"},
        ).json
        for i in range(2)
    ]
    for folder in folders:
        assert c.patch(path, json={"project_id": folder["id"]}).status_code == 200
        assert (
            c.get(f"/api/variants/{frame}/preview").json["prompt"]
            == f"{folder['instructions']}\n\n" + preview["prompt"]
        )
        listing = c.get(f"/api/compositions?project_id={folder['id']}").json
        assert len(listing) == 1 and listing[0]["kind"] == "single"
        assert (
            listing[0]["project"] == folder
            and listing[0]["thumbnail"] == done["outputs"][0]
        )
        assert c.get(f"/api/projects/{folder['id']}/compositions").json == listing
        assert [
            a["id"] for a in c.get(f"/api/assets?used_by_project={folder['id']}").json
        ] == [asset["id"]]
        assert c.get(f"/api/generations/{done['id']}").json == done
    assert c.get(f"/api/assets?used_by_project={folders[0]['id']}").json == []
    assert c.patch(path, json={"project_id": None}).json["project_id"] is None
    assert c.get(f"/api/variants/{frame}/preview").json == preview
    assert c.get("/api/compositions?project_id=none").json[0]["id"] == comp["id"]
    c.delete(path)
    assert c.get("/api/compositions").json == []
    assert c.get(f"/api/generations/{done['id']}").json == done


def test_kind_rules_and_duplicate_preserve_pack_frames_without_history(
    generation_client,
):
    c, engine, root = generation_client
    comp = create(c, brief="Direction\n\nScene")
    path = f"/api/compositions/{comp['id']}"
    assert c.post(path + "/variants", json={}).status_code == 409
    assert c.patch(path, json={"kind": "storyboard"}).status_code == 200
    added = c.post(
        path + "/variants", json={"name": "Second", "instructions": "Action"}
    ).json
    assert c.patch(path, json={"kind": "single"}).status_code == 409
    asset = new_asset(c)
    images = upload(
        c, asset["id"], (image_bytes(), "a.png"), (image_bytes("PNG", "blue"), "b.png")
    ).json["images"]
    for image in images:
        c.patch(
            f"/api/assets/{asset['id']}/images/{image['id']}", json={"approved": True}
        )
    c.put(
        path + f"/assets/{asset['id']}",
        json={"role": "Subject", "deselected_images": [images[0]["id"]]},
    )
    c.patch(
        f"/api/variants/{added['id']}", json={"deselected_images": [images[1]["id"]]}
    )
    removed = new_asset(c)
    c.put(path + f"/assets/{removed['id']}", json={"role": "Removed"})
    c.delete(path + f"/assets/{removed['id']}")
    run = c.post(
        f"/api/variants/{added['id']}/runs",
        json={"models": [{"model": "placeholder-a", "count": 1}]},
    ).json
    done = complete(c, root, run["generations"][0])
    c.put(
        f"/api/variants/{added['id']}/final",
        json={"generation_id": done["id"], "output": 0},
    )
    ids = [added["id"], comp["variants"][0]["id"]]
    c.put(path + "/frame-order", json={"ids": ids})
    original = c.get(path).json
    copy = c.post(path + "/duplicate").json
    assert copy["name"] == original["name"] + " (copy)"
    for field in ["project_id", "kind", "brief"]:
        assert copy[field] == original[field]
    for a, b in zip(copy["variants"], original["variants"], strict=True):
        for field in ["name", "instructions", "position", "deselected_images"]:
            assert a[field] == b[field]
        assert a["final"] is None and a["final_generation_id"] is None
        assert c.get(f"/api/variants/{a['id']}/runs").json == []
    with engine.connect() as connection:
        packs = [
            list(
                connection.execute(
                    select(composition_assets)
                    .where(composition_assets.c.composition_id == identifier)
                    .order_by(composition_assets.c.position)
                ).mappings()
            )
            for identifier in [original["id"], copy["id"]]
        ]
    assert [
        {k: v for k, v in s.items() if k not in ["id", "composition_id"]}
        for s in packs[0]
    ] == [
        {k: v for k, v in s.items() if k not in ["id", "composition_id"]}
        for s in packs[1]
    ]
    assert c.get(path).json == original
    assert c.get(f"/api/generations/{done['id']}").json == done
    c.delete(f"/api/variants/{added['id']}")
    assert c.patch(path, json={"kind": "single"}).status_code == 200


@pytest.mark.parametrize(
    "values",
    [
        {"kind": "invalid"},
        {"kind": []},
        {"project_id": True},
        {"project_id": -1},
        {"direction": None},
        {"brief": 1},
        {"name": " "},
        {"unknown": 1},
    ],
)
def test_composition_validation(client, values):
    c, _, _ = client
    assert (
        c.post(
            "/api/compositions", json={"name": "Synthetic", "kind": "single", **values}
        ).status_code
        == 400
    )
    comp = create(c)
    assert c.patch(f"/api/compositions/{comp['id']}", json=values).status_code == 400


def test_missing_project_and_bad_filter(client):
    c, _, _ = client
    assert (
        c.post(
            "/api/compositions",
            json={"name": "Synthetic", "kind": "single", "project_id": 99999},
        ).status_code
        == 404
    )
    for query in ["project_id=bad", "project_id=-1", "project_id=999999999999"]:
        assert c.get("/api/compositions?" + query).status_code == 400
    assert c.get("/api/compositions?project_id=99999").status_code == 404
    assert c.get("/api/assets?used_by_project=bad").status_code == 400

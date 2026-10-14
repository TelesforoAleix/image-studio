"""Ordered shared-pack frames, byte-exact exports and retained history."""

import hashlib
import io
import os
import uuid
from pathlib import Path
from zipfile import ZipFile

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.schema import CreateSchema, DropSchema
from test_api import client as postgres_client
from test_generation_api import generation_client as frame_client
from test_generation_api import setup_composition
from test_runs import complete

from image_studio.database import database_engine
from image_studio.schema import composition_assets, generations, variants
from image_studio.sequence import slug, stream_sequence

client = postgres_client
generation_client = frame_client


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Frame 2", "frame-2"),
        ("../../Café\\test", "cafe-test"),
        ("☀", "untitled"),
        ("A" * 100, "a" * 80),
    ],
)
def test_safe_slug(name, expected):
    assert slug(name) == expected


def test_stream_zip_unchanged_and_empty(tmp_path):
    content = b"synthetic" * 20000
    digest = hashlib.sha256(content).hexdigest()
    (tmp_path / digest).write_bytes(content)
    before = list(tmp_path.iterdir())
    zipped = b"".join(
        stream_sequence(tmp_path, [{"hash": digest, "filename": "01-frame.png"}])
    )
    with ZipFile(io.BytesIO(zipped)) as archive:
        assert archive.namelist() == ["01-frame.png"]
        assert archive.read("01-frame.png") == content
    with ZipFile(io.BytesIO(b"".join(stream_sequence(tmp_path, [])))) as archive:
        assert archive.namelist() == []
    assert list(tmp_path.iterdir()) == before


def test_storyboard_journey(generation_client):
    c, engine, root = generation_client
    _, comp, asset = setup_composition(c)
    path = f"/api/compositions/{comp['id']}"
    c.put(path + f"/assets/{asset['id']}", json={"role": "Subject"})
    frames = [comp["variants"][0]]
    for _ in range(2):
        response = c.post(path + "/variants", json={})
        assert response.status_code == 201
        frames.append(response.json)
    assert [f["name"] for f in frames] == ["Frame 1", "Frame 2", "Frame 3"]
    excluded = asset["images"][0]
    assert (
        c.patch(
            f"/api/variants/{frames[1]['id']}",
            json={"deselected_images": [excluded["id"]]},
        ).status_code
        == 200
    )
    done = []
    for index, frame in enumerate(frames):
        vpath = f"/api/variants/{frame['id']}"
        assert (
            c.patch(
                vpath,
                json={"name": f"Shot {index + 1}", "instructions": f"Action {index}"},
            ).status_code
            == 200
        )
        preview = c.post(
            vpath + "/preview",
            json={"scene": "Draft scene", "instructions": "Draft action"},
        ).json
        assert preview["prompt"].endswith("Draft action")
        assert len(preview["references"]) == (1 if index == 1 else 2)
        run = c.post(
            vpath + "/runs", json={"models": [{"model": "placeholder-a", "count": 1}]}
        ).json
        g = complete(c, root, run["generations"][0])
        assert g["placeholder"] and g["prompt"].endswith(f"Action {index}")
        assert len(g["references"]) == (1 if index == 1 else 2)
        done.append(g)
        if index != 1:
            assert (
                c.put(
                    vpath + "/final", json={"generation_id": g["id"], "output": 0}
                ).status_code
                == 200
            )
    manifest = c.get(path + "/sequence").json
    assert manifest["skipped"] == [{"id": frames[1]["id"], "name": "Shot 2"}]
    assert [e["filename"] for e in manifest["entries"]] == [
        "01-shot-1.png",
        "02-shot-3.png",
    ]
    before = {p.name: p.stat().st_mtime_ns for p in root.iterdir()}
    response = c.get(path + "/sequence.zip")
    assert (
        response.status_code == 200
        and "synthetic-scene.zip" in response.headers["Content-Disposition"]
    )
    with ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.namelist() == [e["filename"] for e in manifest["entries"]]
        for entry in manifest["entries"]:
            assert (
                hashlib.sha256(archive.read(entry["filename"])).hexdigest()
                == entry["hash"]
            )
    assert {p.name: p.stat().st_mtime_ns for p in root.iterdir()} == before
    c.put(
        f"/api/variants/{frames[1]['id']}/final",
        json={"generation_id": done[1]["id"], "output": 0},
    )
    ids = [frames[i]["id"] for i in [2, 0, 1]]
    assert c.put(path + "/frame-order", json={"ids": ids}).status_code == 200
    assert [f["id"] for f in c.get(path).json["variants"]] == ids
    assert [e["frame_id"] for e in c.get(path + "/sequence").json["entries"]] == ids
    _, foreign, _ = setup_composition(c)
    for invalid in [
        ids[:-1],
        ids + ids[:1],
        [ids[0], ids[1], foreign["variants"][0]["id"]],
        [True, ids[1], ids[2]],
        None,
    ]:
        assert c.put(path + "/frame-order", json={"ids": invalid}).status_code == 400
        assert [f["id"] for f in c.get(path).json["variants"]] == ids
    assert c.delete(f"/api/variants/{frames[0]['id']}").status_code == 200
    assert c.get(f"/api/variants/{frames[0]['id']}").json["deleted_at"]
    assert [f["id"] for f in c.get(path).json["variants"]] == [ids[0], ids[2]]
    assert [e["frame_id"] for e in c.get(path + "/sequence").json["entries"]] == [
        ids[0],
        ids[2],
    ]
    assert c.get(f"/api/generations/{done[0]['id']}").json == done[0]
    assert c.get(f"/api/files/{done[0]['outputs'][0]}").status_code == 200
    assert c.get(f"/api/variants/{frames[0]['id']}/runs").status_code == 200
    assert (
        c.get(f"/api/variants/{frames[0]['id']}/final").json["hash"]
        == done[0]["outputs"][0]
    )
    for method, suffix, payload in [
        ("patch", "", {"instructions": "changed"}),
        ("post", "/runs", {"models": [{"model": "placeholder-a", "count": 1}]}),
        ("post", "/generations", {"model": "placeholder-a", "count": 1}),
        ("delete", "/final", None),
    ]:
        assert (
            getattr(c, method)(
                f"/api/variants/{frames[0]['id']}" + suffix, json=payload
            ).status_code
            == 404
        )
    assert c.delete(f"/api/variants/{frames[2]['id']}").status_code == 200
    assert c.delete(f"/api/variants/{frames[1]['id']}").status_code == 409
    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(composition_assets)
                .where(composition_assets.c.composition_id == comp["id"])
            )
            == 1
        )
        assert connection.scalar(select(func.count()).select_from(generations)) == 3


def test_frame_input_refusals_and_pack_changes(generation_client):
    c, _, _ = generation_client
    _, comp, asset = setup_composition(c)
    path = f"/api/variants/{comp['variants'][0]['id']}"
    for payload in [
        {"name": " "},
        {"name": None},
        {"instructions": 5},
        {"deselected_images": None},
        {"deselected_images": [True]},
        {"deselected_images": [999]},
        {"deselected_images": [asset["images"][1]["id"]]},
        {"deselected_images": [asset["images"][0]["id"]] * 2},
        {"asset_id": asset["id"]},
    ]:
        assert c.patch(path, json=payload).status_code == 400
    assert (
        c.post(
            f"/api/compositions/{comp['id']}/variants", json={"name": ""}
        ).status_code
        == 400
    )
    assert c.get(f"/api/compositions/{comp['id']}/sequence").json["entries"] == []
    assert (
        c.patch(
            path, json={"deselected_images": [asset["images"][0]["id"]]}
        ).status_code
        == 200
    )
    assert c.get(path + "/preview").json["references"] == []
    c.put(
        f"/api/compositions/{comp['id']}/assets/{asset['id']}", json={"role": "Changed"}
    )
    refs = c.get(path + "/preview").json["references"]
    assert [r["hash"] for r in refs] == [asset["images"][1]["hash"]]
    assert refs[0]["role"] == "Changed"


def test_s5_migration_with_run_and_final_twice(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is unset; requires real Postgres")
    admin = database_engine(url)
    schema = "test_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    test_url = admin.url.update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("DATABASE_URL", test_url.render_as_string(hide_password=False))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = database_engine(test_url)
    try:
        command.upgrade(config, "0003")
        with engine.begin() as connection:
            for sql in [
                "INSERT INTO projects (name) VALUES ('Synthetic')",
                "INSERT INTO compositions (project_id, name) VALUES (1, 'Synthetic')",
                "INSERT INTO variants (composition_id, instructions) "
                "VALUES (1, 'Action')",
                """INSERT INTO generations
            (kind, variant_id, run_id, model, model_info, prompt, assembled_prompt,
             edited, "references", placeholder, count, state, outputs)
            VALUES ('composition', 1, 'synthetic-run', 'synthetic', '{}', 'Prompt',
                    'Prompt', false, '[]', true, 1, 'done', '["synthetic-hash"]')""",
                "UPDATE variants SET final_generation_id = 1, final_output = 0",
            ]:
                connection.execute(text(sql))
            before = list(
                connection.execute(text("SELECT * FROM generations")).mappings()
            )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            after = list(connection.execute(select(generations)).mappings())
            assert [{key: row[key] for key in before[0]} for row in after] == before
            assert all(row["service_failures"] == 0 for row in after)
            frame = connection.execute(select(variants)).mappings().one()
            assert frame["deleted_at"] is None and frame["deselected_images"] == []
            assert (
                frame["instructions"] == "Action"
                and frame["final_generation_id"] == 1
                and frame["final_output"] == 0
            )
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def test_concurrent_deletes_keep_one_frame(generation_client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    c, _, _ = generation_client
    _, comp, _ = setup_composition(c)
    second = c.post(f"/api/compositions/{comp['id']}/variants", json={}).json
    barrier = Barrier(2)

    def remove(identifier):
        with c.application.test_client() as concurrent_client:
            barrier.wait(timeout=10)
            return concurrent_client.delete(f"/api/variants/{identifier}").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(remove, [comp["variants"][0]["id"], second["id"]]))
    assert sorted(results) == [200, 409]
    assert len(c.get(f"/api/compositions/{comp['id']}").json["variants"]) == 1


def test_frame_deselections_renumber_without_changing_shared_pack():
    from image_studio.prompting import assemble

    asset = {"id": 1, "name": "Synthetic", "description": "", "type_tag": None}
    images = [
        {
            "id": i,
            "hash": str(i),
            "approved": True,
            "rejected": False,
            "media_type": "image/png",
        }
        for i in range(1, 4)
    ]
    selection = {"role": "Subject", "deselected_images": [2]}
    preview = assemble(
        {"instructions": "Direction"},
        {"scene": "Scene"},
        [(asset, selection, images)],
        {"instructions": "Action", "deselected_images": [1]},
    )
    assert [r["hash"] for r in preview["references"]] == ["3"]
    assert "reference images 1" in preview["prompt"]
    assert preview["prompt"].endswith("Action")
    assert selection["deselected_images"] == [2]

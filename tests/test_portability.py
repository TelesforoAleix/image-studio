"""Portable packages retain exact history and never mutate database or files."""

import hashlib
import io
import json
from zipfile import ZipFile

import pytest
from sqlalchemy import select, update
from test_api import client as postgres_client
from test_api import new_asset, upload
from test_files import image_bytes
from test_generation_api import generation_client as package_client
from test_generation_api import setup_composition
from test_runs import complete

from image_studio.portability import storage_totals, stream_package
from image_studio.schema import generations, metadata, stored_files

client = postgres_client
generation_client = package_client


def unpack(data):
    with ZipFile(io.BytesIO(data)) as archive:
        package = json.loads(archive.read("manifest.json"))
        assert package["format_version"] == (
            2 if package["format"] == "image-studio-composition" else 1
        )
        assert package["exported_at"]
        assert set(archive.namelist()) == {"manifest.json"} | {
            f["filename"] for f in package["files"]
        }
        assert len(archive.namelist()) == 1 + len(package["files"])
        for file in package["files"]:
            content = archive.read(file["filename"])
            assert hashlib.sha256(content).hexdigest() == file["hash"]
            assert file["filename"].split("/")[1].split(".")[0] == file["hash"]
            assert len(content) == file["size"]
    return package


def database_snapshot(engine):
    with engine.connect() as connection:
        return {
            table.name: list(connection.execute(select(table)).mappings())
            for table in metadata.sorted_tables
        }


def test_stream_package_without_staging(tmp_path):
    content = image_bytes()
    digest = hashlib.sha256(content).hexdigest()
    (tmp_path / digest).write_bytes(content)
    package = {
        "format": "image-studio-asset",
        "format_version": 1,
        "exported_at": "synthetic",
        "files": [
            {"hash": digest, "size": len(content), "filename": f"files/{digest}.png"}
        ],
    }
    assert unpack(b"".join(stream_package(tmp_path, package))) == package
    assert [p.name for p in tmp_path.iterdir()] == [digest]


def test_storage_deduplication_and_overlap():
    files = [{"hash": str(i), "size": i * 10} for i in range(1, 5)]
    totals = storage_totals(files, {"1"}, {"1", "2"}, {"1", "2", "3"})
    assert totals == {
        "total": {"bytes": 100, "file_count": 4},
        "uploaded": {"bytes": 10, "file_count": 1},
        "generated": {"bytes": 60, "file_count": 2},
        "placeholder": {"bytes": 30, "file_count": 1},
    }
    assert storage_totals([], set(), set(), set())["total"] == {
        "bytes": 0,
        "file_count": 0,
    }


@pytest.mark.parametrize(
    "format,ext", [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")]
)
def test_asset_package_all_images_including_deleted_rejected(client, format, ext):
    c, engine, root = client
    asset = new_asset(c, type_tag="object", description="Synthetic description")
    asset = upload(c, asset["id"], (image_bytes(format), "synthetic.bin")).json
    c.patch(
        f"/api/assets/{asset['id']}/images/{asset['images'][0]['id']}",
        json={"rejected": True},
    )
    c.delete(f"/api/assets/{asset['id']}")
    before = database_snapshot(engine)
    timestamps = {p.name: p.stat().st_mtime_ns for p in root.iterdir()}
    response = c.get(f"/api/assets/{asset['id']}/export.zip")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    package = unpack(response.data)
    assert package["format"] == "image-studio-asset"
    assert package["asset"]["description"] == "Synthetic description"
    assert package["asset"]["deleted_at"]
    assert package["asset"]["images"][0]["rejected"]
    assert package["files"][0]["filename"].endswith("." + ext)
    assert database_snapshot(engine) == before
    assert {p.name: p.stat().st_mtime_ns for p in root.iterdir()} == timestamps
    assert c.get("/api/assets/99999/export.zip").status_code == 404


def test_complete_package_hidden_frames_retries_pinned_assets(generation_client):
    c, engine, root = generation_client
    project, comp, asset = setup_composition(c)
    path = f"/api/compositions/{comp['id']}"
    frames = [comp["variants"][0], c.post(path + "/variants", json={}).json]
    done = []
    for frame in frames:
        run = c.post(
            f"/api/variants/{frame['id']}/runs",
            json={
                "models": [{"model": "placeholder-a", "count": 1}],
                "prompt": "Edited synthetic",
            },
        ).json
        done.append(complete(c, root, run["generations"][0]))
    c.put(
        f"/api/variants/{frames[0]['id']}/final",
        json={"generation_id": done[0]["id"], "output": 0},
    )
    failed = c.post(
        f"/api/variants/{frames[0]['id']}/generations",
        json={"model": "placeholder-fails", "count": 1},
    ).json
    failed = complete(c, root, failed, fail=True)
    retry = c.post(f"/api/generations/{failed['id']}/retry").json
    pinned = new_asset(c)
    pinned = upload(c, pinned["id"], (image_bytes("PNG", "yellow"), "pinned.png")).json
    extra = c.post(
        f"/api/variants/{frames[1]['id']}/runs",
        json={
            "models": [{"model": "placeholder-a", "count": 1}],
            "prompt": "Pinned",
            "references": [
                {
                    "hash": pinned["images"][0]["hash"],
                    "asset_id": pinned["id"],
                    "role": "Outside pack",
                }
            ],
        },
    ).json["generations"][0]
    extra = complete(c, root, extra)
    replacement = upload(c, asset["id"], (image_bytes("PNG", "green"), "new.png")).json[
        "images"
    ][-1]
    c.patch(
        f"/api/assets/{asset['id']}/images/{replacement['id']}", json={"approved": True}
    )
    c.patch(
        f"/api/assets/{asset['id']}/images/{asset['images'][0]['id']}",
        json={"approved": False},
    )
    c.delete(f"/api/assets/{asset['id']}")
    c.delete(path + f"/assets/{asset['id']}")
    c.delete(f"/api/variants/{frames[0]['id']}")
    before = database_snapshot(engine)
    files_before = {p.name: p.stat().st_mtime_ns for p in root.iterdir()}
    package = unpack(c.get(path + "/export.zip").data)
    assert (
        package["format"] == "image-studio-composition"
        and package["project"] == project
    )
    assert [f["id"] for f in package["frames"]] == [f["id"] for f in frames]
    assert [f["deleted"] for f in package["frames"]] == [True, False]
    assert package["frames"][0]["final"]["hash"] == done[0]["outputs"][0]
    exported = [
        g for f in package["frames"] for run in f["runs"] for g in run["generations"]
    ]
    assert {g["id"]: g for g in exported} == {
        g["id"]: g for g in [*done, failed, retry, extra]
    }
    assert package["asset_pack"][0]["asset"]["deleted_at"]
    assert not package["asset_pack"][0]["active"]
    assert package["referenced_assets"][0]["id"] == pinned["id"]
    expected = (
        {r["hash"] for g in exported for r in g["references"]}
        | {h for g in exported for h in g["outputs"]}
        | {asset["images"][1]["hash"]}
    )
    assert {f["hash"] for f in package["files"]} == expected
    assert replacement["hash"] not in expected
    assert database_snapshot(engine) == before
    assert {p.name: p.stat().st_mtime_ns for p in root.iterdir()} == files_before
    assert c.get("/api/compositions/99999/export.zip").status_code == 404


def test_storage_route_generated_placeholder_shared_and_hidden(generation_client):
    c, engine, root = generation_client
    assert c.get("/api/storage").json["total"] == {"bytes": 0, "file_count": 0}
    _, comp, asset = setup_composition(c)
    done = []
    for _ in range(2):
        row = c.post(
            f"/api/variants/{comp['variants'][0]['id']}/generations",
            json={"model": "placeholder-a", "count": 1},
        ).json
        done.append(complete(c, root, row))
    with engine.begin() as connection:
        connection.execute(
            update(generations)
            .where(generations.c.id == done[0]["id"])
            .values(placeholder=False)
        )
        files = list(connection.execute(select(stored_files)).mappings())
    c.post(f"/api/assets/{asset['id']}/duplicate")
    c.delete(f"/api/assets/{asset['id']}")
    before = database_snapshot(engine)
    totals = c.get("/api/storage").json
    assert totals["total"] == {"bytes": sum(f["size"] for f in files), "file_count": 4}
    assert totals["uploaded"]["file_count"] == 2
    for key, row in zip(["generated", "placeholder"], done, strict=True):
        assert totals[key] == {
            "bytes": next(f["size"] for f in files if f["hash"] == row["outputs"][0]),
            "file_count": 1,
        }
    assert database_snapshot(engine) == before

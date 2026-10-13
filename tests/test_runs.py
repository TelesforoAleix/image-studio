"""Run input validation and real-Postgres comparison/reuse invariants."""

import os
import uuid
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text, update
from sqlalchemy.schema import CreateSchema, DropSchema
from test_api import client as postgres_client
from test_api import new_asset, upload
from test_files import image_bytes
from test_generation_api import generation_client as runs_client
from test_generation_api import setup_composition
from werkzeug.exceptions import BadRequest

from image_studio.database import database_engine
from image_studio.generation_api import run_choices
from image_studio.image_client import ImageClient
from image_studio.jobs import process_generation
from image_studio.schema import generations

client = postgres_client
generation_client = runs_client


@pytest.mark.parametrize(
    "choices",
    [
        None,
        [],
        [{}],
        [{"model": "a", "count": True}],
        [{"model": "a", "count": 5}],
        [{"model": 1, "count": 1}],
        [{"model": "a", "count": 1}] * 2,
        [{"model": str(i), "count": 1} for i in range(4)],
    ],
)
def test_invalid_run_choices(choices):
    with pytest.raises(BadRequest):
        run_choices({"models": choices})


def test_valid_choices_are_ordered():
    choices = [{"model": "b", "count": 4}, {"model": "a", "count": 1}]
    assert run_choices({"models": choices}) == choices


def complete(c, root, row, fail=False):
    process_generation(
        row["id"],
        c.application.config["DATABASE_URL"],
        root=root,
        client=ImageClient(
            "http://endpoint/v1",
            transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        )
        if fail
        else c.application.extensions["image_client"],
    )
    return c.get(f"/api/generations/{row['id']}").json


def test_compare_retry_final_and_pinned_reuse(generation_client):
    c, engine, root = generation_client
    _, comp, asset = setup_composition(c)
    variant = comp["variants"][0]["id"]
    path = f"/api/variants/{variant}/runs"
    result = c.post(
        path,
        json={
            "models": [
                {"model": "placeholder-a", "count": 2},
                {"model": "placeholder-b", "count": 1},
                {"model": "placeholder-fails", "count": 1},
            ],
            "prompt": "Edited synthetic",
        },
    )
    assert result.status_code == 201, result.json
    run = result.json
    assert len(run["generations"]) == 3
    assert all(
        g["run_id"] == run["run_id"]
        and g["prompt"] == run["prompt"]
        and g["references"] == run["references"]
        and g["edited"]
        and g["placeholder"]
        for g in run["generations"]
    )
    a, b, failed = [
        complete(c, root, g, g["model"] == "placeholder-fails")
        for g in run["generations"]
    ]
    assert [a["state"], b["state"], failed["state"]] == ["done", "done", "failed"]
    retry = c.post(f"/api/generations/{failed['id']}/retry")
    assert retry.status_code == 201
    assert (
        retry.json["retry_of"] == failed["id"] and retry.json["run_id"] == run["run_id"]
    )
    for key in ("model", "model_info", "prompt", "references", "count", "placeholder"):
        assert retry.json[key] == failed[key]
    assert c.get(f"/api/generations/{failed['id']}").json == failed
    assert c.post(f"/api/generations/{a['id']}/retry").status_code == 409
    final_path = f"/api/variants/{variant}/final"
    assert c.get(final_path).json is None
    for g in (b, a):
        choice = c.put(final_path, json={"generation_id": g["id"], "output": 0})
        assert choice.status_code == 200 and choice.json["hash"] == g["outputs"][0]
    assert c.get(final_path).json["generation_id"] == a["id"]
    assert c.get(f"/api/generations/{b['id']}").json == b
    assert c.delete(final_path).json is None
    for value in (
        {"generation_id": failed["id"], "output": 0},
        {"generation_id": a["id"], "output": 2},
        {"generation_id": a["id"], "output": -1},
        {"generation_id": True, "output": 0},
    ):
        assert c.put(final_path, json=value).status_code == 400
    _, other, _ = setup_composition(c)
    assert (
        c.put(
            f"/api/variants/{other['variants'][0]['id']}/final",
            json={"generation_id": a["id"], "output": 0},
        ).status_code
        == 400
    )
    before = c.get(path).json
    c.patch(
        f"/api/assets/{asset['id']}", json={"name": "Changed", "description": "Changed"}
    )
    c.patch(
        f"/api/assets/{asset['id']}/images/{asset['images'][0]['id']}",
        json={"approved": False},
    )
    c.delete(f"/api/assets/{asset['id']}")
    refs = [
        {**r, "media_type": "untrusted", "asset_name": "untrusted"}
        for r in run["references"]
    ]
    reused = c.post(
        path,
        json={
            "models": [{"model": "placeholder-b", "count": 1}],
            "prompt": "Changed draft",
            "references": refs,
        },
    )
    assert reused.status_code == 201, reused.json
    assert reused.json["edited"] and reused.json["prompt"] == "Changed draft"
    assert reused.json["references"][0]["hash"] == run["references"][0]["hash"]
    assert reused.json["references"][0]["media_type"] == "image/png"
    assert reused.json["references"][0]["asset_name"] == "Changed"
    assert c.get(path).json[1:] == before
    assert c.get(f"/api/generations/{a['id']}").json == a
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(generations)) == 5


def test_run_refusals_and_transaction_rollback(generation_client, monkeypatch):
    c, engine, _ = generation_client
    project, comp, asset = setup_composition(c)
    path = f"/api/variants/{comp['variants'][0]['id']}/runs"
    ref = c.get(f"/api/variants/{comp['variants'][0]['id']}/preview").json[
        "references"
    ][0]
    choices = [
        {"model": "placeholder-b", "count": 1},
        {"model": "placeholder-a", "count": 1},
    ]
    refusal = c.post(
        path, json={"models": choices, "prompt": "Synthetic", "references": [ref] * 5}
    )
    assert refusal.status_code == 400
    assert all(s in refusal.json["error"] for s in ("placeholder-a", "5", "4"))
    other = c.post("/api/projects", json={"name": "Other"}).json
    private = new_asset(c, project_id=other["id"])
    private = upload(
        c, private["id"], (image_bytes("PNG", "green"), "private.png")
    ).json
    forbidden = [
        {**ref, "hash": "0" * 64},
        {**ref, "hash": private["images"][0]["hash"], "asset_id": private["id"]},
        {**ref, "asset_id": True},
        {**ref, "asset_id": 2**50},
        {**ref, "role": None},
    ]
    for refs in [[r] for r in forbidden] + [None, {}]:
        assert (
            c.post(
                path,
                json={"models": choices, "prompt": "Synthetic", "references": refs},
            ).status_code
            == 400
        )
    for payload in (
        {"models": choices, "prompt": ""},
        {"models": [{"model": "unknown", "count": 1}]},
        {"models": []},
        {"models": choices, "unexpected": True},
    ):
        assert c.post(path, json=payload).status_code == 400
    calls = []
    from image_studio.generation_api import defer

    def broken(connection, identifier):
        calls.append(identifier)
        defer(connection, identifier)
        if len(calls) == 2:
            raise RuntimeError("Synthetic failure")

    monkeypatch.setattr("image_studio.generation_api.defer", broken)
    with pytest.raises(RuntimeError):
        c.post(path, json={"models": choices})
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(generations)) == 0
        assert connection.scalar(text("SELECT count(*) FROM procrastinate_jobs")) == 0


def test_retry_uses_original_model_metadata(generation_client):
    c, engine, _ = generation_client
    _, comp, _ = setup_composition(c)
    row = c.post(
        f"/api/variants/{comp['variants'][0]['id']}/generations",
        json={"model": "placeholder-a", "count": 1},
    ).json
    with engine.begin() as connection:
        connection.execute(
            update(generations)
            .where(generations.c.id == row["id"])
            .values(state="failed")
        )
    # Retry needs no endpoint discovery, including when a model disappears.
    c.application.extensions["image_client"] = None
    retry = c.post(f"/api/generations/{row['id']}/retry")
    assert retry.status_code == 201 and retry.json["model_info"] == row["model_info"]


def test_s4_generation_backfill_twice(monkeypatch):
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
        command.upgrade(config, "0002")
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO assets (name) VALUES ('Synthetic legacy')")
            )
            for _ in range(2):
                connection.execute(
                    text("""INSERT INTO generations
                    (kind, asset_id, model, model_info, prompt, assembled_prompt,
                     edited, "references", placeholder, count)
                    VALUES ('asset_reference', 1, 'synthetic', '{}', 'Synthetic',
                            'Synthetic', false, '[]', true, 1)""")
                )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            first = list(connection.execute(select(generations)).mappings())
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert list(connection.execute(select(generations)).mappings()) == first
        assert len({r["run_id"] for r in first}) == 2
        assert all(r["retry_of"] is None and r["prompt"] == "Synthetic" for r in first)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()

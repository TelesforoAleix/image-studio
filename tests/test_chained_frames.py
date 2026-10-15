"""Continuity and transactional sequence advancement on disposable Postgres."""

import io
import json
from zipfile import ZipFile

import pytest
from sqlalchemy import select, update
from test_api import client as postgres_client
from test_generation_api import generation_client as sequence_client
from test_generation_api import setup_composition
from test_runs import complete
from werkzeug.exceptions import BadRequest

from image_studio.generation_api import finished_run
from image_studio.requests import render, snapshot
from image_studio.schema import frame_sequences, generations

client = postgres_client
generation_client = sequence_client


def storyboard(c):
    _, comp, _ = setup_composition(c)
    frames = [comp["variants"][0]] + [
        c.post(f"/api/compositions/{comp['id']}/variants", json={}).json
        for _ in range(2)
    ]
    return comp, frames


def start(c, comp, frames, mode="full", model="placeholder-a", **extra):
    response = c.post(
        f"/api/compositions/{comp['id']}/frame-sequences",
        json={
            "mode": mode,
            "frame_id": frames[0]["id"],
            "models": [{"model": model, "count": 2}],
            **extra,
        },
    )
    assert response.status_code == 201, response.json
    return response.json


def state(c, comp):
    return c.get(f"/api/compositions/{comp['id']}/frame-sequences").json[0]


def current(c, sequence):
    entry = sequence["frames"][sequence["current_frame"]]
    return next(
        r
        for r in c.get(f"/api/variants/{entry['frame_id']}/runs").json
        if r["run_id"] == entry["run_id"]
    )["generations"]


def test_previous_is_first_in_both_renderers_and_counts_as_object():
    previous = {"role": "previous frame", "type": "other", "asset_name": "previous"}
    person = {"role": "subject", "type": "person", "asset_name": "Person"}
    for family in ("openai", "gemini"):
        prompt, refs = render(
            "Synthetic", [previous, person], {"prompt_family": family}
        )
        assert refs == [previous, person]
        assert "Image 1: the previous frame" in prompt
        info = {"prompt_family": family, "max_references": 1}
        with pytest.raises(BadRequest, match="selected 2 references"):
            snapshot("synthetic", "Synthetic", refs, info, 1)
        info.update(max_references=2, reference_slots={"object": 0})
        with pytest.raises(BadRequest, match="selected 1 object"):
            snapshot("synthetic", "Synthetic", refs, info, 1)


def test_full_sequence_single_runs_final_and_pinned_reuse(generation_client):
    c, engine, root = generation_client
    comp, frames = storyboard(c)
    seq = start(c, comp, frames)
    assert [f["state"] for f in seq["frames"]] == ["running", "waiting", "waiting"]
    assert c.get(f"/api/variants/{frames[1]['id']}/runs").json == []
    a = complete(c, root, current(c, seq)[0])
    seq = state(c, comp)
    b = current(c, seq)[0]
    assert b["references"][0]["hash"] == a["outputs"][0]
    assert b["references"][0]["source"] == "first output"
    assert b["references"][0]["frame_id"] == frames[0]["id"]
    assert b["references"][0]["role"] == "previous frame"
    assert b["settings"] == a["settings"]
    assert c.get(f"/api/variants/{frames[2]['id']}/runs").json == []
    b = complete(c, root, b)
    seq = state(c, comp)
    third = current(c, seq)[0]
    assert third["references"][0]["hash"] == b["outputs"][0]
    complete(c, root, third)
    assert state(c, comp)["state"] == "done"
    # A selected final wins over first output on subsequent queueing.
    assert (
        c.put(
            f"/api/variants/{frames[1]['id']}/final",
            json={"generation_id": b["id"], "output": 1},
        ).status_code
        == 200
    )
    path = f"/api/variants/{frames[2]['id']}"
    run = c.post(
        path + "/runs", json={"models": [{"model": "placeholder-a", "count": 1}]}
    ).json
    ref = run["references"][0]
    assert ref["source"] == "final" and ref["hash"] == b["outputs"][1]
    c.delete(f"/api/variants/{frames[1]['id']}/final")
    c.patch(path, json={"use_previous_frame": False})
    unchained = c.post(
        path + "/runs", json={"models": [{"model": "placeholder-a", "count": 1}]}
    ).json
    assert all(r["role"] != "previous frame" for r in unchained["references"])
    reused = c.post(
        path + "/runs",
        json={
            "models": [{"model": "placeholder-a", "count": 1}],
            "references": run["references"],
            "content": "Synthetic pinned",
        },
    )
    assert reused.status_code == 201, reused.json
    assert reused.json["references"][0] == ref
    # Refusal includes the continuity reference and is atomic.
    too_many = c.post(
        path + "/runs",
        json={
            "models": [{"model": "placeholder-a", "count": 1}],
            "references": [ref] + run["references"][1:] * 4,
            "content": "Synthetic",
        },
    )
    assert too_many.status_code == 400 and "5 references" in too_many.json["error"]
    with engine.connect() as connection:
        assert finished_run(connection, frames[0]["id"])["id"] == a["id"]
        assert len(list(connection.execute(select(frame_sequences)))) == 1
    with ZipFile(
        io.BytesIO(c.get(f"/api/compositions/{comp['id']}/export.zip").data)
    ) as archive:
        package = json.loads(archive.read("manifest.json"))
        assert package["format_version"] == 6 and len(package["sequences"]) == 1
        assert ref["hash"] in {f["hash"] for f in package["files"]}


def test_failure_rest_stop_and_duplicate_completion(generation_client):
    c, engine, root = generation_client
    comp, frames = storyboard(c)
    seq = start(c, comp, frames)
    # Another start is refused under the composition lock.
    assert (
        c.post(
            f"/api/compositions/{comp['id']}/frame-sequences",
            json={"mode": "full", "models": [{"model": "placeholder-a", "count": 1}]},
        ).status_code
        == 409
    )
    first = complete(c, root, current(c, seq)[0])
    seq = state(c, comp)
    second = current(c, seq)[0]
    complete(c, root, second, fail=True)
    seq = state(c, comp)
    assert seq["state"] == "failed" and seq["error"]
    assert seq["frames"][1]["state"] == "failed"
    assert c.get(f"/api/variants/{frames[2]['id']}/runs").json == []
    resumed = start(c, comp, frames, "rest", frame_id=frames[1]["id"])
    assert [f["frame_id"] for f in resumed["frames"]] == [f["id"] for f in frames[1:]]
    assert (
        c.post(f"/api/frame-sequences/{resumed['id']}/stop").json["state"] == "stopping"
    )
    done = complete(c, root, current(c, resumed)[0])
    seq = state(c, comp)
    assert seq["state"] == "stopped"
    assert [f["state"] for f in seq["frames"]] == ["done", "stopped"]
    assert c.get(f"/api/variants/{frames[2]['id']}/runs").json == []
    assert complete(c, root, done) == done
    assert complete(c, root, first) == first
    assert state(c, comp) == seq
    # Next is a sequence of exactly one frame.
    next_seq = start(c, comp, frames, "next")
    assert (
        len(next_seq["frames"]) == 1
        and next_seq["frames"][0]["frame_id"] == frames[1]["id"]
    )
    complete(c, root, current(c, next_seq)[0])
    assert state(c, comp)["state"] == "done"
    # A latest partial run never supplies its output.
    with engine.begin() as connection:
        connection.execute(
            update(generations)
            .where(generations.c.id == second["id"])
            .values(state="waiting")
        )
        assert finished_run(connection, frames[1]["id"])["state"] == "done"


def test_sequences_wait_for_all_models_and_limit_failure(generation_client):
    c, _, root = generation_client
    comp, frames = storyboard(c)
    seq = start(
        c,
        comp,
        frames,
        models=[
            {"model": "placeholder-a", "count": 1},
            {"model": "placeholder-b", "count": 1},
        ],
    )
    a, b = current(c, seq)
    complete(c, root, a)
    assert state(c, comp)["current_frame"] == 0
    complete(c, root, b)
    assert state(c, comp)["current_frame"] == 1
    c.post(f"/api/frame-sequences/{seq['id']}/stop")
    for g in current(c, state(c, comp)):
        complete(c, root, g)
    assert state(c, comp)["state"] == "stopped"
    # Four asset refs are valid on frame 1, but continuity is a fifth on frame 2.
    pack = c.get(f"/api/variants/{frames[0]['id']}/preview").json["references"]
    from test_api import upload
    from test_files import image_bytes

    asset_id = pack[0]["asset_id"]
    images = upload(
        c,
        asset_id,
        (image_bytes("PNG", "green"), "a.png"),
        (image_bytes("PNG", "yellow"), "b.png"),
        (image_bytes("PNG", "purple"), "c.png"),
    ).json["images"]
    for image in images[2:]:
        c.patch(f"/api/assets/{asset_id}/images/{image['id']}", json={"approved": True})
    seq = start(c, comp, frames)
    complete(c, root, current(c, seq)[0])
    seq = state(c, comp)
    assert seq["state"] == "failed" and "5 references" in seq["error"]
    assert seq["frames"][1]["run_id"] is None


def test_u4_upgrade_twice_and_downgrade(client):
    from alembic import command
    from alembic.config import Config

    from scripts.check_chained_migration import main

    command.downgrade(Config("alembic.ini"), "0011")
    main()

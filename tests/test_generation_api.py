"""Postgres integration: queue transactions, snapshots, candidates and retries."""

import io
import os
import uuid
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.schema import CreateSchema, DropSchema
from test_api import client as postgres_client
from test_api import new_asset, upload
from test_files import image_bytes

from image_studio.database import database_engine
from image_studio.image_client import EndpointUnavailable, ImageClient
from image_studio.jobs import ensure_job_schema, process_generation
from image_studio.placeholder import MODELS, draw_placeholder
from image_studio.schema import composition_assets, compositions, generations

client = postgres_client


@pytest.fixture
def generation_client(client):
    c, engine, root = client
    ensure_job_schema(c.application.config["DATABASE_URL"])
    ensure_job_schema(c.application.config["DATABASE_URL"])

    def handler(request):
        if request.url.path.endswith("model/info"):
            return httpx.Response(200, json={"data": MODELS})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": draw_placeholder(
                            MODELS[0]["model_info"], "Synthetic", 0
                        )
                    }
                ]
            },
        )

    c.application.extensions["image_client"] = ImageClient(
        "http://endpoint/v1", transport=httpx.MockTransport(handler)
    )
    return c, engine, root


def setup_composition(c):
    project = c.post(
        "/api/projects", json={"name": "Synthetic project", "instructions": "Direction"}
    ).json
    comp = c.post(
        f"/api/projects/{project['id']}/compositions",
        json={"name": "Synthetic scene", "scene": "Scene"},
    ).json
    asset = new_asset(c, description="Description")
    asset = upload(
        c,
        asset["id"],
        (image_bytes(), "one.png"),
        (image_bytes("PNG", "blue"), "two.png"),
    ).json
    for image in asset["images"]:
        c.patch(
            f"/api/assets/{asset['id']}/images/{image['id']}", json={"approved": True}
        )
    c.put(
        f"/api/compositions/{comp['id']}/assets/{asset['id']}",
        json={"role": "Subject", "deselected_images": [asset["images"][1]["id"]]},
    )
    return project, comp, asset


def test_composition_snapshot_and_completed_outputs(generation_client):
    c, engine, root = generation_client
    project, comp, asset = setup_composition(c)
    variant = comp["variants"][0]
    assert variant["name"] == "Frame 1"
    c.patch(
        f"/api/variants/{variant['id']}", json={"instructions": "Frame instruction"}
    )
    preview = c.get(f"/api/variants/{variant['id']}/preview").json
    assert [r["hash"] for r in preview["references"]] == [asset["images"][0]["hash"]]
    assert preview["prompt"].endswith("Frame instruction")
    queued = c.post(
        f"/api/variants/{variant['id']}/generations",
        json={
            "model": "placeholder-a",
            "count": 2,
            "prompt": "Edited synthetic prompt",
        },
    )
    assert queued.status_code == 201, queued.json
    record = queued.json
    assert record["edited"] and record["placeholder"] and record["state"] == "waiting"
    with engine.connect() as connection:
        jobs = (
            connection.execute(
                text("SELECT task_name, lock, args FROM procrastinate_jobs")
            )
            .mappings()
            .all()
        )
        assert len(jobs) == 1 and jobs[0]["args"] == {"generation_id": record["id"]}
        assert jobs[0]["lock"] == "studio-image-endpoint"
    process_generation(
        record["id"],
        c.application.config["DATABASE_URL"],
        client=c.application.extensions["image_client"],
        root=root,
    )
    done = c.get(f"/api/generations/{record['id']}").json
    assert done["state"] == "done" and len(done["outputs"]) == 2
    assert done["started_at"] and done["finished_at"]
    for hash in done["outputs"]:
        assert c.get("/api/files/" + hash).status_code == 200
    c.patch(
        f"/api/assets/{asset['id']}", json={"name": "Changed", "description": "Changed"}
    )
    c.patch(
        f"/api/assets/{asset['id']}/images/{asset['images'][0]['id']}",
        json={"approved": False},
    )
    new = upload(c, asset["id"], (image_bytes("PNG", "green"), "new.png")).json[
        "images"
    ][-1]
    c.patch(f"/api/assets/{asset['id']}/images/{new['id']}", json={"approved": True})
    assert c.get(f"/api/generations/{record['id']}").json == done
    updated = c.get(f"/api/variants/{variant['id']}/preview").json
    assert [r["hash"] for r in updated["references"]] == [new["hash"]]
    assert "Changed" in updated["prompt"]
    assert c.get(f"/api/variants/{variant['id']}/generations").json == [done]
    assert len(c.get(f"/api/projects/{project['id']}/compositions").json) == 1
    c.delete(f"/api/compositions/{comp['id']}")
    assert c.get(f"/api/projects/{project['id']}/compositions").json == []
    assert c.get(f"/api/generations/{record['id']}").json == done
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(compositions)) == 1


def test_reference_candidates_approve_reject_and_keep_files(generation_client):
    c, _, root = generation_client
    asset = new_asset(c)
    asset = upload(c, asset["id"], (image_bytes(), "one.png")).json
    result = c.post(
        f"/api/assets/{asset['id']}/generations",
        json={"model": "placeholder-a", "count": 2},
    )
    assert result.status_code == 201
    process_generation(
        result.json["id"],
        c.application.config["DATABASE_URL"],
        client=c.application.extensions["image_client"],
        root=root,
    )
    images = c.get(f"/api/assets/{asset['id']}").json["images"]
    first, second = [i for i in images if i["source"] == "generated"]
    assert not first["approved"] and not first["rejected"]
    c.patch(f"/api/assets/{asset['id']}/images/{first['id']}", json={"approved": True})
    c.patch(f"/api/assets/{asset['id']}/images/{second['id']}", json={"rejected": True})
    assert len(c.get(f"/api/assets/{asset['id']}").json["images"]) == 2
    all_images = c.get(f"/api/assets/{asset['id']}?include_rejected=true").json[
        "images"
    ]
    assert all_images[-1]["rejected"] and not all_images[-1]["approved"]
    assert c.get("/api/files/" + second["hash"]).status_code == 200
    assert (
        len(c.get(f"/api/assets/{asset['id']}/reference-preview").json["references"])
        == 1
    )
    duplicate = c.post(f"/api/assets/{asset['id']}/duplicate").json
    assert c.get(f"/api/assets/{duplicate['id']}?include_rejected=true").json["images"][
        -1
    ]["rejected"]


def test_endpoint_outage_cached_models_retry_and_terminal_failure(generation_client):
    c, _, root = generation_client
    asset = new_asset(c)
    assert len(c.get("/api/models").json) == 3

    def unavailable(request):
        raise httpx.ConnectError("offline", request=request)

    outage = ImageClient(
        "http://endpoint/v1", transport=httpx.MockTransport(unavailable)
    )
    original = c.application.extensions["image_client"]
    c.application.extensions["image_client"] = outage
    record = c.post(
        f"/api/assets/{asset['id']}/generations",
        json={"model": "placeholder-a", "count": 1},
    ).json
    with pytest.raises(EndpointUnavailable):
        process_generation(
            record["id"], c.application.config["DATABASE_URL"], client=outage, root=root
        )
    waiting = c.get(f"/api/generations/{record['id']}").json
    assert (
        waiting["state"] == "waiting" and waiting["attempts"] == 1 and waiting["error"]
    )
    process_generation(
        record["id"], c.application.config["DATABASE_URL"], client=original, root=root
    )
    assert c.get(f"/api/generations/{record['id']}").json["state"] == "done"
    c.application.extensions["image_client"] = original
    fail = c.post(
        f"/api/assets/{asset['id']}/generations",
        json={"model": "placeholder-fails", "count": 1},
    ).json
    process_generation(
        fail["id"],
        c.application.config["DATABASE_URL"],
        root=root,
        client=ImageClient(
            "http://endpoint/v1",
            transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        ),
    )
    failure = c.get(f"/api/generations/{fail['id']}").json
    assert failure["state"] == "failed" and "500" in failure["error"]


@pytest.mark.parametrize(
    "body",
    [{"model": "placeholder-a", "count": n} for n in [0, 5, True, "1"]]
    + [
        {"model": "unknown", "count": 1},
        {"model": "placeholder-a", "count": 1, "prompt": ""},
    ],
)
def test_queue_validation_creates_no_row(generation_client, body):
    c, engine, _ = generation_client
    asset = new_asset(c)
    assert (
        c.post(f"/api/assets/{asset['id']}/generations", json=body).status_code == 400
    )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(generations)) == 0
        assert connection.scalar(text("SELECT count(*) FROM procrastinate_jobs")) == 0


def test_reference_limit_and_visibility(generation_client):
    c, engine, _ = generation_client
    _, comp, asset = setup_composition(c)
    for i in range(5):
        output = io.BytesIO()
        from PIL import Image

        Image.new("RGB", (8 + i, 8), "red").save(output, format="PNG")
        upload(c, asset["id"], (output.getvalue(), "synthetic.png"))
    refusal = c.post(
        f"/api/assets/{asset['id']}/generations",
        json={"model": "placeholder-a", "count": 1},
    )
    assert (
        refusal.status_code == 400
        and "7 references" in refusal.json["error"]
        and "4" in refusal.json["error"]
    )
    other = c.post("/api/projects", json={"name": "Other"}).json
    private = new_asset(c, project_id=other["id"])
    assert (
        c.put(
            f"/api/compositions/{comp['id']}/assets/{private['id']}",
            json={"role": "Subject"},
        ).status_code
        == 400
    )
    assert (
        c.put(
            f"/api/compositions/{comp['id']}/assets/{asset['id']}",
            json={"role": "Subject", "deselected_images": [999]},
        ).status_code
        == 400
    )
    c.delete(f"/api/compositions/{comp['id']}/assets/{asset['id']}")
    with engine.connect() as connection:
        assert (
            connection.scalar(select(func.count()).select_from(composition_assets)) == 1
        )
    assert c.get(f"/api/compositions/{comp['id']}").json["assets"] == []


def test_atomic_queue_rollback(generation_client, monkeypatch):
    c, engine, _ = generation_client
    asset = new_asset(c)

    def failing_defer(*args):
        raise RuntimeError("Synthetic deferral failure")

    monkeypatch.setattr("image_studio.generation_api.defer", failing_defer)
    with pytest.raises(RuntimeError):
        c.post(
            f"/api/assets/{asset['id']}/generations",
            json={"model": "placeholder-a", "count": 1},
        )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(generations)) == 0


def test_upgrade_existing_0001_data_twice(monkeypatch):
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
        command.upgrade(config, "0001")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO projects (name, instructions) "
                    "VALUES ('Synthetic legacy', 'Legacy instruction')"
                )
            )
            connection.execute(
                text("INSERT INTO assets (name) VALUES ('Synthetic legacy asset')")
            )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT instructions FROM projects"))
                == "Legacy instruction"
            )
            assert (
                connection.scalar(text("SELECT name FROM assets"))
                == "Synthetic legacy asset"
            )
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def test_partial_outputs_survive_retry(generation_client):
    c, _, root = generation_client
    asset = new_asset(c)
    queued = c.post(
        f"/api/assets/{asset['id']}/generations",
        json={"model": "placeholder-a", "count": 2},
    ).json
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 2:
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": draw_placeholder(
                            MODELS[0]["model_info"], "Synthetic", 0
                        )
                    }
                ]
            },
        )

    endpoint = ImageClient("http://endpoint/v1", transport=httpx.MockTransport(handler))
    with pytest.raises(EndpointUnavailable):
        process_generation(
            queued["id"],
            c.application.config["DATABASE_URL"],
            client=endpoint,
            root=root,
        )
    waiting = c.get(f"/api/generations/{queued['id']}").json
    assert waiting["state"] == "waiting" and len(waiting["outputs"]) == 1
    process_generation(
        queued["id"], c.application.config["DATABASE_URL"], client=endpoint, root=root
    )
    done = c.get(f"/api/generations/{queued['id']}").json
    assert done["state"] == "done" and done["outputs"][0] == waiting["outputs"][0]
    assert len(calls) == 3 and len(done["outputs"]) == 2

"""Feedback validation, retained rows and the full journey on real Postgres."""

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from test_api import client as postgres_client
from test_api import upload as upload_images
from test_files import image_bytes
from test_generation_api import generation_client as request_client
from werkzeug.exceptions import BadRequest

from image_studio.feedback import model_tallies, validate_feedback
from image_studio.image_client import ImageClient
from image_studio.jobs import process_generation
from image_studio.placeholder import create_placeholder
from image_studio.schema import output_feedback
from scripts.check_feedback import prove
from scripts.check_feedback_migration import main as migration_proof

client = postgres_client
generation_client = request_client


@pytest.mark.parametrize(
    "value",
    [
        {"verdict": "bad"},
        {"verdict": []},
        {"note": None},
        {"asset_ratings": {}},
        {"asset_ratings": [None]},
        {"asset_ratings": [{"asset_id": True, "rating": "kept"}]},
        {"asset_ratings": [{"asset_id": 2, "rating": "kept"}]},
        {"asset_ratings": [{"asset_id": 1, "rating": "bad"}]},
        {"asset_ratings": [{"asset_id": 1, "rating": "kept", "extra": 1}]},
        {"asset_ratings": [{"asset_id": 1, "rating": "kept"}] * 2},
    ],
)
def test_invalid_feedback(value):
    with pytest.raises(BadRequest):
        validate_feedback(value, [{"asset_id": 1}])


def test_optional_detail_and_tally():
    value = {"verdict": None, "asset_ratings": [], "note": ""}
    assert validate_feedback(value, []) == value
    assert model_tallies(
        [
            {"model": "a", "feedback": [{"verdict": "good"}, {"verdict": None}]},
            {"model": "a", "feedback": [{"verdict": "not_good"}]},
            {"model": "b", "feedback": []},
        ]
    ) == {"a": {"rated": 2, "good": 1}, "b": {"rated": 0, "good": 0}}


def test_r3_upgrade_twice_and_downgrade(client):
    _, engine, _ = client
    command.downgrade(Config("alembic.ini"), "0008")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO assets (name) VALUES ('Synthetic R3')"))
        connection.execute(
            text("""INSERT INTO generations
            (kind, asset_id, run_id, model, model_info, prompt, assembled_prompt,
             edited, "references", placeholder, count, state, outputs)
            VALUES ('asset_reference', 1, 'synthetic-r3', 'placeholder-a', '{}',
                    'Synthetic', 'Synthetic', false, '[]', true, 1, 'done',
                    '["synthetic-output"]')""")
        )
    migration_proof()


def test_full_feedback_journey_and_retention(generation_client, monkeypatch):
    c, engine, root = generation_client
    simulator = create_placeholder().test_client()
    monkeypatch.setattr("image_studio.placeholder.time.sleep", lambda _: None)

    def handler(call):
        response = simulator.open(
            call.url.path,
            method=call.method,
            data=call.content,
            content_type=call.headers.get("content-type"),
        )
        return httpx.Response(response.status_code, json=response.json)

    endpoint = ImageClient("http://endpoint/v1", transport=httpx.MockTransport(handler))
    c.application.extensions["image_client"] = endpoint

    def request(path, method="GET", body=None, status=200):
        response = c.open(path, method=method, json=body)
        assert response.status_code == status, response.data
        return response.json if response.is_json else response.data

    def wait(identifier):
        process_generation(
            identifier, c.application.config["DATABASE_URL"], client=endpoint, root=root
        )
        row = request(f"/api/generations/{identifier}")
        assert row["state"] == "done", row
        return row

    def upload(identifier, colors):
        response = upload_images(
            c,
            identifier,
            *[(image_bytes("PNG", color), "synthetic.png") for color in colors],
        )
        assert response.status_code == 201
        return response.json

    a, b, frame = prove(request, wait, upload)
    path = f"/api/generations/{a['id']}/outputs/0/feedback"
    for payload in [{}, [], {"extra": 1}, {"verdict": "bad"}, {"note": None}]:
        request(path, "PATCH", payload, status=400)
    request(
        f"/api/generations/{a['id']}/outputs/2/feedback",
        "PATCH",
        {"verdict": "good"},
        status=404,
    )
    request(
        "/api/generations/99999/outputs/0/feedback",
        "PATCH",
        {"verdict": "good"},
        status=404,
    )
    # Snapshot validation survives later library edits/deletion.
    asset_id = a["references"][0]["asset_id"]
    request(f"/api/assets/{asset_id}", "DELETE")
    request(
        path, "PATCH", {"asset_ratings": [{"asset_id": asset_id, "rating": "lost"}]}
    )
    request(path, "PATCH", {"verdict": None, "asset_ratings": [], "note": ""})
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(output_feedback)) == 3
    assert request(f"/api/generations/{b['id']}")["feedback"][1]["updated_at"]
    # Final remains independent; feedback does not select a final.
    assert request(f"/api/variants/{frame}/final") is None

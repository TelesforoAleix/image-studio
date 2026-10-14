"""Deterministic profiles and full placeholder request proof on real Postgres."""

from copy import deepcopy

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from test_api import client as postgres_client
from test_api import upload as upload_images
from test_files import image_bytes
from test_generation_api import generation_client as request_client
from werkzeug.exceptions import BadRequest

from image_studio.image_client import ImageClient
from image_studio.jobs import process_generation
from image_studio.placeholder import MODELS, create_placeholder
from image_studio.requests import render, settings, snapshot
from scripts.check_model_requests import prove
from scripts.check_model_requests_migration import main as migration_proof

client = postgres_client
generation_client = request_client


def test_renderer_families_and_reference_numbers():
    refs = [
        {"asset_name": name, "role": "Subject", "type": kind}
        for name, kind in [
            ("Ink", "style"),
            ("Coat", "garment_product"),
            ("Person", "person"),
        ]
    ]
    content = (
        "Scene\nStyle: Ink (reference images 1)\n"
        "Coat (reference images 2)\nPerson (reference images 3)"
    )
    openai, ordered = render(content, refs, {"prompt_family": "openai"})
    assert (
        ordered == refs
        and openai.startswith("Image 1: Ink")
        and openai.endswith(content)
    )
    gemini, ordered = render(content, refs, {"prompt_family": "gemini"})
    assert ordered == [refs[2], refs[0], refs[1]]
    assert gemini.startswith("Scene\nStyle: Ink (reference images 2)")
    assert "Person (reference images 1)" in gemini
    assert gemini.endswith("Image 3: Coat, Subject, garment_product")
    for family in [None, "unknown"]:
        assert render(content, refs, {"prompt_family": family}) == (content, refs)


@pytest.mark.parametrize(
    "index,quality,expected",
    [
        (
            0,
            "high",
            {
                "size": "1536x1024",
                "quality": "high",
                "background": "auto",
                "output_compression": "100",
            },
        ),
        (
            3,
            "2K",
            {
                "providerOptions": {
                    "google": {"imageConfig": {"aspectRatio": "3:2", "imageSize": "2K"}}
                },
                "reasoning_effort": "medium",
            },
        ),
        (5, "1536x1024", {"size": "1536x1024"}),
    ],
)
def test_fields_prices_and_defaults(index, quality, expected):
    info = MODELS[index]["model_info"]
    row = snapshot(
        "Synthetic",
        "Scene",
        [{"asset_name": "Person", "role": "Subject", "type": "person"}],
        info,
        2,
        {"quality": quality},
        ratio="3:2",
    )
    for key, value in expected.items():
        assert row["request_fields"][key] == value
    assert "seed" not in row["request_fields"]
    assert settings(info, {}, "3:2")["quality"] == (
        "low" if index == 0 else "1K" if index == 3 else "1536x1024"
    )
    assert row["estimated_cost"] == (
        0.104 if index == 0 else 0.1 if index == 3 else 0.08
    )


@pytest.mark.parametrize(
    "supplied",
    [
        [],
        False,
        {"quality": "auto"},
        {"quality": []},
        {"format": []},
        {"advanced": {"seed": 1}},
        {"advanced": {"output_compression": True}},
        {"advanced": {"output_compression": 101}},
        {"advanced": {"background": "invalid"}},
    ],
)
def test_invalid_settings(supplied):
    with pytest.raises(BadRequest):
        settings(MODELS[0]["model_info"], supplied)


def test_limits_and_multipart_dotted_fields():
    info = deepcopy(MODELS[3]["model_info"])
    refs = [{"asset_name": "Person", "role": "Subject", "type": "person"}] * 5
    with pytest.raises(
        BadRequest, match="Synthetic: selected 5 character; accepts at most 4"
    ):
        snapshot("Synthetic", "Scene", refs, info, 1)
    info["max_prompt_chars"] = 2
    with pytest.raises(BadRequest, match="prompt characters"):
        snapshot("Synthetic", "Scene", [], info, 1)
    info = deepcopy(MODELS[0]["model_info"])
    info["aspect_ratios"]["field"] = "nested.size"
    with pytest.raises(BadRequest, match="plain names"):
        snapshot("Synthetic", "Scene", [], info, 1)


def test_r2_migration_twice_with_runs_and_downgrade(client):
    _, engine, _ = client
    command.downgrade(Config("alembic.ini"), "0007")
    with engine.begin() as c:
        identifier = c.scalar(
            text("INSERT INTO assets (name) VALUES ('Synthetic R2') RETURNING id")
        )
        c.execute(
            text(
                "INSERT INTO generations (kind, asset_id, run_id, model, "
                'model_info, prompt, assembled_prompt, edited, "references", '
                "placeholder, count) VALUES ('asset_reference', :id, "
                "'synthetic-r2', 'placeholder-a', '{}', 'Synthetic', "
                "'Synthetic', false, '[]', true, 1)"
            ),
            {"id": identifier},
        )
    migration_proof()


def test_full_request_proof_postgres(generation_client, monkeypatch):
    c, _, root = generation_client
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

    prove(request, wait, upload)

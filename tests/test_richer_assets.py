"""Preservation, ordered originals, style overrides and unchanged historical data."""

import httpx
import pytest
from alembic import command
from alembic.config import Config
from test_api import client as postgres_client
from test_api import upload as upload_images
from test_files import image_bytes
from test_generation_api import generation_client as richer_client

from image_studio.image_client import ImageClient
from image_studio.jobs import process_generation
from image_studio.placeholder import MODELS, draw_placeholder
from image_studio.prompting import assemble, chosen_images, reference_view
from scripts.check_richer_assets import prove
from scripts.check_richer_migration import main as migration_proof

client = postgres_client
generation_client = richer_client


def test_r1_migration_twice_and_downgrade(client):
    command.downgrade(Config("alembic.ini"), "0006")
    migration_proof()


def test_richer_journey_against_postgres(generation_client):
    c, _, root = generation_client

    def request(path, method="GET", body=None, status=200):
        response = c.open(path, method=method, json=body)
        assert response.status_code == status, response.data
        return response.json if response.is_json else response.data

    def generated_response(request):
        output = draw_placeholder(MODELS[0]["model_info"], "Synthetic", 0)
        if request.url.path.endswith("chat/completions"):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "images": [
                                    {
                                        "image_url": {
                                            "url": "data:image/png;base64," + output
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"data": [{"b64_json": output}]})

    endpoint = ImageClient(
        "http://endpoint/v1", transport=httpx.MockTransport(generated_response)
    )

    def wait(identifier):
        process_generation(
            identifier,
            c.application.config["DATABASE_URL"],
            client=endpoint,
            root=root,
        )
        row = request(f"/api/generations/{identifier}")
        assert row["state"] == "done"
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


def test_prompt_and_original_order():
    asset = {
        "id": 1,
        "name": "Synthetic",
        "type": "person",
        "type_tag": "label",
        "description": "Description",
        "preserve": "face shape",
    }
    images = [
        {
            "id": i,
            "hash": str(i),
            "source": "uploaded",
            "approved": i == 2,
            "rejected": False,
            "media_type": "image/png",
        }
        for i in range(1, 4)
    ]
    images[2]["rejected"] = True
    selection = {
        "role": "Subject",
        "deselected_images": [],
        "selected_originals": [1, 3],
    }
    frame = {"instructions": "Action", "selected_originals": [1]}
    assert [i["id"] for i in chosen_images(images, selection, frame)] == [2, 1]
    preview = assemble(None, {"scene": "Scene"}, [(asset, selection, images)], frame)
    assert (
        preview["prompt"] == "Scene\n\nSubject: Synthetic (Person) — Description\n"
        "Keep: face shape (reference images 1, 2)\n\nAction"
    )
    assert [r["hash"] for r in preview["references"]] == ["2", "1"]
    assert all(
        r["type"] == "person" and r["preserve"] == "face shape"
        for r in preview["references"]
    )
    selection["deselected_images"] = [1]
    assert [i["id"] for i in chosen_images(images, selection, frame)] == [2]
    view = reference_view(asset, images)
    assert "Person" in view["prompt"] and "keep: face shape" in view["prompt"]
    assert [r["hash"] for r in view["references"]] == ["1", "2", "3"]


@pytest.mark.parametrize("value", [None, "unknown", [], True])
def test_invalid_type(client, value):
    c, _, _ = client
    assert (
        c.post("/api/assets", json={"name": "Synthetic", "type": value}).status_code
        == 400
    )


@pytest.mark.parametrize("value", [True, -1, "1", [], {}])
def test_invalid_style_id(client, value):
    c, _, _ = client
    assert (
        c.post(
            "/api/projects", json={"name": "Synthetic", "style_asset_id": value}
        ).status_code
        == 400
    )
    assert (
        c.post(
            "/api/compositions",
            json={"name": "Synthetic", "kind": "single", "style_asset_id": value},
        ).status_code
        == 400
    )


def test_type_changes_and_invalid_selections(client):
    c, _, _ = client
    asset = c.post("/api/assets", json={"name": "Synthetic", "type": "person"}).json
    style = c.post(
        "/api/assets", json={"name": "Synthetic style", "type": "style"}
    ).json
    project = c.post(
        "/api/projects", json={"name": "Synthetic", "style_asset_id": style["id"]}
    ).json
    assert (
        c.patch(f"/api/assets/{style['id']}", json={"type": "person"}).status_code
        == 409
    )
    assert (
        c.patch(
            f"/api/projects/{project['id']}", json={"style_asset_id": asset["id"]}
        ).status_code
        == 400
    )
    comp = c.post(
        "/api/compositions", json={"name": "Synthetic", "kind": "single"}
    ).json
    path = f"/api/compositions/{comp['id']}"
    assert (
        c.put(path + f"/assets/{asset['id']}", json={"role": "Subject"}).status_code
        == 200
    )
    assert (
        c.patch(f"/api/assets/{asset['id']}", json={"type": "style"}).status_code == 409
    )
    frame = comp["variants"][0]["id"]
    for value in [None, True, [999], [True], [1, 1]]:
        assert (
            c.patch(
                f"/api/variants/{frame}", json={"selected_originals": value}
            ).status_code
            == 400
        )
        assert (
            c.put(
                path + f"/assets/{asset['id']}",
                json={"role": "Subject", "selected_originals": value},
            ).status_code
            == 400
        )
        assert c.patch(path, json={"style_deselected_images": value}).status_code == 400

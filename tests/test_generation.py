"""Synthetic unit tests for the endpoint contract and fixed templates."""

import base64
import io
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from werkzeug.exceptions import ServiceUnavailable

from image_studio.image_client import EndpointUnavailable, ImageClient, ModelFailure
from image_studio.jobs import ServiceRetry
from image_studio.placeholder import MODELS, create_placeholder, draw_placeholder
from image_studio.prompting import assemble, reference_view


def test_prompt_order_empty_parts_and_reference_views():
    asset = {
        "id": 1,
        "name": "Synthetic",
        "description": "Description",
        "type_tag": "object",
    }
    images = [
        {
            "id": i,
            "hash": str(i),
            "approved": True,
            "rejected": False,
            "media_type": "image/png",
            "source": "uploaded",
        }
        for i in range(1, 4)
    ]
    images[2]["source"] = "generated"
    preview = assemble(
        {"instructions": "Project"},
        {"scene": "Scene"},
        [(asset, {"role": "Subject", "deselected_images": [2]}, images)],
        {"instructions": "Variant"},
    )
    assert preview["prompt"] == (
        "Project\n\nScene\n\nSubject: Synthetic — Description "
        "(reference images 1, 2)\n\nVariant"
    )
    assert [r["hash"] for r in preview["references"]] == ["1", "3"]
    assert preview["references"][0]["role"] == "Subject"
    assert (
        assemble({"instructions": ""}, {"scene": ""}, [], {"instructions": "Frame"})[
            "prompt"
        ]
        == "Frame"
    )
    view = reference_view(asset, images)
    assert [r["hash"] for r in view["references"]] == ["1", "2"]
    assert "plain light background" in view["prompt"].lower()
    assert "whole item in view" in view["prompt"]


def test_placeholder_contract(monkeypatch):
    waits = []
    monkeypatch.setattr("image_studio.placeholder.time.sleep", waits.append)
    client = create_placeholder().test_client()
    assert client.get("/v1/model/info").json == {"data": MODELS}
    fields = {
        "model": "placeholder-a",
        "prompt": "Synthetic first line\nSecond",
        "n": 1,
        "response_format": "b64_json",
    }
    first = client.post("/v1/images/generations", json=fields)
    assert first.status_code == 200
    data = base64.b64decode(first.json["data"][0]["b64_json"])
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "PNG" and image.size == (960, 640)
    assert draw_placeholder(
        MODELS[0]["model_info"], "Synthetic", 0
    ) != draw_placeholder(MODELS[0]["model_info"], "Synthetic", 0)
    second = client.post(
        "/v1/images/edits",
        data={
            **fields,
            "model": "placeholder-b",
            "image[]": (io.BytesIO(data), "synthetic.png"),
        },
    )
    assert second.status_code == 200
    assert waits == [3, 8]
    failure = client.post(
        "/v1/images/generations", json={**fields, "model": "placeholder-fails"}
    )
    assert failure.status_code == 500 and "deliberately" in failure.json["error"]
    assert (
        client.post(
            "/v1/images/generations", json={**fields, "model": "unknown"}
        ).status_code
        == 400
    )


def test_client_filters_models_and_never_returns_key():
    def handler(request):
        assert request.url.path == "/v1/model/info"
        assert request.headers["Authorization"] == "Bearer synthetic-key"
        return httpx.Response(
            200,
            json={
                "data": [
                    *MODELS,
                    {"model_name": "ignored", "model_info": {"mode": "chat"}},
                ]
            },
        )

    client = ImageClient(
        "http://endpoint/v1/", "synthetic-key", httpx.MockTransport(handler)
    )
    assert client.models() == MODELS


@pytest.mark.parametrize("status", [400, 401, 500])
def test_model_discovery_errors_are_safe(status):
    client = ImageClient(
        "http://endpoint/v1",
        "synthetic-key",
        httpx.MockTransport(lambda _: httpx.Response(status, text="synthetic-key")),
    )
    with pytest.raises(ServiceUnavailable) as error:
        client.models()
    assert "synthetic-key" not in str(error.value)


@pytest.mark.parametrize("references", [False, True])
def test_client_image_route_and_n_one(tmp_path, references):
    data = base64.b64decode(draw_placeholder(MODELS[0]["model_info"], "Synthetic", 1))
    (tmp_path / "hash").write_bytes(data)

    def handler(request):
        assert request.url.path == (
            "/v1/images/edits" if references else "/v1/images/generations"
        )
        if references:
            assert b'name="image[]"' in request.content
            assert data in request.content and b"\r\n1\r\n" in request.content
        else:
            import json

            assert json.loads(request.content)["n"] == 1
        return httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(data).decode()}]}
        )

    client = ImageClient("http://endpoint/v1", transport=httpx.MockTransport(handler))
    generation = {
        "model": "synthetic",
        "prompt": "Synthetic",
        "placeholder": False,
        "references": [{"hash": "hash", "media_type": "image/png"}]
        if references
        else [],
    }
    result, file = client.generate(generation, tmp_path)
    assert result == data and file["media_type"] == "image/png"


@pytest.mark.parametrize(
    "status,model,placeholder,error_type",
    [
        (500, "synthetic", False, EndpointUnavailable),
        (503, "synthetic", False, EndpointUnavailable),
        (500, "placeholder-fails", True, ModelFailure),
        (400, "synthetic", False, ModelFailure),
    ],
)
def test_worker_error_classification(tmp_path, status, model, placeholder, error_type):
    client = ImageClient(
        "http://endpoint/v1",
        transport=httpx.MockTransport(lambda _: httpx.Response(status)),
    )
    with pytest.raises(error_type):
        client.generate(
            {
                "model": model,
                "placeholder": placeholder,
                "prompt": "Synthetic",
                "references": [],
            },
            tmp_path,
        )


def test_transport_retry_and_growing_capped_delay(tmp_path):
    def handler(request):
        raise httpx.ConnectError("synthetic-key", request=request)

    client = ImageClient("http://endpoint/v1", transport=httpx.MockTransport(handler))
    with pytest.raises(EndpointUnavailable) as error:
        client.generate(
            {"model": "synthetic", "prompt": "Synthetic", "references": []}, tmp_path
        )
    assert "synthetic-key" not in str(error.value)
    delays = [
        ServiceRetry()
        .get_retry_decision(exception=error.value, job=SimpleNamespace(attempts=i))
        .retry_at
        for i in range(7)
    ]
    now = datetime.now(UTC)
    assert 9 < (delays[0] - now).total_seconds() <= 10
    assert delays[1] > delays[0] and delays[5] <= delays[6]
    assert (
        ServiceRetry().get_retry_decision(
            exception=ModelFailure(), job=SimpleNamespace(attempts=0)
        )
        is None
    )


@pytest.mark.parametrize(
    "response", [{}, {"data": []}, {"data": [{"b64_json": "bad"}]}]
)
def test_invalid_image_responses_are_terminal(tmp_path, response):
    client = ImageClient(
        "http://endpoint/v1",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response)),
    )
    with pytest.raises(ModelFailure):
        client.generate(
            {"model": "synthetic", "prompt": "Synthetic", "references": []}, tmp_path
        )

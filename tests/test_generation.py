"""Synthetic unit tests for the endpoint contract and fixed templates."""

import base64
import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from werkzeug.exceptions import ServiceUnavailable

from image_studio.image_client import (
    EndpointUnavailable,
    ImageClient,
    ModelFailure,
    ServiceFailure,
)
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
        "Project\n\nScene\n\nSubject: Synthetic (Other) — Description "
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
        (500, "synthetic", False, ServiceFailure),
        (503, "synthetic", False, ServiceFailure),
        (500, "placeholder-fails", True, ServiceFailure),
        (400, "synthetic", False, ModelFailure),
        (401, "synthetic", False, ModelFailure),
        (402, "synthetic", False, ModelFailure),
        (429, "synthetic", False, ModelFailure),
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


@pytest.mark.parametrize(
    "endpoint,limit,size,expected",
    [
        ("chat/completions", 512, (1200, 800), (512, 341)),
        ("chat/completions", 512, (800, 1200), (341, 512)),
        ("chat/completions", 512, (160, 120), (160, 120)),
        ("images/edits", 512, (1200, 800), (512, 341)),
        ("images/edits", None, (3000, 1500), (2048, 1024)),
    ],
)
def test_resized_ordered_request_shapes(
    tmp_path, endpoint, limit, size, expected, monkeypatch
):
    monkeypatch.setattr("image_studio.placeholder.time.sleep", lambda _: None)
    placeholder = create_placeholder().test_client()
    originals = []
    refs = []
    for i, color in enumerate(("red", "blue", "green")):
        output = io.BytesIO()
        Image.new("RGB", size, color).save(output, format="PNG")
        data = output.getvalue()
        (tmp_path / str(i)).write_bytes(data)
        originals.append(data)
        refs.append({"hash": str(i), "media_type": "image/png"})

    def handler(request):
        assert request.extensions["timeout"]["read"] == 360
        if endpoint == "chat/completions":
            body = json.loads(request.content)
            assert "n" not in body and body["modalities"] == ["text", "image"]
            (message,) = body["messages"]
            assert message["role"] == "user"
            assert message["content"][0] == {"type": "text", "text": "Synthetic"}
            assert len(message["content"]) == 4
        response = placeholder.post(
            request.url.path,
            data=request.content,
            content_type=request.headers["content-type"],
        )
        return httpx.Response(response.status_code, json=response.json)

    info = {
        "endpoint": endpoint,
        "response": "message_images" if endpoint == "chat/completions" else "b64_json",
    }
    if limit is not None:
        info["reference_max_side"] = limit
    client = ImageClient("http://endpoint/v1", transport=httpx.MockTransport(handler))
    result, _ = client.generate(
        {
            "model": "placeholder-chat"
            if endpoint == "chat/completions"
            else "placeholder-a",
            "model_info": info,
            "prompt": "Synthetic",
            "references": refs,
        },
        tmp_path,
    )
    with Image.open(io.BytesIO(result)) as image:
        assert json.loads(image.info["received_sizes"]) == [list(expected)] * 3
    assert [(tmp_path / str(i)).read_bytes() for i in range(3)] == originals
    assert len(list(tmp_path.iterdir())) == 3


@pytest.mark.parametrize(
    "exception,expected",
    [
        (httpx.ConnectError, EndpointUnavailable),  # refused or DNS
        (httpx.ConnectTimeout, ServiceFailure),
        (httpx.ReadTimeout, ServiceFailure),
        (httpx.WriteTimeout, ServiceFailure),
        (httpx.ReadError, ServiceFailure),
    ],
)
def test_transport_failure_classes(tmp_path, exception, expected):
    def handler(request):
        raise exception("synthetic-key", request=request)

    client = ImageClient("http://endpoint/v1", transport=httpx.MockTransport(handler))
    with pytest.raises(expected) as caught:
        client.generate(
            {"model": "synthetic", "prompt": "Synthetic", "references": []}, tmp_path
        )
    assert type(caught.value) is expected and "synthetic-key" not in str(caught.value)


def test_budget_message_and_url_refusal(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(402, text="synthetic-key")

    client = ImageClient("http://endpoint/v1", transport=httpx.MockTransport(handler))
    generation = {"model": "synthetic", "prompt": "Synthetic", "references": []}
    with pytest.raises(
        ModelFailure, match=r"Monthly image budget reached — resets on the 1st \(UTC\)"
    ):
        client.generate(generation, tmp_path)
    with pytest.raises(ModelFailure, match="URL responses are unsupported"):
        client.generate({**generation, "model_info": {"response": "url"}}, tmp_path)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"images": []}}]},
        {
            "choices": [
                {
                    "message": {
                        "images": [
                            {"image_url": {"url": "https://arbitrary.invalid/image"}}
                        ]
                    }
                }
            ]
        },
    ],
)
def test_invalid_chat_response(tmp_path, data):
    client = ImageClient(
        "http://endpoint/v1",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)),
    )
    with pytest.raises(ModelFailure):
        client.generate(
            {
                "model": "synthetic",
                "model_info": {
                    "endpoint": "chat/completions",
                    "response": "message_images",
                },
                "prompt": "Synthetic",
                "references": [],
            },
            tmp_path,
        )


def test_unknown_profile_fields_preserved():
    models = [
        {
            **MODELS[0],
            "model_info": {
                **MODELS[0]["model_info"],
                "future_capability": {"synthetic": 1},
                "price_per_image": {"small": 0.01, "large": 0.1},
                "price_per_reference": 0.002,
                "price_estimated": True,
            },
        }
    ]
    client = ImageClient(
        "http://endpoint/v1",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": models})
        ),
    )
    assert client.models() == models


def test_chat_without_references_decodes_only_first_output(tmp_path):
    data = base64.b64decode(draw_placeholder(MODELS[0]["model_info"], "Synthetic", 0))

    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body == {
            "model": "synthetic",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Synthetic"}]}
            ],
            "modalities": ["text", "image"],
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "images": [
                                {
                                    "image_url": {
                                        "url": "data:image/png;base64,"
                                        + base64.b64encode(data).decode()
                                    }
                                },
                                {"image_url": {"url": "invalid second output"}},
                            ]
                        }
                    }
                ]
            },
        )

    client = ImageClient("http://endpoint/v1", transport=httpx.MockTransport(handler))
    result, _ = client.generate(
        {
            "model": "synthetic",
            "prompt": "Synthetic",
            "references": [],
            "model_info": {
                "endpoint": "chat/completions",
                "response": "message_images",
            },
        },
        tmp_path,
    )
    assert result == data

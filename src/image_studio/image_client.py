"""Environment-configured image contract; never expose endpoint credentials."""

import base64
import binascii
import io

import httpx
from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import ServiceUnavailable

from image_studio.files import decode_upload


class EndpointUnavailable(Exception):
    """Connection failure: no request reached the service; retry without limit."""


class ServiceFailure(EndpointUnavailable):
    """Timeout or uncertain service failure: at most three attempts."""


class ModelFailure(Exception):
    """A terminal model or malformed-response failure."""


class ImageClient:
    def __init__(self, base, key="", transport=None):
        self.base = base.rstrip("/")
        self.key = key
        self.transport = transport

    def client(self, timeout):
        if not self.base:
            raise EndpointUnavailable("Image endpoint is not configured")
        return httpx.Client(
            headers={"Authorization": f"Bearer {self.key}"} if self.key else {},
            timeout=httpx.Timeout(timeout, connect=5),
            transport=self.transport,
        )

    def models(self):
        try:
            with self.client(10) as client:
                response = client.get(self.base + "/model/info")
                response.raise_for_status()
                models = response.json()["data"]
                result = []
                for model in models:
                    info = model.get("model_info", {})
                    if info.get("mode") != "image_generation":
                        continue
                    if (
                        not isinstance(model.get("model_name"), str)
                        or not isinstance(info.get("display_name"), str)
                        or type(info.get("paid")) is not bool
                        or type(info.get("placeholder")) is not bool
                        or type(info.get("max_references")) is not int
                        or info["max_references"] < 0
                        or not isinstance(info.get("licence"), str)
                        or info.get("endpoint")
                        not in ("images/edits", "chat/completions")
                        or info.get("response")
                        not in ("b64_json", "url", "message_images")
                        or not isinstance(info.get("price_per_image"), dict)
                        or not info["price_per_image"]
                        or any(
                            type(price) not in (int, float) or price < 0
                            for price in info["price_per_image"].values()
                        )
                        or type(info.get("reference_max_side", 2048)) is not int
                        or info.get("reference_max_side", 2048) < 1
                        or (
                            info.get("seconds_per_image") is not None
                            and (
                                type(info["seconds_per_image"]) not in (int, float)
                                or info["seconds_per_image"] < 0
                            )
                        )
                    ):
                        raise ValueError("Invalid model metadata")
                    result.append(model)
                return result
        except (
            httpx.HTTPError,
            EndpointUnavailable,
            ValueError,
            KeyError,
            TypeError,
        ) as error:
            raise ServiceUnavailable(
                "Image model list temporarily unavailable"
            ) from error

    def generate(self, generation, root):
        info = generation.get("model_info", {})
        endpoint = info.get("endpoint", "images/edits")
        response_kind = info.get("response", "b64_json")
        if response_kind == "url":
            raise ModelFailure(
                "Image URL responses are unsupported; no URL was fetched"
            )
        if (endpoint, response_kind) not in {
            ("images/edits", "b64_json"),
            ("chat/completions", "message_images"),
        }:
            raise ModelFailure("Unsupported image endpoint or response profile")
        fields = {
            "model": generation["model"],
            "prompt": generation["prompt"],
            "n": 1,
            "response_format": "b64_json",
        }
        try:
            refs = [
                prepare_reference(root, ref, info) for ref in generation["references"]
            ]
            with self.client(360) as client:
                if endpoint == "chat/completions":
                    content = [{"type": "text", "text": generation["prompt"]}]
                    content.extend(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media};base64,"
                                + base64.b64encode(data).decode()
                            },
                        }
                        for data, media, size in refs
                    )
                    response = client.post(
                        self.base + "/chat/completions",
                        json={
                            "model": generation["model"],
                            "messages": [{"role": "user", "content": content}],
                            "modalities": ["text", "image"],
                        },
                    )
                elif refs:
                    response = client.post(
                        self.base + "/images/edits",
                        data={k: str(v) for k, v in fields.items()},
                        files=[
                            ("image[]", (ref["hash"], data, media))
                            for ref, (data, media, size) in zip(
                                generation["references"], refs, strict=True
                            )
                        ],
                    )
                else:
                    response = client.post(
                        self.base + "/images/generations", json=fields
                    )
                if response.status_code >= 500:
                    raise ServiceFailure(
                        f"Image request failed (HTTP {response.status_code})"
                    )
                if response.status_code == 402:
                    raise ModelFailure(
                        "Monthly image budget reached — resets on the 1st (UTC)"
                    )
                if response.is_error:
                    raise ModelFailure(
                        f"Image request failed (HTTP {response.status_code})"
                    )
                if response_kind == "message_images":
                    output = response.json()["choices"][0]["message"]["images"][0]
                    decoded = decode_data_url(output["image_url"]["url"])
                else:
                    data = response.json()["data"]
                    if len(data) != 1:
                        raise ValueError("Expected exactly one output")
                    decoded = base64.b64decode(data[0]["b64_json"], validate=True)
                return decode_upload(
                    FileStorage(stream=io.BytesIO(decoded), filename="generated image")
                )
        except httpx.ConnectError as error:
            raise EndpointUnavailable(
                "Image service connection failed; will retry"
            ) from error
        except httpx.TransportError as error:
            # Only connection refusal/DNS is certainly safe; other transport failures
            # (including timeouts) may follow a paid request reaching the endpoint.
            raise ServiceFailure(
                "Image request failed (timeout or transport failure)"
            ) from error
        except (ValueError, KeyError, TypeError, IndexError, binascii.Error) as error:
            raise ModelFailure(
                "Image service returned an invalid image response"
            ) from error


def decode_data_url(value):
    if not isinstance(value, str):
        raise ValueError("Expected an image data URL")
    header, data = value.split(",", 1)
    if not header.startswith("data:image/") or not header.endswith(";base64"):
        raise ValueError("Expected a base64 image data URL")
    return base64.b64decode(data, validate=True)


def prepare_reference(root, ref, info):
    """Ephemeral copy only; the original bytes and hash never change."""
    limit = info.get("reference_max_side", 2048)
    data = (root / ref["hash"]).read_bytes()
    with Image.open(io.BytesIO(data)) as image:
        media = ref["media_type"]
        if max(image.size) > limit:
            image.thumbnail((limit, limit), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            # PNG preserves colour and alpha without another lossy encoding.
            if image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                image = image.convert("RGB")
            image.save(output, format="PNG")
            data, media = output.getvalue(), "image/png"
        return data, media, list(image.size)

"""Environment-configured image contract; never expose endpoint credentials."""

import base64
import binascii
import io
from contextlib import ExitStack

import httpx
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import ServiceUnavailable

from image_studio.files import decode_upload


class EndpointUnavailable(Exception):
    """Transport or service failure, safe to retry later."""


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
        fields = {
            "model": generation["model"],
            "prompt": generation["prompt"],
            "n": 1,
            "response_format": "b64_json",
        }
        try:
            with ExitStack() as stack:
                client = stack.enter_context(self.client(1800))
                refs = generation["references"]
                if refs:
                    files = [
                        (
                            "image[]",
                            (
                                ref["hash"],
                                stack.enter_context((root / ref["hash"]).open("rb")),
                                ref["media_type"],
                            ),
                        )
                        for ref in refs
                    ]
                    response = client.post(
                        self.base + "/images/edits",
                        data={k: str(v) for k, v in fields.items()},
                        files=files,
                    )
                else:
                    response = client.post(
                        self.base + "/images/generations", json=fields
                    )
                if response.status_code >= 500:
                    # The deliberate simulator failure is terminal.
                    if (
                        generation["placeholder"]
                        and generation["model"] == "placeholder-fails"
                    ):
                        raise ModelFailure(
                            "HTTP 500: Placeholder model deliberately failed"
                        )
                    raise EndpointUnavailable(
                        f"Image service returned HTTP {response.status_code}"
                    )
                if response.is_error:
                    raise ModelFailure(
                        f"Image request failed (HTTP {response.status_code})"
                    )
                data = response.json()["data"]
                if len(data) != 1:
                    raise ValueError("Expected exactly one output")
                decoded = base64.b64decode(data[0]["b64_json"], validate=True)
                return decode_upload(
                    FileStorage(stream=io.BytesIO(decoded), filename="generated image")
                )
        except httpx.TransportError as error:
            raise EndpointUnavailable(
                "Image service did not answer; will retry"
            ) from error
        except (ValueError, KeyError, TypeError, binascii.Error) as error:
            raise ModelFailure(
                "Image service returned an invalid image response"
            ) from error

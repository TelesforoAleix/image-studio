"""Internal, deliberately marked image contract simulator; draws only at runtime."""

import base64
import io
import json
import time
import uuid

from flask import Flask, jsonify, request
from PIL import Image, ImageDraw, ImageFont

MODELS = [
    {
        "model_name": "placeholder-a",
        "model_info": {
            "mode": "image_generation",
            "display_name": "Placeholder A — not a real model",
            "paid": False,
            "max_references": 4,
            "seconds_per_image": 3,
            "placeholder": True,
        },
    },
    {
        "model_name": "placeholder-b",
        "model_info": {
            "mode": "image_generation",
            "display_name": "Placeholder B — not a real model",
            "paid": True,
            "max_references": 10,
            "seconds_per_image": 8,
            "placeholder": True,
        },
    },
    {
        "model_name": "placeholder-fails",
        "model_info": {
            "mode": "image_generation",
            "display_name": "Placeholder — always fails",
            "paid": False,
            "max_references": 10,
            "seconds_per_image": None,
            "placeholder": True,
        },
    },
]

MODELS.extend(
    [
        {
            "model_name": "placeholder-chat",
            "model_info": {
                "mode": "image_generation",
                "display_name": "Placeholder chat — not a real model",
                "paid": False,
                "max_references": 10,
                "seconds_per_image": 1,
                "placeholder": True,
                "endpoint": "chat/completions",
                "response": "message_images",
                "reference_max_side": 512,
            },
        },
        {
            "model_name": "placeholder-budget",
            "model_info": {
                "mode": "image_generation",
                "display_name": "Placeholder — budget exhausted",
                "paid": True,
                "max_references": 10,
                "seconds_per_image": 0,
                "placeholder": True,
            },
        },
    ]
)
for model in MODELS:
    model["model_info"] = {
        "licence": "MIT (simulator)",
        "endpoint": "images/edits",
        "response": "b64_json",
        "prompt_family": "openai",
        "price_per_image": {"default": 0},
        "price_checked": "2026-10-14",
        **model["model_info"],
    }
MODELS[3]["model_info"]["prompt_family"] = "gemini"


def draw_placeholder(model, prompt, references):
    image = Image.new("RGB", (960, 640), "#f7f8f5")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 30, 930, 610), outline="#40552e", width=3)
    font = ImageFont.load_default(size=24)
    lines = [
        "Generated image — placeholder",
        model["display_name"],
        f"References received: {references}",
        (prompt.splitlines() or [""])[0][:65],
    ]
    for i, line in enumerate(lines):
        draw.text((55, 100 + i * 80), line, fill="#252c29", font=font)
    # Each trial candidate is a distinct immutable file, even with identical inputs.
    output = io.BytesIO()
    from PIL.PngImagePlugin import PngInfo

    metadata = PngInfo()
    metadata.add_text("trial", uuid.uuid4().hex)
    metadata.add_text("received_sizes", json.dumps(references))
    image.save(output, format="PNG", pnginfo=metadata)
    return base64.b64encode(output.getvalue()).decode()


def create_placeholder():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 90 * 1024 * 1024

    @app.get("/v1/model/info")
    def models():
        return jsonify(data=MODELS)

    @app.post("/v1/chat/completions")
    @app.post("/v1/images/generations")
    @app.post("/v1/images/edits")
    def generate():
        body = request.form if request.path.endswith("edits") else request.get_json()
        model = next((m for m in MODELS if m["model_name"] == body.get("model")), None)
        if model is None:
            return jsonify(error="Unknown model"), 400
        if model["model_name"] == "placeholder-fails":
            return jsonify(error="Placeholder model deliberately failed"), 500
        if model["model_name"] == "placeholder-budget":
            return jsonify(error="Monthly image budget exhausted"), 402
        chat = request.path.endswith("chat/completions")
        if chat != (model["model_info"]["endpoint"] == "chat/completions"):
            return jsonify(error="Wrong endpoint"), 400
        if chat:
            if body.get("modalities") != ["text", "image"] or "n" in body:
                return jsonify(error="Supply text/image modalities without n"), 400
            messages = body.get("messages", [])
            if len(messages) != 1 or messages[0].get("role") != "user":
                return jsonify(error="Supply one user message"), 400
            content = messages[0]["content"]
            if not content or content[0].get("type") != "text":
                return jsonify(error="Supply prompt first"), 400
            prompt = content[0].get("text")
            from image_studio.image_client import decode_data_url

            streams = [
                io.BytesIO(decode_data_url(part["image_url"]["url"]))
                for part in content[1:]
                if part["type"] == "image_url"
            ]
            if len(streams) != len(content) - 1:
                return jsonify(error="Supply ordered image_url parts"), 400
        else:
            streams = [file.stream for file in request.files.getlist("image[]")]
            prompt = body.get("prompt")
        sizes = []
        for stream in streams:
            with Image.open(stream) as image:
                sizes.append(list(image.size))
        refs = len(sizes)
        if refs > model["model_info"]["max_references"]:
            return jsonify(error="Too many references"), 400
        if not chat and (
            str(body.get("n")) != "1" or body.get("response_format") != "b64_json"
        ):
            return jsonify(error="Supply n=1 and response_format=b64_json"), 400
        if not isinstance(prompt, str):
            return jsonify(error="Supply prompt as text"), 400
        time.sleep(model["model_info"]["seconds_per_image"])
        output = draw_placeholder(model["model_info"], prompt, sizes)
        if chat:
            return jsonify(
                choices=[
                    {
                        "message": {
                            "images": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": "data:image/png;base64," + output
                                    },
                                }
                            ]
                        }
                    }
                ]
            )
        return jsonify(data=[{"b64_json": output}])

    return app

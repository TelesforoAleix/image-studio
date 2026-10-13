"""Internal, deliberately marked image contract simulator; draws only at runtime."""

import base64
import io
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
    image.save(output, format="PNG", pnginfo=metadata)
    return base64.b64encode(output.getvalue()).decode()


def create_placeholder():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 90 * 1024 * 1024

    @app.get("/v1/model/info")
    def models():
        return jsonify(data=MODELS)

    @app.post("/v1/images/generations")
    @app.post("/v1/images/edits")
    def generate():
        body = request.form if request.path.endswith("edits") else request.get_json()
        model = next((m for m in MODELS if m["model_name"] == body.get("model")), None)
        if model is None:
            return jsonify(error="Unknown model"), 400
        if model["model_name"] == "placeholder-fails":
            return jsonify(error="Placeholder model deliberately failed"), 500
        refs = len(request.files.getlist("image[]"))
        if refs > model["model_info"]["max_references"]:
            return jsonify(error="Too many references"), 400
        if str(body.get("n")) != "1" or body.get("response_format") != "b64_json":
            return jsonify(error="Supply n=1 and response_format=b64_json"), 400
        prompt = body.get("prompt")
        if not isinstance(prompt, str):
            return jsonify(error="Supply prompt as text"), 400
        time.sleep(model["model_info"]["seconds_per_image"])
        return jsonify(
            data=[{"b64_json": draw_placeholder(model["model_info"], prompt, refs)}]
        )

    return app

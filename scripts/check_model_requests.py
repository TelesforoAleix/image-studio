"""Per-model proof; runtime synthetic inputs only, never a hosted model."""

import io
import json

from PIL import Image


def prove(request, wait, upload):
    assets = []
    for kind, name, color in [
        ("person", "Synthetic person", "red"),
        ("garment_product", "Synthetic garment", "blue"),
        ("style", "Synthetic style", "green"),
    ]:
        row = request(
            "/api/assets",
            "POST",
            {
                "name": name,
                "type": kind,
                "description": "Synthetic description",
                "preserve": "Synthetic keep",
            },
            status=201,
        )
        row = upload(row["id"], [color])
        image = row["images"][0]
        row = request(
            f"/api/assets/{row['id']}/images/{image['id']}", "PATCH", {"approved": True}
        )
        assets.append(row)
    person, garment, style = assets
    comp = request(
        "/api/compositions",
        "POST",
        {
            "name": "Synthetic per-model",
            "kind": "single",
            "scene": "Synthetic scene",
            "direction": "Synthetic direction",
            "style_asset_id": style["id"],
        },
        status=201,
    )
    for row in [garment, person]:
        request(
            f"/api/compositions/{comp['id']}/assets/{row['id']}",
            "PUT",
            {"role": "Subject"},
        )
    frame = comp["variants"][0]["id"]
    path = f"/api/variants/{frame}/runs"
    preview = request(f"/api/variants/{frame}/preview")
    choices = [
        {
            "model": "placeholder-a",
            "count": 2,
            "settings": {"quality": "high", "advanced": {"background": "transparent"}},
        },
        {
            "model": "placeholder-chat",
            "count": 1,
            "settings": {"quality": "2K", "advanced": {"reasoning_effort": "high"}},
        },
        {"model": "placeholder-sizes", "count": 1},
    ]
    initial_spend = request("/api/spend")["estimated_spend"]
    rendered = request(
        "/api/render",
        "POST",
        {
            "content": preview["prompt"],
            "references": preview["references"],
            "models": choices,
            "format": "3:2",
        },
    )
    run = request(path, "POST", {"models": choices, "format": "3:2"}, status=201)
    rows = [wait(g["id"]) for g in run["generations"]]
    a, chat, sized = rows
    assert a["rendered_prompt"].startswith("Image 1: Synthetic style")
    assert chat["rendered_prompt"].startswith("Synthetic direction")
    assert (
        chat["rendered_prompt"].endswith("Image 3: Synthetic person, Subject, person")
        is False
    )
    assert [r["type"] for r in chat["references"]] == [
        "person",
        "style",
        "garment_product",
    ]
    assert "reference images 1" in chat["rendered_prompt"]
    for p, g in zip(rendered, rows, strict=True):
        for key in [
            "prompt",
            "rendered_prompt",
            "assembled_prompt",
            "settings",
            "estimated_cost",
            "request_fields",
        ]:
            assert p[key] == g[key], (key, p, g)
    print("PROOF MODEL 1 renderers and ordered references", rows, flush=True)
    received = []
    for g in rows:
        with Image.open(io.BytesIO(request("/api/files/" + g["outputs"][0]))) as image:
            fields = json.loads(image.info["received_fields"])
            assert json.loads(image.info["received_sizes"]) == [
                r["sent_size"] for r in g["references"]
            ]
        assert fields == g["request_fields"], (fields, g["request_fields"])
        received.append(fields)
    assert received[0]["size"] == "1536x1024"
    assert received[1]["providerOptions"]["google"]["imageConfig"] == {
        "aspectRatio": "3:2",
        "imageSize": "2K",
    }
    assert received[2]["size"] == "1536x1024"
    assert (
        received[0]["background"] == "transparent"
        and "background" not in received[1]
        and "background" not in received[2]
    )
    print(
        "PROOF MODEL 2 field shapes, matching sizes, advanced isolation "
        "and exact sent sizes",
        received,
        flush=True,
    )
    assert a["estimated_cost"] == 2 * (0.05 + 3 * 0.002)
    assert chat["estimated_cost"] == 0.05 and sized["estimated_cost"] == 0.04
    total = sum(g["estimated_cost"] for g in rows)
    spend = request("/api/spend")
    assert abs(spend["estimated_spend"] - initial_spend - total) < 1e-8
    print("PROOF MODEL 3 cost formula and UTC monthly sum", total, spend, flush=True)
    before = request(path)
    invalid = request(
        path,
        "POST",
        {
            "models": [
                {
                    "model": "placeholder-a",
                    "count": 1,
                    "settings": {"advanced": {"background": "invalid"}},
                }
            ]
        },
        status=400,
    )
    over_prompt = request(
        path,
        "POST",
        {"models": [{"model": "placeholder-a", "count": 1, "prompt": "x" * 32001}]},
        status=400,
    )
    refs = [preview["references"][-1]] * 5
    over_slot = request(
        path,
        "POST",
        {
            "models": [{"model": "placeholder-chat", "count": 1}],
            "content": "Synthetic",
            "references": refs,
        },
        status=400,
    )
    assert all(
        s in over_slot["error"] for s in ["placeholder-chat", "character", "5", "4"]
    )
    assert all(s in over_prompt["error"] for s in ["placeholder-a", "32001", "32000"])
    assert request(path) == before
    print(
        "PROOF MODEL 4 invalid advanced, prompt and character-slot "
        "refusals; nothing queued",
        invalid,
        over_prompt,
        over_slot,
        flush=True,
    )
    edited_choices = [{**choices[0], "prompt": "Synthetic one-model edit"}, choices[1]]
    edited = request(
        path, "POST", {"models": edited_choices, "format": "3:2"}, status=201
    )
    e, unchanged = edited["generations"]
    assert e["prompt"] == "Synthetic one-model edit" and e["edited"]
    assert unchanged["prompt"] == chat["rendered_prompt"] and not unchanged["edited"]
    print("PROOF MODEL 5 edit is model-local", edited, flush=True)
    reuse = {
        "models": [
            {
                "model": g["model"],
                "count": g["count"],
                "prompt": g["prompt"],
                "settings": g["settings"],
            }
            for g in edited["generations"]
        ],
        "references": edited["references"],
        "content": e["assembled_prompt"],
        "format": e["settings"]["format"],
    }
    reused = request(path, "POST", reuse, status=201)
    for old, new in zip(edited["generations"], reused["generations"], strict=True):
        for key in [
            "prompt",
            "settings",
            "references",
            "request_fields",
            "estimated_cost",
            "rendered_prompt",
        ]:
            assert old[key] == new[key], key
    print(
        "PROOF MODEL 6 Reuse settings restores both prompts, "
        "all settings, references and request fields",
        reused,
        flush=True,
    )
    for g in edited["generations"] + reused["generations"]:
        wait(g["id"])


if __name__ == "__main__":
    from check_generation import wait
    from check_stack import multipart, request, synthetic_png

    def upload(identifier, colors):
        data, media = multipart(
            [(f"synthetic-{i}.png", synthetic_png(c)) for i, c in enumerate(colors)]
        )
        return request(
            f"/api/assets/{identifier}/images", "POST", data, media, status=201
        )

    prove(request, wait, upload)

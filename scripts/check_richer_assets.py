"""Richer assets journey; injected transport also runs against Postgres in tests."""

import io
import json
from zipfile import ZipFile


def prove(request, wait, upload):
    def asset(kind, name, colors, preserve=""):
        row = request(
            "/api/assets",
            "POST",
            {
                "name": name,
                "type": kind,
                "type_tag": "Synthetic label",
                "description": "Synthetic description",
                "preserve": preserve,
            },
            status=201,
        )
        return upload(row["id"], colors)

    def approve(row, image):
        return request(
            f"/api/assets/{row['id']}/images/{image['id']}", "PATCH", {"approved": True}
        )

    def package(path):
        with ZipFile(io.BytesIO(request(path + "/export.zip"))) as archive:
            result = json.loads(archive.read("manifest.json"))
            assert len(archive.namelist()) == 1 + len(result["files"])
            for file in result["files"]:
                assert archive.read(file["filename"]) == request(
                    "/api/files/" + file["hash"]
                )
        print("PROOF RICH package", result, flush=True)
        return result

    person = asset(
        "person", "Synthetic person", ["red", "blue"], "face shape and eyebrows"
    )
    original = person["images"][1]
    person = approve(person, person["images"][0])
    garment = asset(
        "garment_product",
        "Synthetic jacket",
        ["green"],
        "six buttons and lapel proportions",
    )
    garment = approve(garment, garment["images"][0])
    view = request(f"/api/assets/{garment['id']}/reference-preview")
    assert "Garment/Product" in view["prompt"] and "keep: six buttons" in view["prompt"]
    generated = request(
        f"/api/assets/{garment['id']}/generations",
        "POST",
        {"model": "placeholder-a", "count": 1},
        status=201,
    )
    generated = wait(generated["id"])
    garment = request(f"/api/assets/{garment['id']}")
    candidate = next(i for i in garment["images"] if i["source"] == "generated")
    assert candidate["lineage"] == {
        "generation_id": generated["id"],
        "originals": generated["references"],
    }
    assert [r["hash"] for r in candidate["lineage"]["originals"]] == [
        i["hash"] for i in garment["originals"]
    ]
    garment = approve(garment, candidate)
    print(
        "PROOF RICH 1 person two uploads/one reference; "
        "jacket upload/generated reference with ordered lineage",
        person,
        garment,
        flush=True,
    )
    style = asset("style", "Synthetic ink style", ["purple", "orange"], "ink texture")
    for image in style["images"]:
        style = approve(style, image)
    comp = request(
        "/api/compositions",
        "POST",
        {
            "name": "Synthetic richer composition",
            "kind": "storyboard",
            "direction": "Synthetic direction",
            "scene": "Synthetic scene",
            "style_asset_id": style["id"],
        },
        status=201,
    )
    path = f"/api/compositions/{comp['id']}"
    frames = [comp["variants"][0], request(path + "/variants", "POST", {}, status=201)]
    for row in [person, garment]:
        request(path + f"/assets/{row['id']}", "PUT", {"role": "Subject"})
    preview = request(f"/api/variants/{frames[0]['id']}/preview")
    for text in [
        "(Person)",
        "(Garment/Product)",
        "Keep: face shape",
        "Keep: six buttons",
        "Style: Synthetic ink style — Synthetic description",
        "Keep: ink texture",
    ]:
        assert text in preview["prompt"]
    expected = [
        i["hash"] for row in [style, person, garment] for i in row["references"]
    ]
    assert [r["hash"] for r in preview["references"]] == expected
    assert [r["role"] for r in preview["references"][:2]] == ["style reference"] * 2
    assert original["hash"] not in expected
    assert len(expected) == 5
    before = request(f"/api/variants/{frames[0]['id']}/runs")
    refusal = request(
        f"/api/variants/{frames[0]['id']}/runs",
        "POST",
        {"models": [{"model": "placeholder-a", "count": 1}]},
        status=400,
    )
    assert "5 references" in refusal["error"] and "4" in refusal["error"]
    assert request(f"/api/variants/{frames[0]['id']}/runs") == before
    print(
        "PROOF RICH 2 preview types, preservation and style; "
        "default references exclude unticked original; limit counts style (5 vs 4)",
        preview,
        refusal,
        flush=True,
    )
    snapshots = []
    for frame in frames:
        run = request(
            f"/api/variants/{frame['id']}/runs",
            "POST",
            {"models": [{"model": "placeholder-chat", "count": 1}]},
            status=201,
        )
        done = wait(run["generations"][0]["id"])
        assert [r["hash"] for r in done["references"]] == expected[2:3] + expected[
            :2
        ] + expected[3:]
        snapshots.append(done)
    request(
        f"/api/variants/{frames[0]['id']}",
        "PATCH",
        {"selected_originals": [original["id"]]},
    )
    run = request(
        f"/api/variants/{frames[0]['id']}/runs",
        "POST",
        {"models": [{"model": "placeholder-chat", "count": 1}]},
        status=201,
    )
    ticked = wait(run["generations"][0]["id"])
    assert [r["hash"] for r in ticked["references"]] == expected[2:3] + [
        original["hash"]
    ] + expected[:2] + expected[3:]
    assert [
        r["hash"]
        for r in request(f"/api/variants/{frames[1]['id']}/preview")["references"]
    ] == expected
    assert request(f"/api/generations/{snapshots[1]['id']}") == snapshots[1]
    print(
        "PROOF RICH 3 one frame ticks original after person References; "
        "other frame snapshot unchanged",
        ticked,
        snapshots[1],
        flush=True,
    )
    # Pack originals apply to every frame; frame deselection can override them.
    request(
        path + f"/assets/{person['id']}",
        "PUT",
        {"role": "Subject", "selected_originals": [original["id"]]},
    )
    assert len(request(f"/api/variants/{frames[1]['id']}/preview")["references"]) == 6
    request(
        f"/api/variants/{frames[1]['id']}",
        "PATCH",
        {"deselected_images": [original["id"]]},
    )
    assert len(request(f"/api/variants/{frames[1]['id']}/preview")["references"]) == 5
    # Style references can be deselected independently in the pack and frame.
    request(path, "PATCH", {"style_deselected_images": [style["images"][0]["id"]]})
    request(
        f"/api/variants/{frames[0]['id']}",
        "PATCH",
        {"deselected_images": [style["images"][1]["id"]]},
    )
    assert not any(
        r["role"] == "style reference"
        for r in request(f"/api/variants/{frames[0]['id']}/preview")["references"]
    )
    print(
        "PROOF RICH 4 pack originals/frame override; style pack/frame deselections",
        request(path),
        flush=True,
    )
    other = asset("style", "Synthetic project style", ["cyan"])
    other = approve(other, other["images"][0])
    project = request(
        "/api/projects",
        "POST",
        {"name": "Synthetic styled project", "style_asset_id": other["id"]},
        status=201,
    )
    inherited = request(
        f"/api/projects/{project['id']}/compositions",
        "POST",
        {"name": "Synthetic inherited"},
        status=201,
    )
    ipath = f"/api/compositions/{inherited['id']}"
    iframe = inherited["variants"][0]["id"]
    assert inherited["style"]["id"] == other["id"]
    inherited_preview = request(f"/api/variants/{iframe}/preview")
    assert (
        "Synthetic project style" in inherited_preview["prompt"]
        and len(inherited_preview["references"]) == 1
    )
    request(ipath, "PATCH", {"style_asset_id": style["id"]})
    own = request(f"/api/variants/{iframe}/preview")
    assert (
        "Synthetic project style" not in own["prompt"] and len(own["references"]) == 2
    )
    assert all(r["asset_id"] == style["id"] for r in own["references"])
    refusal = request(
        path + f"/assets/{style['id']}", "PUT", {"role": "Subject"}, status=400
    )
    assert "Style" in refusal["error"]
    print(
        "PROOF RICH 5 project style inherited, own style replaces; "
        "Style subject refused",
        inherited_preview,
        own,
        refusal,
        flush=True,
    )
    assert [
        a["id"] for a in request("/api/assets?type=person") if a["id"] == person["id"]
    ] == [person["id"]]
    original_comp = request(path)
    copy = request(path + "/duplicate", "POST", status=201)
    for field in ("style_asset_id", "style_deselected_images"):
        assert copy[field] == original_comp[field]
    for a, b in zip(copy["assets"], original_comp["assets"], strict=True):
        assert a["selected_originals"] == b["selected_originals"]
    for a, b in zip(copy["variants"], original_comp["variants"], strict=True):
        assert a["selected_originals"] == b["selected_originals"]
        assert a["deselected_images"] == b["deselected_images"]
    asset_copy = request(f"/api/assets/{garment['id']}/duplicate", "POST", status=201)
    for field in ("type", "type_tag", "preserve"):
        assert asset_copy[field] == garment[field]
    assert (
        next(i for i in asset_copy["images"] if i["source"] == "generated")["lineage"]
        == candidate["lineage"]
    )
    exported = package(path)
    assert exported["format_version"] == 3 and exported["style"]["id"] == style["id"]
    assert exported["asset_pack"][0]["asset"]["type"] == "person"
    assert exported["asset_pack"][0]["asset"]["preserve"] == person["preserve"]
    aexport = package(f"/api/assets/{garment['id']}")
    assert aexport["format_version"] == 2
    assert all(
        aexport["asset"][k] == garment[k] for k in ("type", "type_tag", "preserve")
    )
    print(
        "PROOF RICH 6 package versions asset 2/composition 3 "
        "with type, label, preservation and style",
        flush=True,
    )
    request(f"/api/assets/{style['id']}", "DELETE")
    assert style["id"] not in [a["id"] for a in request("/api/assets?type=style")]
    assert request(f"/api/generations/{snapshots[0]['id']}") == snapshots[0]
    assert request(path)["style"] is None
    assert not any(
        r["role"] == "style reference"
        for r in request(f"/api/variants/{frames[1]['id']}/preview")["references"]
    )
    request(ipath, "PATCH", {"style_asset_id": style["id"]}, status=404)
    after = package(path)
    assert any(
        a["id"] == style["id"] and a["deleted_at"] for a in after["referenced_assets"]
    )
    print(
        "PROOF RICH 7 deleted style absent from picker, cannot be picked; "
        "historical style snapshots and exports readable",
        snapshots[0],
        flush=True,
    )


if __name__ == "__main__":
    from check_generation import wait
    from check_stack import multipart, request, synthetic_png

    def upload(identifier, colors):
        data, media = multipart(
            [
                (f"synthetic-{i}.png", synthetic_png(color))
                for i, color in enumerate(colors)
            ]
        )
        return request(
            f"/api/assets/{identifier}/images", "POST", data, media, status=201
        )

    prove(request, wait, upload)

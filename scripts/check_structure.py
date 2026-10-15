"""Structure journey against the disposable placeholder stack, never owner data."""

import io
from zipfile import ZipFile

from check_generation import approved_upload, wait
from check_portability import package
from check_stack import request


def main():
    project = request(
        "/api/projects",
        "POST",
        {
            "name": "Synthetic structure folder",
            "instructions": "Synthetic project direction",
        },
        status=201,
    )
    assets = [
        request(
            "/api/assets", "POST", {"name": "Synthetic structure asset"}, status=201
        ),
        next(
            a
            for a in request("/api/assets")
            if a["name"] == "Synthetic formerly limited asset"
        ),
    ]
    assets = [
        approved_upload(a["id"], [color])
        for a, color in zip(assets, ["purple", "orange"], strict=True)
    ]
    single = request(
        "/api/compositions",
        "POST",
        {
            "name": "Synthetic stand-alone",
            "kind": "single",
            "brief": "Synthetic composition direction\n\nSynthetic scene",
        },
        status=201,
    )
    path = f"/api/compositions/{single['id']}"
    frame = single["variants"][0]["id"]
    assert single["brief"] == "Synthetic composition direction\n\nSynthetic scene"
    assert "direction" not in single and "scene" not in single
    draft = request(
        f"/api/variants/{frame}/preview",
        "POST",
        {"brief": "Synthetic draft brief", "instructions": "Hidden single text"},
    )
    assert draft["prompt"] == "Synthetic draft brief"
    assert request(path)["brief"] == single["brief"]
    for asset in assets:
        request(path + f"/assets/{asset['id']}", "PUT", {"role": "Subject"})
    preview = request(f"/api/variants/{frame}/preview")
    assert preview["prompt"].startswith(
        "Synthetic composition direction\n\nSynthetic scene"
    )
    assert "Synthetic project direction" not in preview["prompt"]
    assert len(preview["references"]) == 2
    run = request(
        f"/api/variants/{frame}/runs",
        "POST",
        {"models": [{"model": "placeholder-a", "count": 1}]},
        status=201,
    )
    done = wait(run["generations"][0]["id"])
    request(
        f"/api/variants/{frame}/final",
        "PUT",
        {"generation_id": done["id"], "output": 0},
    )
    print(
        "PROOF STRUCTURE 1 stand-alone single, two global assets (including "
        "formerly limited), direction then scene; placeholder-a done",
        flush=True,
    )
    with ZipFile(io.BytesIO(request(path + "/sequence.zip"))) as archive:
        assert len(archive.namelist()) == 1
        assert archive.read(archive.namelist()[0]) == request(
            "/api/files/" + done["outputs"][0]
        )
    exported = package(path)
    assert exported["format_version"] == 6
    assert exported["composition"]["brief"] == single["brief"]
    assert "direction" not in exported["composition"]
    assert "scene" not in exported["composition"]
    assert exported["project"] is None and exported["composition"]["kind"] == "single"
    assert all(s["asset"]["project_id"] is None for s in exported["asset_pack"])
    print(
        "PROOF STRUCTURE 2 both stand-alone exports work; package version 6 "
        "project null and assets global",
        flush=True,
    )
    request(path, "PATCH", {"project_id": project["id"]})
    moved = request(f"/api/variants/{frame}/preview")
    assert moved["prompt"] == "Synthetic project direction\n\n" + preview["prompt"]
    assert request(f"/api/generations/{done['id']}") == done
    print(
        "PROOF STRUCTURE 3 moved into project: project then composition direction; "
        "earlier snapshot unchanged",
        flush=True,
    )
    story = request(
        "/api/compositions",
        "POST",
        {
            "name": "Synthetic structure storyboard",
            "kind": "storyboard",
            "project_id": project["id"],
        },
        status=201,
    )
    spath = f"/api/compositions/{story['id']}"
    for asset in assets:
        request(
            spath + f"/assets/{asset['id']}",
            "PUT",
            {"role": "Subject", "deselected_images": [asset["images"][0]["id"]]},
        )
    frames = [story["variants"][0]] + [
        request(spath + "/variants", "POST", {}, status=201) for _ in range(2)
    ]
    ids = [f["id"] for f in reversed(frames)]
    story = request(spath + "/frame-order", "PUT", {"ids": ids})
    generated = request(
        f"/api/variants/{ids[0]}/runs",
        "POST",
        {
            "models": [{"model": "placeholder-a", "count": 1}],
            "prompt": "Synthetic story",
        },
        status=201,
    )
    final = wait(generated["generations"][0]["id"])
    request(
        f"/api/variants/{ids[0]}/final",
        "PUT",
        {"generation_id": final["id"], "output": 0},
    )
    listing = request(f"/api/compositions?project_id={project['id']}")
    assert {c["id"] for c in listing} == {single["id"], story["id"]}
    assert {c["kind"] for c in listing} == {"single", "storyboard"}
    assert all(
        c["project"]["id"] == project["id"] and c["thumbnail"] and c["last_activity"]
        for c in listing
    )
    assert {c["id"] for c in request("/api/compositions")} >= {
        single["id"],
        story["id"],
    }
    assert {
        a["id"] for a in request(f"/api/assets?used_by_project={project['id']}")
    } == {a["id"] for a in assets}
    print(
        "PROOF STRUCTURE 4 three reordered storyboard frames, one final; listing "
        "kinds, projects, thumbnails, activity and project filter",
        flush=True,
    )
    request(path + "/variants", "POST", {}, status=409)
    request(path, "PATCH", {"kind": "storyboard"})
    added = request(path + "/variants", "POST", {}, status=201)
    request(path, "PATCH", {"kind": "single"}, status=409)
    request(f"/api/variants/{added['id']}", "DELETE")
    request(path, "PATCH", {"kind": "single"})
    print(
        "PROOF STRUCTURE 5 single to storyboard unlocks add; two-frame single "
        "refused; one-frame single accepted",
        flush=True,
    )
    original = request(spath)
    original_runs = [
        request(f"/api/variants/{f['id']}/runs") for f in original["variants"]
    ]
    copy = request(spath + "/duplicate", "POST", status=201)
    for key in ["project_id", "kind", "brief"]:
        assert copy[key] == original[key]
    assert copy["name"] == original["name"] + " (copy)"
    assert [
        {k: s[k] for k in ["asset_id", "role", "position", "deselected_images"]}
        for s in copy["assets"]
    ] == [
        {k: s[k] for k in ["asset_id", "role", "position", "deselected_images"]}
        for s in original["assets"]
    ]
    assert [
        {k: f[k] for k in ["name", "instructions", "position", "deselected_images"]}
        for f in copy["variants"]
    ] == [
        {k: f[k] for k in ["name", "instructions", "position", "deselected_images"]}
        for f in original["variants"]
    ]
    assert all(
        f["final"] is None and request(f"/api/variants/{f['id']}/runs") == []
        for f in copy["variants"]
    )
    assert request(spath) == original
    assert [
        request(f"/api/variants/{f['id']}/runs") for f in original["variants"]
    ] == original_runs
    print(
        "PROOF STRUCTURE 6 duplicate pack, deselections and ordered frames; no "
        "runs/finals; original unchanged",
        flush=True,
    )
    print(
        "PROOF STRUCTURE 7 formerly project-limited asset migrated global and used "
        "stand-alone",
        flush=True,
    )


if __name__ == "__main__":
    main()

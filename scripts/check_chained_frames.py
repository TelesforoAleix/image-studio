"""Chained frame journey using only the disposable CI placeholder stack."""

import io
import json
import time
from zipfile import ZipFile

from check_generation import approved_upload, wait
from check_stack import request


def sequence(path, *, terminal=True):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        seq = request(path + "/frame-sequences")[0]
        if not terminal or seq["state"] not in ("running", "stopping"):
            return seq
        time.sleep(0.25)
    raise AssertionError("Sequence did not finish")


def main():
    comp = request(
        "/api/compositions",
        "POST",
        {
            "name": "Synthetic chained storyboard",
            "kind": "storyboard",
            "brief": "Synthetic continuous scene",
        },
        status=201,
    )
    path = f"/api/compositions/{comp['id']}"
    frames = [comp["variants"][0]] + [
        request(path + "/variants", "POST", {}, status=201) for _ in range(2)
    ]
    assets = [
        approved_upload(
            request(
                "/api/assets",
                "POST",
                {"name": f"Synthetic continuity asset {i}"},
                status=201,
            )["id"],
            [color],
        )
        for i, color in enumerate(["red", "green"])
    ]
    for asset in assets:
        request(path + f"/assets/{asset['id']}", "PUT", {"role": "Subject"})
    settings = {"models": [{"model": "placeholder-a", "count": 2}], "format": "1:1"}

    def start(mode, frame=None, model=None):
        return request(
            path + "/frame-sequences",
            "POST",
            {
                **settings,
                "mode": mode,
                **({"frame_id": frame} if frame else {}),
                **({"models": [{"model": model, "count": 1}]} if model else {}),
            },
            status=201,
        )

    seq = start("full")
    assert [f["state"] for f in seq["frames"]] == ["running", "waiting", "waiting"]
    assert request(f"/api/variants/{frames[1]['id']}/runs") == []
    assert request(f"/api/variants/{frames[2]['id']}/runs") == []
    assert sequence(path)["state"] == "done"
    done = [
        request(f"/api/variants/{f['id']}/runs")[0]["generations"][0] for f in frames
    ]
    assert not any(r["role"] == "previous frame" for r in done[0]["references"])
    for index in (1, 2):
        g = done[index]
        ref = g["references"][0]
        assert (
            ref["role"] == "previous frame"
            and ref["hash"] == done[index - 1]["outputs"][0]
        )
        assert (
            ref["frame_id"] == frames[index - 1]["id"]
            and ref["source"] == "first output"
        )
        assert ref["generation_id"] == done[index - 1]["id"] and ref["output"] == 0
        assert g["started_at"] >= done[index - 1]["finished_at"]
        assert (
            len(g["references"]) == 3 and "Image 1: the previous frame" in g["prompt"]
        )
    print(
        "PROOF CHAIN full: first frame alone, next queued after "
        "completion, previous first output first among two assets, exact "
        "source and legend",
        flush=True,
    )
    second = frames[1]["id"]
    third = f"/api/variants/{frames[2]['id']}"
    request(
        f"/api/variants/{second}/final",
        "PUT",
        {"generation_id": done[1]["id"], "output": 1},
    )
    single = request(third + "/runs", "POST", settings, status=201)
    assert single["references"][0]["hash"] == done[1]["outputs"][1]
    assert single["references"][0]["source"] == "final"
    wait(single["generations"][0]["id"])
    print(
        "PROOF CHAIN final rule directly: single-frame run on frame 3 "
        "takes frame 2 final instead of first output",
        flush=True,
    )
    request(third, "PATCH", {"use_previous_frame": False})
    off = request(third + "/runs", "POST", settings, status=201)
    assert len(off["references"]) == 2
    wait(off["generations"][0]["id"])
    request(third, "PATCH", {"use_previous_frame": True})
    reused = request(
        third + "/runs",
        "POST",
        {**settings, "references": single["references"], "content": "Synthetic pinned"},
        status=201,
    )
    assert reused["references"] == single["references"]
    wait(reused["generations"][0]["id"])
    count_before = len(request(third + "/runs"))
    start("rest", second, "placeholder-fails")
    failed = sequence(path)
    assert failed["state"] == "failed" and failed["frames"][0]["frame_id"] == second
    assert failed["frames"][0]["state"] == "failed" and failed["error"]
    assert len(request(third + "/runs")) == count_before
    resumed = start("rest", second)
    assert [f["frame_id"] for f in resumed["frames"]] == [second, frames[2]["id"]]
    assert sequence(path)["state"] == "done"
    print(
        "PROOF CHAIN failure on frame 2 stops; rest resumes from frame 2; "
        "switch removes previous reference; reuse pins it",
        flush=True,
    )
    count_before = len(request(f"/api/variants/{second}/runs"))
    stopping = start("full")
    assert (
        request(f"/api/frame-sequences/{stopping['id']}/stop", "POST")["state"]
        == "stopping"
    )
    stopped = sequence(path)
    assert stopped["state"] == "stopped"
    assert [f["state"] for f in stopped["frames"]] == ["done", "stopped", "stopped"]
    assert len(request(f"/api/variants/{second}/runs")) == count_before
    start("next", frames[0]["id"])
    assert sequence(path)["state"] == "done"
    # Two additional asset refs make four; continuity must be counted as the fifth.
    approved_upload(assets[0]["id"], ["blue", "yellow"])
    refusal = request(third + "/runs", "POST", settings, status=400)
    assert "5 references" in refusal["error"]
    solo = request(
        "/api/compositions",
        "POST",
        {"name": "Synthetic continuity single", "kind": "single", "brief": "Synthetic"},
        status=201,
    )
    solo_run = request(
        f"/api/variants/{solo['variants'][0]['id']}/runs", "POST", settings, status=201
    )
    assert solo_run["references"] == []
    wait(solo_run["generations"][0]["id"])
    before = request("/api/storage")
    with ZipFile(io.BytesIO(request(path + "/export.zip"))) as archive:
        package = json.loads(archive.read("manifest.json"))
        assert package["format_version"] == 6 and len(package["sequences"]) == 5
        assert package["sequences"][0]["state"] == "done"
        assert any(
            g["references"] and g["references"][0]["role"] == "previous frame"
            for f in package["frames"]
            for r in f["runs"]
            for g in r["generations"]
        )
    assert request("/api/storage") == before
    print(
        "PROOF CHAIN stop finishes only current frame; next is one frame; "
        "limits count continuity; singles never chain; version 6 package "
        "carries sequences and snapshots without storage writes",
        flush=True,
    )


if __name__ == "__main__":
    main()

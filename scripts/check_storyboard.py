"""Journey C against the internal placeholder using disposable CI records only."""

import hashlib
import io
import json
import subprocess
import time
from zipfile import ZipFile

from check_generation import approved_upload, wait
from check_stack import request


def pack_count(identifier):
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "studio",
            "-d",
            "studio",
            "-Atc",
            "SELECT count(*) FROM composition_assets "
            f"WHERE composition_id = {identifier}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def export(path, expected, skipped):
    manifest = request(path + "/sequence")
    assert [e["frame_id"] for e in manifest["entries"]] == [
        f["id"] for f, _ in expected
    ]
    assert [f["id"] for f in manifest["skipped"]] == skipped
    data = request(path + "/sequence.zip")
    with ZipFile(io.BytesIO(data)) as archive:
        assert archive.namelist() == [e["filename"] for e in manifest["entries"]]
        for index, ((frame, generation), entry) in enumerate(
            zip(expected, manifest["entries"], strict=True), 1
        ):
            assert (
                entry["filename"]
                == f"{index:02d}-frame-{frame['name'].split()[-1]}.png"
            )
            content = archive.read(entry["filename"])
            digest = hashlib.sha256(content).hexdigest()
            assert digest == generation["outputs"][0] == entry["hash"]
            assert content == request("/api/files/" + digest)
            print("ZIP ENTRY", entry["filename"], "sha256", digest, flush=True)
    return manifest


def main():
    project = request(
        "/api/projects", "POST", {"name": "Synthetic storyboard"}, status=201
    )
    assets = [
        request(
            "/api/assets",
            "POST",
            {"name": f"Synthetic story asset {i}", "project_id": project["id"]},
            status=201,
        )
        for i in range(2)
    ]
    assets = [
        approved_upload(assets[0]["id"], ["red", "blue"]),
        approved_upload(assets[1]["id"], ["green"]),
    ]
    comp = request(
        f"/api/projects/{project['id']}/compositions",
        "POST",
        {"name": "Synthetic storyboard", "scene": "Synthetic scene"},
        status=201,
    )
    path = f"/api/compositions/{comp['id']}"
    for asset, role in zip(assets, ["Subject", "Background"], strict=True):
        request(path + f"/assets/{asset['id']}", "PUT", {"role": role})
    frames = [comp["variants"][0]] + [
        request(path + "/variants", "POST", {}, status=201) for _ in range(2)
    ]
    for frame, instructions in zip(
        frames, ["Standing beside the car", "Getting in", "Seated"], strict=True
    ):
        request(f"/api/variants/{frame['id']}", "PATCH", {"instructions": instructions})
    excluded = assets[0]["images"][0]
    request(
        f"/api/variants/{frames[1]['id']}",
        "PATCH",
        {"deselected_images": [excluded["id"]]},
    )
    print(
        "PROOF C1 two assets, three references, three ordered frames "
        "with different instructions",
        flush=True,
    )
    done = []
    hashes = [i["hash"] for asset in assets for i in asset["images"]]
    for index, frame in enumerate(frames):
        run = request(
            f"/api/variants/{frame['id']}/runs",
            "POST",
            {"models": [{"model": "placeholder-a", "count": 1}]},
            status=201,
        )
        generation = wait(run["generations"][0]["id"])
        assert generation["placeholder"]
        assert [r["hash"] for r in generation["references"]] == [
            h for h in hashes if index != 1 or h != excluded["hash"]
        ]
        done.append(generation)
    assert pack_count(comp["id"]) == 2
    print(
        "PROOF C2 frame snapshots have 3/2/3 references; frame 2 excludes",
        excluded["hash"],
        "; composition_assets rows = 2",
        flush=True,
    )
    for index in [0, 2]:
        request(
            f"/api/variants/{frames[index]['id']}/final",
            "PUT",
            {"generation_id": done[index]["id"], "output": 0},
        )
    export(path, [(frames[i], done[i]) for i in [0, 2]], [frames[1]["id"]])
    print(
        "PROOF C3 frame 2 named as skipped; two contiguous ZIP entries "
        "match stored final bytes",
        flush=True,
    )
    request(
        f"/api/variants/{frames[1]['id']}/final",
        "PUT",
        {"generation_id": done[1]["id"], "output": 0},
    )
    ids = [frames[i]["id"] for i in [2, 0, 1]]
    request(path + "/frame-order", "PUT", {"ids": ids})
    export(path, [(frames[i], done[i]) for i in [2, 0, 1]], [])
    print("PROOF C4 all finals exported in reordered frame order 3, 1, 2", flush=True)
    foreign = request(
        f"/api/projects/{project['id']}/compositions",
        "POST",
        {"name": "Synthetic foreign"},
        status=201,
    )["variants"][0]["id"]
    request(path + "/frame-order", "PUT", {"ids": ids[:-1]}, status=400)
    request(
        path + "/frame-order", "PUT", {"ids": [ids[0], ids[1], foreign]}, status=400
    )
    assert [f["id"] for f in request(path)["variants"]] == ids
    print("PROOF C5 missing and foreign frame IDs refused; order unchanged", flush=True)
    request(f"/api/variants/{frames[0]['id']}", "DELETE")
    assert [f["id"] for f in request(path)["variants"]] == [ids[0], ids[2]]
    assert request(f"/api/variants/{frames[0]['id']}")["deleted_at"]
    export(path, [(frames[i], done[i]) for i in [2, 1]], [])
    assert request(f"/api/generations/{done[0]['id']}") == done[0]
    request("/api/files/" + done[0]["outputs"][0])
    request(f"/api/variants/{frames[2]['id']}", "DELETE")
    request(f"/api/variants/{frames[1]['id']}", "DELETE", status=409)
    print(
        "PROOF C6 deleted frame hidden from storyboard/export; "
        "generation and output retained; last live frame deletion refused",
        flush=True,
    )
    before = request(path)
    manifest = request(path + "/sequence")
    history = request(f"/api/variants/{frames[1]['id']}/runs")
    subprocess.run(["docker", "compose", "restart", "app", "worker"], check=True)
    for _ in range(60):
        try:
            request("/api/health")
            break
        except Exception:
            time.sleep(1)
    else:
        raise AssertionError("App did not recover")
    assert request(path) == before
    assert request(path + "/sequence") == manifest
    assert request(f"/api/variants/{frames[1]['id']}/runs") == history
    for generation in done:
        assert request(f"/api/generations/{generation['id']}") == generation
        request("/api/files/" + generation["outputs"][0])
    assert pack_count(comp["id"]) == 2
    export(path, [(frames[1], done[1])], [])
    print(
        "PROOF C7 app + worker restart preserves "
        "frame order, deselections, deletion, runs, finals, files and single pack; "
        "dump restore follows",
        flush=True,
    )
    print("STORYBOARD SUMMARY", json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()

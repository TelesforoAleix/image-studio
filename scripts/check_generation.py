"""Journey B and reference-view proof against the disposable placeholder stack."""

import subprocess
import time

from check_stack import multipart, request, synthetic_png


def approved_upload(asset_id, colors):
    data, media = multipart(
        [(f"synthetic-{i}.png", synthetic_png(color)) for i, color in enumerate(colors)]
    )
    asset = request(f"/api/assets/{asset_id}/images", "POST", data, media, status=201)
    for image in asset["images"]:
        asset = request(
            f"/api/assets/{asset_id}/images/{image['id']}", "PATCH", {"approved": True}
        )
    return asset


def wait(identifier, state="done", predicate=None):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        row = request(f"/api/generations/{identifier}")
        if predicate(row) if predicate else row["state"] == state:
            return row
        if row["state"] == "failed" and state != "failed":
            raise AssertionError(row)
        time.sleep(1)
    raise AssertionError(f"Generation {identifier} did not reach {state}")


def main():
    models = request("/api/models")
    assert {m["model_name"] for m in models} == {
        "placeholder-a",
        "placeholder-b",
        "placeholder-fails",
        "placeholder-chat",
        "placeholder-budget",
        "placeholder-sizes",
    }
    assert all(m["model_info"]["placeholder"] for m in models)
    project = request(
        "/api/projects",
        "POST",
        {
            "name": "Synthetic generation project",
            "instructions": "Synthetic project instructions",
        },
        status=201,
    )
    assets = [
        request(
            "/api/assets",
            "POST",
            {
                "name": f"Synthetic subject {i}",
                "description": "Synthetic description",
            },
            status=201,
        )
        for i in range(2)
    ]
    assets[0] = approved_upload(assets[0]["id"], ["red", "blue"])
    assets[1] = approved_upload(assets[1]["id"], ["green"])
    comp = request(
        f"/api/projects/{project['id']}/compositions",
        "POST",
        {
            "name": "Synthetic composition",
            "kind": "storyboard",
            "brief": "Synthetic scene instructions",
        },
        status=201,
    )
    variant = comp["variants"][0]["id"]
    request(
        f"/api/variants/{variant}",
        "PATCH",
        {"instructions": "Synthetic variant instructions"},
    )
    for i, asset in enumerate(assets):
        request(
            f"/api/compositions/{comp['id']}/assets/{asset['id']}",
            "PUT",
            {
                "role": ["the subject", "the background"][i],
                "deselected_images": [asset["images"][1]["id"]] if i == 0 else [],
            },
        )
    preview = request(f"/api/variants/{variant}/preview")
    hashes = [assets[0]["images"][0]["hash"], assets[1]["images"][0]["hash"]]
    assert [r["hash"] for r in preview["references"]] == hashes
    assert (
        "Synthetic project instructions" in preview["prompt"]
        and "reference images 2" in preview["prompt"]
    )
    print(
        "PROOF project + two assets + roles + deselection + fixed preview", flush=True
    )
    edited = "Synthetic edited prompt\n" + preview["prompt"]
    queue_path = f"/api/variants/{variant}/generations"
    queued = request(
        queue_path,
        "POST",
        {"model": "placeholder-a", "count": 2, "prompt": edited},
        status=201,
    )
    done = wait(queued["id"])
    assert done["prompt"] == edited and done["edited"] and done["placeholder"]
    assert done["model_info"] == models[0]["model_info"]
    assert [r["hash"] for r in done["references"]] == hashes
    assert [r["role"] for r in done["references"]] == ["the subject", "the background"]
    assert len(done["outputs"]) == 2
    outputs = {hash: request("/api/files/" + hash) for hash in done["outputs"]}
    print(
        "PROOF two done outputs fetched; "
        "edited prompt and ordered selected hashes snapshotted",
        flush=True,
    )
    # Replace canonical input without disturbing the old immutable record.
    old = assets[0]["images"][0]
    request(
        f"/api/assets/{assets[0]['id']}/images/{old['id']}",
        "PATCH",
        {"approved": False},
    )
    data, media = multipart([("replacement.png", synthetic_png("yellow"))])
    replacement = request(
        f"/api/assets/{assets[0]['id']}/images", "POST", data, media, status=201
    )["images"][-1]
    request(
        f"/api/assets/{assets[0]['id']}/images/{replacement['id']}",
        "PATCH",
        {"approved": True},
    )
    assert request(f"/api/generations/{done['id']}") == done
    new_preview = request(f"/api/variants/{variant}/preview")
    assert [r["hash"] for r in new_preview["references"]] == [
        replacement["hash"],
        hashes[1],
    ]
    print(
        "PROOF old snapshot unchanged; new preview uses replacement canonical file",
        flush=True,
    )
    reference = request(
        f"/api/assets/{assets[1]['id']}/generations",
        "POST",
        {"model": "placeholder-a", "count": 2},
        status=201,
    )
    reference = wait(reference["id"])
    candidates = [
        i
        for i in request(f"/api/assets/{assets[1]['id']}")["images"]
        if i["source"] == "generated"
    ]
    assert len(candidates) == 2 and all(
        not i["approved"] and not i["rejected"] for i in candidates
    )
    request(
        f"/api/assets/{assets[1]['id']}/images/{candidates[0]['id']}",
        "PATCH",
        {"approved": True},
    )
    visible = request(
        f"/api/assets/{assets[1]['id']}/images/{candidates[1]['id']}",
        "PATCH",
        {"rejected": True},
    )
    assert candidates[1]["id"] not in [i["id"] for i in visible["images"]]
    retained = request(f"/api/assets/{assets[1]['id']}?include_rejected=true")
    assert retained["images"][-1]["rejected"]
    request("/api/files/" + candidates[1]["hash"])
    print(
        "PROOF reference-view candidates generated; "
        "one approved, one rejected and hidden; file retained",
        flush=True,
    )
    failure = request(
        queue_path, "POST", {"model": "placeholder-fails", "count": 1}, status=201
    )
    failure = wait(failure["id"], "failed")
    assert "500" in failure["error"] and failure["attempts"] == 3
    print(
        "PROOF model HTTP 500 is failed after exactly three attempts with its status",
        flush=True,
    )
    subprocess.run(["docker", "compose", "stop", "placeholder"], check=True)
    try:
        offline = request(
            queue_path, "POST", {"model": "placeholder-a", "count": 1}, status=201
        )
        retried = wait(
            offline["id"],
            "waiting",
            lambda g: g["state"] == "waiting" and g["attempts"] >= 2,
        )
        assert retried["error"] and not retried["outputs"]
        print(
            "PROOF endpoint offline: queued with cached metadata; "
            "stays waiting through at least one retry",
            flush=True,
        )
    finally:
        subprocess.run(["docker", "compose", "start", "placeholder"], check=True)
    recovered = wait(offline["id"])
    assert recovered["attempts"] >= 3
    print("PROOF endpoint returns: same waiting generation finishes", flush=True)
    # More canonical references than the four accepted by placeholder-a.
    approved_upload(assets[0]["id"], ["purple", "orange", "black"])
    excessive = request(f"/api/variants/{variant}/preview")
    count = len(excessive["references"])
    assert count > 4
    refused = request(
        queue_path, "POST", {"model": "placeholder-a", "count": 1}, status=400
    )
    assert f"{count} references" in refused["error"] and "4" in refused["error"]
    print(
        "PROOF excessive references refused naming selected and accepted counts; "
        "none dropped",
        flush=True,
    )
    history = request(queue_path)
    library = request("/api/assets")
    subprocess.run(["docker", "compose", "restart", "app", "worker"], check=True)
    for _ in range(60):
        try:
            request("/api/health")
            break
        except Exception:
            time.sleep(1)
    else:
        raise AssertionError("App did not recover")
    assert request(queue_path) == history
    assert request("/api/assets") == library
    assert request(f"/api/generations/{done['id']}") == done
    assert request(f"/api/assets/{assets[1]['id']}?include_rejected=true") == retained
    for hash, data in outputs.items():
        assert request("/api/files/" + hash) == data
    print(
        "PROOF app + worker restart: compositions, snapshots, states, "
        "flags and outputs persist",
        flush=True,
    )


if __name__ == "__main__":
    main()

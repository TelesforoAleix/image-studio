"""Journey D proof using only disposable CI data and the placeholder endpoint."""

import subprocess
import time

from check_generation import approved_upload, wait
from check_stack import multipart, request, synthetic_png


def main():
    project = request(
        "/api/projects", "POST", {"name": "Synthetic comparison"}, status=201
    )
    assets = [
        request(
            "/api/assets",
            "POST",
            {"name": f"Synthetic comparison {i}"},
            status=201,
        )
        for i in range(2)
    ]
    assets[0] = approved_upload(assets[0]["id"], ["red", "blue"])
    assets[1] = approved_upload(assets[1]["id"], ["green"])
    comp = request(
        f"/api/projects/{project['id']}/compositions",
        "POST",
        {"name": "Synthetic compare", "scene": "Synthetic scene"},
        status=201,
    )
    variant = comp["variants"][0]["id"]
    for i, asset in enumerate(assets):
        request(
            f"/api/compositions/{comp['id']}/assets/{asset['id']}",
            "PUT",
            {"role": ["Subject", "Background"][i]},
        )
    path = f"/api/variants/{variant}/runs"
    preview = request(f"/api/variants/{variant}/preview")
    assert len(preview["references"]) == 3
    edited = "Synthetic comparison edited prompt"
    run = request(
        path,
        "POST",
        {
            "models": [
                {"model": "placeholder-a", "count": 2},
                {"model": "placeholder-b", "count": 1},
                {"model": "placeholder-fails", "count": 1},
            ],
            "prompt": edited,
        },
        status=201,
    )
    a, b, failure = [
        wait(g["id"], "failed" if g["model"] == "placeholder-fails" else "done")
        for g in run["generations"]
    ]
    assert (
        len(a["outputs"]) == 2 and len(b["outputs"]) == 1 and "500" in failure["error"]
    )
    initial = request(path)[0]
    assert len(initial["generations"]) == 3
    assert all(
        g["run_id"] == run["run_id"]
        and g["prompt"] == edited
        and g["edited"]
        and [{k: v for k, v in r.items() if k != "sent_size"} for r in g["references"]]
        == preview["references"]
        and g["placeholder"]
        for g in initial["generations"]
    )
    print(
        "PROOF D1 three model rows share one run, edited prompt and three references; "
        "A done x2, B done x1, deliberate failure kept with error",
        flush=True,
    )
    retry = request(f"/api/generations/{failure['id']}/retry", "POST", status=201)
    assert retry["retry_of"] == failure["id"] and retry["run_id"] == run["run_id"]
    for key in ("model", "model_info", "prompt", "references", "count", "placeholder"):
        assert retry[key] == failure[key]
    wait(retry["id"], "failed")
    assert request(f"/api/generations/{failure['id']}") == failure
    after_retry = request(path)[0]
    assert len(after_retry["generations"]) == 4
    assert all(
        g["run_id"] == run["run_id"]
        and g["prompt"] == edited
        and [{k: v for k, v in r.items() if k != "sent_size"} for r in g["references"]]
        == preview["references"]
        for g in after_retry["generations"]
    )
    print(
        "PROOF D2 new linked retry row in same run; "
        "four rows retained, old failure unchanged",
        flush=True,
    )
    final_path = f"/api/variants/{variant}/final"
    for g in (b, a):
        final = request(final_path, "PUT", {"generation_id": g["id"], "output": 0})
        assert final["hash"] == g["outputs"][0]
    assert request(final_path)["generation_id"] == a["id"]
    assert request(f"/api/generations/{a['id']}") == a
    assert request(f"/api/generations/{b['id']}") == b
    print(
        "PROOF D3 B final replaced by A final; both outputs remain listed", flush=True
    )
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
    current = request(f"/api/variants/{variant}/preview")
    assert old["hash"] not in [r["hash"] for r in current["references"]]
    reused = request(
        path,
        "POST",
        {
            "models": [{"model": "placeholder-b", "count": 1}],
            "prompt": "Synthetic changed draft",
            "references": initial["references"],
        },
        status=201,
    )
    reused_done = wait(reused["generations"][0]["id"])
    assert reused_done["prompt"] == "Synthetic changed draft" and reused_done["edited"]
    assert [r["hash"] for r in reused_done["references"]] == [
        r["hash"] for r in initial["references"]
    ]
    assert old["hash"] in [r["hash"] for r in reused_done["references"]]
    assert request(path)[1] == after_retry
    print(
        "PROOF D4 browser draft reuse sends old immutable hash "
        "after canonical replacement, "
        "changed prompt and B only; original run unchanged",
        flush=True,
    )
    approved_upload(assets[0]["id"], ["purple", "orange"])
    # The S4 helper approves all attachments; retain the canonical replacement.
    request(
        f"/api/assets/{assets[0]['id']}/images/{old['id']}",
        "PATCH",
        {"approved": False},
    )
    excessive = request(f"/api/variants/{variant}/preview")
    assert len(excessive["references"]) == 5
    before = request(path)
    refused = request(
        path,
        "POST",
        {
            "models": [
                {"model": "placeholder-a", "count": 1},
                {"model": "placeholder-b", "count": 1},
            ]
        },
        status=400,
    )
    assert all(s in refused["error"] for s in ("placeholder-a", "5", "4"))
    assert request(path) == before
    print(
        "PROOF D5 entire run refused naming placeholder-a, 5 and 4; nothing queued",
        flush=True,
    )
    # A stored output exists, but is not attached to any visible asset.
    forbidden = {**initial["references"][0], "hash": a["outputs"][0]}
    request(
        path,
        "POST",
        {
            "models": [{"model": "placeholder-b", "count": 1}],
            "prompt": "Synthetic",
            "references": [forbidden],
        },
        status=400,
    )
    request(
        path,
        "POST",
        {
            "models": [{"model": "placeholder-b", "count": 1}],
            "prompt": "Synthetic",
            "references": [{**forbidden, "hash": "0" * 64}],
        },
        status=400,
    )
    assert request(path) == before
    print(
        "PROOF D6 unattached stored hash and unknown hash refused; nothing queued",
        flush=True,
    )
    final = request(final_path)
    library = request("/api/assets")
    outputs = {
        h: request("/api/files/" + h) for g in (a, b, reused_done) for h in g["outputs"]
    }
    subprocess.run(["docker", "compose", "restart", "app", "worker"], check=True)
    for _ in range(60):
        try:
            request("/api/health")
            break
        except Exception:
            time.sleep(1)
    else:
        raise AssertionError("App did not recover")
    assert request(path) == before and request(final_path) == final
    assert request("/api/assets") == library
    for h, data in outputs.items():
        assert request("/api/files/" + h) == data
    print(
        "PROOF D7 app + worker restart preserves runs, retries, final, "
        "references and all outputs",
        flush=True,
    )


if __name__ == "__main__":
    main()

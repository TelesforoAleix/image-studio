"""Hosted contract proof using synthetic inputs and the disposable CI simulator."""

import io
import json
import subprocess

from check_generation import wait
from check_stack import multipart, request
from PIL import Image


def main():
    project = request(
        "/api/projects", "POST", {"name": "Synthetic route proof"}, status=201
    )
    asset = request(
        "/api/assets",
        "POST",
        {"name": "Synthetic route references"},
        status=201,
    )
    originals = []
    for color, size in [
        ("red", (1200, 800)),
        ("blue", (800, 1200)),
        ("green", (1024, 1024)),
    ]:
        output = io.BytesIO()
        Image.new("RGB", size, color).save(output, format="PNG")
        originals.append(output.getvalue())
    data, media = multipart(
        [(f"synthetic-{i}.png", data) for i, data in enumerate(originals)]
    )
    asset = request(
        f"/api/assets/{asset['id']}/images", "POST", data, media, status=201
    )
    for image in asset["images"]:
        request(
            f"/api/assets/{asset['id']}/images/{image['id']}",
            "PATCH",
            {"approved": True},
        )
    comp = request(
        f"/api/projects/{project['id']}/compositions",
        "POST",
        {"name": "Synthetic two shapes", "scene": "Synthetic scene"},
        status=201,
    )
    request(
        f"/api/compositions/{comp['id']}/assets/{asset['id']}",
        "PUT",
        {"role": "Subject"},
    )
    frame = comp["variants"][0]["id"]
    run = request(
        f"/api/variants/{frame}/runs",
        "POST",
        {
            "models": [
                {"model": "placeholder-a", "count": 1},
                {"model": "placeholder-chat", "count": 1},
            ]
        },
        status=201,
    )
    hashes = [image["hash"] for image in asset["images"]]
    for row in run["generations"]:
        done = wait(row["id"])
        assert done["attempts"] == 1
        assert [ref["hash"] for ref in done["references"]] == hashes
        with Image.open(
            io.BytesIO(request("/api/files/" + done["outputs"][0]))
        ) as image:
            received = json.loads(image.info["received_sizes"])
        assert received == [ref["sent_size"] for ref in done["references"]]
        expected = (
            [[512, 341], [341, 512], [512, 512]]
            if done["model"] == "placeholder-chat"
            else [[1200, 800], [800, 1200], [1024, 1024]]
        )
        assert received == expected
        print(
            "PROOF ROUTE",
            done["model"],
            "done; received sizes",
            received,
            "snapshot original hashes",
            hashes,
            flush=True,
        )
    for image, original in zip(asset["images"], originals, strict=True):
        assert request("/api/files/" + image["hash"]) == original
    budget = request(
        f"/api/variants/{frame}/generations",
        "POST",
        {"model": "placeholder-budget", "count": 1},
        status=201,
    )
    budget = wait(budget["id"], "failed")
    assert budget["attempts"] == 1 and budget["service_failures"] == 0
    assert budget["error"] == "Monthly image budget reached — resets on the 1st (UTC)"
    print(
        "PROOF ROUTE budget HTTP 402: failed after one attempt:",
        budget["error"],
        flush=True,
    )
    failed = request(
        f"/api/variants/{frame}/generations",
        "POST",
        {"model": "placeholder-fails", "count": 1},
        status=201,
    )
    failed = wait(failed["id"], "failed")
    assert (
        failed["attempts"] == failed["service_failures"] == 3
        and "HTTP 500" in failed["error"]
    )
    print(
        "PROOF ROUTE HTTP 500: failed after exactly three attempts:",
        failed["error"],
        flush=True,
    )
    # Disposable fixture models historical data from an endpoint that retired a model.
    subprocess.run(
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
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "UPDATE generations SET model='placeholder-retired' "
            f"WHERE id={failed['id']}",
        ],
        check=True,
    )
    before = request(f"/api/variants/{frame}/runs")
    refused = request(f"/api/generations/{failed['id']}/retry", "POST", status=400)
    assert "no longer listed" in refused["error"]
    assert request(f"/api/variants/{frame}/runs") == before
    print(
        "PROOF ROUTE retired model retry refused without a row or job:",
        refused,
        flush=True,
    )


if __name__ == "__main__":
    main()

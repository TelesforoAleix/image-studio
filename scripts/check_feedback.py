"""One-output feedback proof, synthetic placeholder work only."""

import io
import json
from zipfile import ZipFile


def prove(request, wait, upload):
    assets = []
    for name, kind, color in [
        ("Synthetic subject", "person", "red"),
        ("Synthetic style", "style", "blue"),
    ]:
        asset = request("/api/assets", "POST", {"name": name, "type": kind}, status=201)
        asset = upload(asset["id"], [color])
        request(
            f"/api/assets/{asset['id']}/images/{asset['images'][0]['id']}",
            "PATCH",
            {"approved": True},
        )
        assets.append(asset)
    comp = request(
        "/api/compositions",
        "POST",
        {
            "name": "Synthetic feedback",
            "kind": "single",
            "brief": "Synthetic scene",
            "style_asset_id": assets[1]["id"],
        },
        status=201,
    )
    request(
        f"/api/compositions/{comp['id']}/assets/{assets[0]['id']}",
        "PUT",
        {"role": "Subject"},
    )
    frame = comp["variants"][0]["id"]
    path = f"/api/variants/{frame}/runs"
    run = request(
        path,
        "POST",
        {
            "models": [
                {"model": name, "count": 2}
                for name in ["placeholder-a", "placeholder-chat"]
            ]
        },
        status=201,
    )
    a, b = [wait(g["id"]) for g in run["generations"]]
    assert len(a["outputs"]) == len(b["outputs"]) == 2
    assert all(f["updated_at"] is None for g in [a, b] for f in g["feedback"])

    def click(g, output, verdict):
        response = request(
            f"/api/generations/{g['id']}/outputs/{output}/feedback",
            "PATCH",
            {"verdict": verdict},
        )
        stored = request(f"/api/generations/{g['id']}")["feedback"][output]
        assert (
            response == stored and stored["verdict"] == verdict and stored["updated_at"]
        )
        return stored

    states = [
        click(a, 0, "good"),
        click(b, 1, "not_good"),
        click(a, 0, "not_good"),
        click(b, 1, None),
    ]
    print(
        "PROOF FEEDBACK 1 two models/two outputs; good, not good, change, clear "
        "stored after each click",
        states,
        flush=True,
    )
    ratings = [
        {"asset_id": asset["id"], "rating": rating}
        for asset, rating in zip(assets, ["kept", "partly"], strict=True)
    ]
    detail_path = f"/api/generations/{a['id']}/outputs/1/feedback"
    detail = request(
        detail_path,
        "PATCH",
        {
            "verdict": "good",
            "asset_ratings": ratings,
            "note": "Synthetic feedback note",
        },
    )
    assert (
        detail["asset_ratings"] == ratings
        and detail["note"] == "Synthetic feedback note"
    )
    stranger = request(
        "/api/assets", "POST", {"name": "Synthetic unreferenced"}, status=201
    )
    refused = request(
        detail_path,
        "PATCH",
        {"asset_ratings": [{"asset_id": stranger["id"], "rating": "lost"}]},
        status=400,
    )
    assert request(f"/api/generations/{a['id']}")["feedback"][1] == detail
    # Quick verdict writes preserve detail; clearing does not remove its row.
    preserved = click(a, 1, None)
    assert preserved["asset_ratings"] == ratings and preserved["note"] == detail["note"]
    click(a, 1, "good")
    print(
        "PROOF FEEDBACK 2 snapshot subject/style ratings and note saved; "
        "unreferenced asset refused; quick verdict preserves detail",
        detail,
        refused,
        preserved,
        flush=True,
    )
    tally = request(f"/api/variants/{frame}/feedback-tally")
    assert tally == {
        "placeholder-a": {"rated": 2, "good": 1},
        "placeholder-chat": {"rated": 0, "good": 0},
    }
    history = request(path)
    rows = {g["id"]: g for r in history for g in r["generations"]}
    assert rows[a["id"]]["feedback"][0]["verdict"] == "not_good"
    assert rows[b["id"]]["feedback"][1]["verdict"] is None
    print(
        "PROOF FEEDBACK 3 History reads per-output feedback; per-model tally matches",
        tally,
        history,
        flush=True,
    )
    storage = request("/api/storage")
    with ZipFile(
        io.BytesIO(request(f"/api/compositions/{comp['id']}/export.zip"))
    ) as archive:
        package = json.loads(archive.read("manifest.json"))
    assert package["format_version"] == 5
    exported = {
        g["id"]: g
        for f in package["frames"]
        for r in f["runs"]
        for g in r["generations"]
    }
    assert exported == rows
    assert request(path) == history and request("/api/storage") == storage
    print(
        "PROOF FEEDBACK 4 complete composition package version 5 carries every "
        "output feedback; records/storage unchanged",
        package,
        flush=True,
    )
    return a, b, frame


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

"""Curated membership journey against the disposable CI stack, never owner data."""

from check_stack import request


def main():
    project = request(
        "/api/projects", "POST", {"name": "Synthetic curated folder"}, status=201
    )
    asset = request(
        "/api/assets", "POST", {"name": "Synthetic curated subject"}, status=201
    )
    comp = request(
        "/api/compositions",
        "POST",
        {
            "name": "Synthetic curated composition",
            "kind": "single",
            "project_id": project["id"],
        },
        status=201,
    )
    path = f"/api/projects/{project['id']}/assets"
    pack = f"/api/compositions/{comp['id']}/assets/{asset['id']}"
    assert request(path) == []
    request(pack, "PUT", {"role": "Subject"})
    first = request(path)
    assert [a["id"] for a in first] == [asset["id"]]
    request(pack, "PUT", {"role": "Subject"})
    assert request(path) == first
    request(path + f"/{asset['id']}", "DELETE")
    request(path + f"/{asset['id']}", "DELETE")
    assert request(path) == []
    assert (
        request(f"/api/compositions/{comp['id']}")["assets"][0]["asset_id"]
        == asset["id"]
    )
    request(path + f"/{asset['id']}", "PUT")
    request(f"/api/assets/{asset['id']}", "DELETE")
    assert request(path)[0]["deleted_at"]
    request(path + f"/{asset['id']}", "DELETE")
    assert request(path) == []
    assert (
        request(f"/api/compositions/{comp['id']}")["assets"][0]["asset_id"]
        == asset["id"]
    )
    assert request("/api/compositions?q=synthetic%20curated")[0]["frame_count"] == 1
    print(
        "PROOF PROJECT ASSETS: pack adds membership atomically/idempotently; "
        "timestamp removal leaves pack; re-add and deleted mark/removal; "
        "name search/frame count",
        flush=True,
    )


if __name__ == "__main__":
    main()

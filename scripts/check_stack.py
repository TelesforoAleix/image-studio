"""Disposable CI stack proof; all image bytes are generated in memory."""

import hashlib
import io
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from PIL import Image

BASE = "http://127.0.0.1:8200"


def request(path, method="GET", body=None, content_type="application/json", status=200):
    if body is not None and not isinstance(body, bytes):
        body = json.dumps(body).encode()
    call = urllib.request.Request(
        BASE + path,
        data=body,
        method=method,
        headers={"Content-Type": content_type} if body else {},
    )
    try:
        response = urllib.request.urlopen(call, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read()
        if response.headers.get_content_type() == "application/json":
            result = json.loads(data)
            print(method, path, response.status, json.dumps(result), flush=True)
        else:
            result = data
            print(
                method,
                path,
                response.status,
                "bytes=",
                len(data),
                "sha256=",
                hashlib.sha256(data).hexdigest(),
                flush=True,
            )
        assert response.status == status, result
        return result


def multipart(files):
    boundary = "synthetic-" + uuid.uuid4().hex
    parts = []
    for name, content in files:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '(
                f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
            ).encode()
            + content
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def synthetic_png(color):
    output = io.BytesIO()
    Image.new("RGB", (16, 12), color).save(output, format="PNG")
    return output.getvalue()


def signature(asset):
    return [
        (image["hash"], image["approved"], image["source"]) for image in asset["images"]
    ]


def main():
    project = request(
        "/api/projects",
        "POST",
        {"name": "Synthetic project", "instructions": "Synthetic CI direction"},
        status=201,
    )
    assert request(f"/api/projects/{project['id']}") == project
    asset = request(
        "/api/assets",
        "POST",
        {
            "name": "Synthetic asset",
            "description": "Synthetic CI asset",
            "type_tag": "object",
        },
        status=201,
    )
    assert asset["project_id"] is None
    path = f"/api/assets/{asset['id']}"
    originals = [synthetic_png("red"), synthetic_png("blue")]
    body, content_type = multipart(
        [(f"synthetic-{i}.png", data) for i, data in enumerate(originals)]
    )
    uploaded = request(path + "/images", "POST", body, content_type, status=201)
    assert len(uploaded["images"]) == 2
    body, content_type = multipart([("synthetic.txt", b"not an image")])
    refused = request(path + "/images", "POST", body, content_type, status=400)
    assert (
        "synthetic.txt" in refused["error"] and "JPEG, PNG or WebP" in refused["error"]
    )
    print("PROOF non-image refused with named JSON 400", flush=True)
    # Repeat bytes to prove deduplication, including unchanged attachment count.
    body, content_type = multipart([("synthetic-repeat.png", originals[0])])
    repeat = request(path + "/images", "POST", body, content_type, status=201)
    assert signature(repeat) == signature(uploaded)
    print("PROOF repeated upload shares hash and attachment", flush=True)
    first, second = uploaded["images"]
    approved = request(path + f"/images/{first['id']}", "PATCH", {"approved": True})
    assert [i["approved"] for i in approved["images"]] == [True, False]
    request(path + f"/images/{second['id']}", "PATCH", {"approved": True})
    replaced = request(path + f"/images/{first['id']}", "PATCH", {"approved": False})
    assert [i["approved"] for i in replaced["images"]] == [False, True]
    print("PROOF canonical replacement keeps both images attached", flush=True)
    duplicate = request(path + "/duplicate", "POST", status=201)
    assert signature(duplicate) == signature(replaced)
    print("PROOF duplicate uses same hashes and approvals", flush=True)
    request(path, "DELETE")
    library = request("/api/assets")
    assert asset["id"] not in [a["id"] for a in library]
    assert duplicate["id"] in [a["id"] for a in library]
    request(path, status=404)
    deleted = request(path + "?include_deleted=true")
    assert deleted["deleted_at"] is not None
    assert signature(deleted) == signature(replaced)
    print(
        "PROOF soft-deleted original absent from live library, rows retained",
        flush=True,
    )
    for image, data in zip(uploaded["images"], originals, strict=True):
        assert request("/api/files/" + image["hash"]) == data
    print("PROOF all original files fetchable after soft delete", flush=True)
    subprocess.run(["docker", "compose", "restart", "app"], check=True)
    for _attempt in range(60):
        try:
            request("/api/health")
            break
        except (AssertionError, urllib.error.URLError, ConnectionError):
            time.sleep(1)
    else:
        raise AssertionError("App did not recover after restart")
    assert request(f"/api/projects/{project['id']}") == project
    assert request("/api/assets") == library
    assert request(path + "?include_deleted=true") == deleted
    assert request(f"/api/assets/{duplicate['id']}") == duplicate
    for image, data in zip(uploaded["images"], originals, strict=True):
        assert request("/api/files/" + image["hash"]) == data
    print(
        "PROOF project, library, deleted original, duplicate approvals "
        "and files survive restart",
        flush=True,
    )


if __name__ == "__main__":
    main()

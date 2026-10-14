"""Journey E and portable exports using disposable synthetic CI records only."""

import hashlib
import io
import json
import subprocess
from zipfile import ZipFile

from check_dump import counts, sql
from check_generation import approved_upload, wait
from check_stack import multipart, request, signature, synthetic_png


def package(path):
    data = request(path + "/export.zip")
    with ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format_version"] == (
            4 if manifest["format"] == "image-studio-composition" else 2
        )
        assert manifest["exported_at"]
        assert len(archive.namelist()) == 1 + len(manifest["files"])
        assert set(archive.namelist()) == {"manifest.json"} | {
            f["filename"] for f in manifest["files"]
        }
        for file in manifest["files"]:
            content = archive.read(file["filename"])
            assert hashlib.sha256(content).hexdigest() == file["hash"]
            assert file["filename"].split("/")[1].split(".")[0] == file["hash"]
            assert len(content) == file["size"]
            assert content == request("/api/files/" + file["hash"])
            print("PACKAGE FILE", file["filename"], "sha256 verified", flush=True)
    print("PACKAGE MANIFEST", json.dumps(manifest), flush=True)
    return manifest


def expected_storage():
    # Independent database calculation: each stored hash occupies one category.
    return json.loads(
        sql(
            "studio",
            """
WITH categorized AS (
 SELECT f.*,
 CASE WHEN EXISTS (SELECT 1 FROM asset_images i WHERE i.file_hash = f.hash
                   AND i.source = 'uploaded') THEN 'uploaded'
      WHEN EXISTS (SELECT 1 FROM generations g WHERE NOT g.placeholder
                   AND g.outputs @> jsonb_build_array(f.hash)) THEN 'generated'
      WHEN EXISTS (SELECT 1 FROM generations g WHERE g.placeholder
                   AND g.outputs @> jsonb_build_array(f.hash)) THEN 'placeholder'
      ELSE 'generated' END AS category
 FROM stored_files f
), categories AS (
 SELECT category, sum(size)::bigint AS bytes, count(*) AS file_count
 FROM categorized GROUP BY category
)
SELECT jsonb_build_object(
 'total', (SELECT jsonb_build_object('bytes', coalesce(sum(size), 0),
                                  'file_count', count(*)) FROM stored_files),
 'uploaded', coalesce((SELECT jsonb_build_object('bytes', bytes,
                         'file_count', file_count) FROM categories
                         WHERE category = 'uploaded'), '{"bytes":0,"file_count":0}'),
 'generated', coalesce((SELECT jsonb_build_object('bytes', bytes,
                         'file_count', file_count) FROM categories
                         WHERE category = 'generated'), '{"bytes":0,"file_count":0}'),
 'placeholder', coalesce((SELECT jsonb_build_object('bytes', bytes,
                         'file_count', file_count) FROM categories
                         WHERE category = 'placeholder'), '{"bytes":0,"file_count":0}')
)
""",
        )
    )


def main():
    project = request(
        "/api/projects",
        "POST",
        {"name": "Synthetic portability", "instructions": "Synthetic direction"},
        status=201,
    )
    asset = request(
        "/api/assets",
        "POST",
        {
            "name": "Synthetic portable asset",
            "type_tag": "object",
            "description": "Synthetic description",
        },
        status=201,
    )
    apath = f"/api/assets/{asset['id']}"
    body, content_type = multipart(
        [
            ("first.png", synthetic_png("purple")),
            ("second.png", synthetic_png("orange")),
        ]
    )
    asset = request(apath + "/images", "POST", body, content_type, status=201)
    first = asset["images"][0]
    asset = request(apath + f"/images/{first['id']}", "PATCH", {"approved": True})
    second = request(
        "/api/assets", "POST", {"name": "Synthetic second portable asset"}, status=201
    )
    second = approved_upload(second["id"], ["cyan"])
    comp = request(
        f"/api/projects/{project['id']}/compositions",
        "POST",
        {
            "name": "Synthetic portable composition",
            "scene": "Synthetic scene",
            "kind": "storyboard",
        },
        status=201,
    )
    cpath = f"/api/compositions/{comp['id']}"
    for a, role in [(asset, "Subject"), (second, "Background")]:
        request(cpath + f"/assets/{a['id']}", "PUT", {"role": role})
    frames = [comp["variants"][0], request(cpath + "/variants", "POST", {}, status=201)]
    done = []
    for i, frame in enumerate(frames):
        request(
            f"/api/variants/{frame['id']}",
            "PATCH",
            {"instructions": f"Synthetic action {i}"},
        )
        run = request(
            f"/api/variants/{frame['id']}/runs",
            "POST",
            {"models": [{"model": "placeholder-a", "count": 1}]},
            status=201,
        )
        done.append(wait(run["generations"][0]["id"]))
    final = request(
        f"/api/variants/{frames[0]['id']}/final",
        "PUT",
        {"generation_id": done[0]["id"], "output": 0},
    )
    print(
        "PROOF E1 two uploads, one approved; two assets, two frames, "
        "two placeholder-a runs and one final",
        flush=True,
    )
    # Freeze periodic library job writes so all table row counts can be compared.
    subprocess.run(["docker", "compose", "stop", "worker"], check=True)
    try:
        prove_exports(project, asset, first, comp, frames, done, final)
    finally:
        subprocess.run(["docker", "compose", "start", "worker"], check=True)


def prove_exports(project, asset, first, comp, frames, done, final):
    apath = f"/api/assets/{asset['id']}"
    cpath = f"/api/compositions/{comp['id']}"
    body, content_type = multipart([("replacement.png", synthetic_png("yellow"))])
    replacement = request(apath + "/images", "POST", body, content_type, status=201)[
        "images"
    ][-1]
    request(apath + f"/images/{replacement['id']}", "PATCH", {"approved": True})
    current = request(apath + f"/images/{first['id']}", "PATCH", {"approved": False})
    before = counts("studio")
    exported = package(apath)
    assert exported["asset"] == {**current, "project_id": None}
    assert len(exported["asset"]["images"]) == 3
    assert [i["approved"] for i in exported["asset"]["images"]] == [False, False, True]
    assert counts("studio") == before
    print(
        "PROOF E2 canonical replacement retains three attachments; "
        "asset package flags current; every file hash verified; counts unchanged",
        flush=True,
    )
    copy = request(apath + "/duplicate", "POST", status=201)
    assert signature(copy) == signature(current)
    assert request(apath) == current
    assert copy["id"] in [a["id"] for a in request("/api/assets")]
    print(
        "PROOF E3 duplicate listed with shared files and flags; original unchanged",
        flush=True,
    )
    request(apath, "DELETE")
    assert asset["id"] not in [a["id"] for a in request("/api/assets")]
    deleted = request(apath + "?include_deleted=true")
    before = counts("studio")
    assert package(apath)["asset"] == {**deleted, "project_id": None}
    complete = package(cpath)
    assert complete["project"] == project
    assert complete["composition"]["scene"] == comp["scene"]
    assert complete["asset_pack"][0]["asset"]["deleted_at"] == deleted["deleted_at"]
    assert [f["id"] for f in complete["frames"]] == [f["id"] for f in frames]
    assert all(not f["deleted"] for f in complete["frames"])
    assert complete["frames"][0]["final"] == final
    assert complete["frames"][1]["final"] is None
    exported_generations = [
        g for f in complete["frames"] for r in f["runs"] for g in r["generations"]
    ]
    assert exported_generations == done
    assert all(g["placeholder"] for g in exported_generations)
    referenced = (
        {r["hash"] for g in done for r in g["references"]}
        | {h for g in done for h in g["outputs"]}
        | {i["hash"] for s in complete["asset_pack"] for i in s["asset"]["images"]}
    )
    assert {f["hash"] for f in complete["files"]} == referenced
    for generation in done:
        assert request(f"/api/generations/{generation['id']}") == generation
        for digest in generation["outputs"]:
            request("/api/files/" + digest)
    print(
        "PROOF E4 deleted asset hidden; complete package retains its deleted "
        "record and every earlier input/output; generations and outputs "
        "fetchable by id",
        flush=True,
    )
    sequence = request(cpath + "/sequence")
    assert sequence["skipped"] == [{"id": frames[1]["id"], "name": frames[1]["name"]}]
    request(cpath + "/sequence.zip")
    print(
        "PROOF E5 both frames ordered, one final, both full run snapshots; "
        "no archive file missing or extra; images-only names skipped frame",
        flush=True,
    )
    storage = request("/api/storage")
    expected = expected_storage()
    assert storage == expected
    assert counts("studio") == before
    print(
        "PROOF E6 storage equals direct stored_files and placeholder SQL sums",
        json.dumps(expected),
        "all row counts unchanged",
        json.dumps(before),
        flush=True,
    )
    # Also prove a hidden frame's run and final remain in the complete package.
    request(f"/api/variants/{frames[0]['id']}", "DELETE")
    hidden = package(cpath)
    assert hidden["frames"][0]["deleted"] and hidden["frames"][0]["final"] == final
    assert hidden["frames"][0]["runs"] == complete["frames"][0]["runs"]
    print(
        "PROOF E7 hidden frame retains run, full snapshot and final; "
        "dump restore follows",
        flush=True,
    )


if __name__ == "__main__":
    main()

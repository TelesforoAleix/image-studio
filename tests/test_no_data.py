"""All synthetic file contents are created at run time outside the repository."""

import pytest

from scripts.check_no_data import (
    DATA_EXTENSIONS,
    JSON_CONFIG_PATHS,
    MAX_BYTES,
    check_paths,
)


@pytest.mark.parametrize("extension", sorted(DATA_EXTENSIONS))
def test_data_extension(tmp_path, extension):
    name = "synthetic" + extension
    (tmp_path / name).write_bytes(b"synthetic")
    assert "data extension" in check_paths(tmp_path, [name])[0]


@pytest.mark.parametrize(
    "header",
    [
        b"%PDF",
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff",
        b"GIF87a",
        b"GIF89a",
        b"RIFF\x00\x00\x00\x00WEBP",
        b"\x00\x00\x00\x18ftypheic",
    ],
    ids=["pdf", "png", "jpeg-renamed", "gif87", "gif89", "webp", "heic"],
)
def test_signature_regardless_of_name(tmp_path, header):
    (tmp_path / "synthetic.txt").write_bytes(header)
    assert "PDF or image signature" in check_paths(tmp_path, ["synthetic.txt"])[0]


def test_unlisted_json(tmp_path):
    (tmp_path / "record.json").write_text("{}")
    assert "JSON path" in check_paths(tmp_path, ["record.json"])[0]


def test_size_limit(tmp_path):
    path = tmp_path / "large.txt"
    path.write_bytes(b"x" * MAX_BYTES)
    assert check_paths(tmp_path, [path.name]) == []
    with path.open("ab") as file:
        file.write(b"x")
    assert "larger than 1 MB" in check_paths(tmp_path, [path.name])[0]


def test_clean_tree(tmp_path):
    names = ["app.py", "README.md", *sorted(JSON_CONFIG_PATHS)]
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if name.endswith(".json") else "# code")
    assert check_paths(tmp_path, names) == []
    assert check_paths(tmp_path, []) == []


def test_allowlist_is_exact(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    assert check_paths(tmp_path, ["package.json"])


def test_symlink_and_missing_file(tmp_path):
    (tmp_path / "link.txt").symlink_to(tmp_path / "missing.txt")
    violations = check_paths(tmp_path, ["link.txt", "missing.txt"])
    assert len(violations) == 2


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.production",
        "nested/.env.example",
        "nested/.ENV",
        "frontend/dist/bundle.js",
        "node_modules/package/index.js",
        ".venv/pyvenv.cfg",
        "data/prompt.txt",
        "exports/manifest.txt",
        ".aws/credentials",
        ".ssh/config",
        "id_ed25519",
        "playwright-report/index.html",
        "test-results/result.txt",
    ],
)
def test_forbidden_paths_even_when_force_added(tmp_path, name):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic")
    assert check_paths(tmp_path, [name])


def test_root_environment_example_is_allowed(tmp_path):
    (tmp_path / ".env.example").write_text("SYNTHETIC_SETTING=\n")
    assert check_paths(tmp_path, [".env.example"]) == []


def test_renamed_binary(tmp_path):
    (tmp_path / "synthetic.txt").write_bytes(b"synthetic\x00binary")
    assert "binary file signature" in check_paths(tmp_path, ["synthetic.txt"])[0]

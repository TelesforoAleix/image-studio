"""Synthetic images only: decoding and immutable publication without a database."""

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from image_studio.files import FILE_LIMIT, decode_upload, publish_file


def image_bytes(format="PNG", color="red"):
    output = io.BytesIO()
    Image.new("RGB", (12, 9), color).save(output, format=format)
    return output.getvalue()


@pytest.mark.parametrize(
    "format,media",
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_decode_ignores_filename_and_content_type(format, media):
    data = image_bytes(format)
    decoded, info = decode_upload(
        FileStorage(
            stream=io.BytesIO(data), filename="synthetic.txt", content_type="text/plain"
        )
    )
    assert decoded == data
    assert info == {
        "hash": hashlib.sha256(data).hexdigest(),
        "media_type": media,
        "size": len(data),
        "width": 12,
        "height": 9,
    }


@pytest.mark.parametrize(
    "data,name",
    [
        (b"not an image", "synthetic.txt"),
        (b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32, "synthetic.heic"),
        (image_bytes("GIF"), "synthetic.gif"),
        (image_bytes()[:30], "broken.png"),
    ],
)
def test_reject_invalid_or_unsupported_content(data, name):
    with pytest.raises(BadRequest, match=f"{name}: upload a valid JPEG, PNG or WebP"):
        decode_upload(FileStorage(stream=io.BytesIO(data), filename=name))


def test_file_limit():
    with pytest.raises(RequestEntityTooLarge, match="large.png.*25 MB"):
        decode_upload(
            FileStorage(
                stream=io.BytesIO(b"x" * (FILE_LIMIT + 1)), filename="large.png"
            )
        )


def test_publish_once_even_concurrently(tmp_path):
    data = image_bytes()
    digest = hashlib.sha256(data).hexdigest()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: publish_file(tmp_path, digest, data), range(12)))
    path = tmp_path / digest
    before = path.stat()
    publish_file(tmp_path, digest, data)
    assert path.read_bytes() == data
    assert path.stat().st_ino == before.st_ino
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    assert list(tmp_path.iterdir()) == [path]

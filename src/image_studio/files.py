"""Decode uploads and atomically publish immutable, content-addressed bytes."""

import hashlib
import io
import os
import tempfile
import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

FILE_LIMIT = 25 * 1024 * 1024
REQUEST_LIMIT = 90 * 1024 * 1024
MEDIA_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def decode_upload(upload):
    name = upload.filename or "unnamed file"
    data = upload.stream.read(FILE_LIMIT + 1)
    if len(data) > FILE_LIMIT:
        raise RequestEntityTooLarge(f"{name}: maximum file size is 25 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in MEDIA_TYPES:
                    raise ValueError("Unsupported format")
                media_type = MEDIA_TYPES[image.format]
                width, height = image.size
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                # Decode every frame, including animated PNG/WebP uploads.
                for frame in range(getattr(image, "n_frames", 1)):
                    image.seek(frame)
                    image.load()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise BadRequest(f"{name}: upload a valid JPEG, PNG or WebP image") from error
    return data, {
        "hash": hashlib.sha256(data).hexdigest(),
        "media_type": media_type,
        "size": len(data),
        "width": width,
        "height": height,
    }


def publish_file(root: Path, digest: str, data: bytes):
    root.mkdir(parents=True, exist_ok=True)
    target = root / digest
    # Hard-link publication is atomic and never replaces an existing hash.
    # Only the unreferenced staging file is removed, never a stored file.
    with tempfile.NamedTemporaryFile(
        dir=root, prefix=".upload-", delete=False
    ) as stage:
        stage_name = stage.name
        try:
            stage.write(data)
            stage.flush()
            os.fsync(stage.fileno())
            try:
                os.link(stage_name, target)
            except FileExistsError:
                pass
        finally:
            os.unlink(stage_name)

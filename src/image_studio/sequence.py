"""Image-only ZIP streaming using the standard library, without staging files."""

import re
import unicodedata
from zipfile import ZIP_STORED, ZipFile

EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def slug(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:80] or "untitled"


class ZipSink:
    """Unseekable output adapter; ZipFile owns headers, offsets and directory."""

    def __init__(self):
        self.buffer = bytearray()
        self.offset = 0

    def write(self, data):
        self.buffer.extend(data)
        self.offset += len(data)
        return len(data)

    def tell(self):
        return self.offset

    def flush(self):
        pass

    def drain(self):
        data = bytes(self.buffer)
        self.buffer.clear()
        return data


def stream_sequence(root, entries):
    sink = ZipSink()
    with ZipFile(sink, "w", compression=ZIP_STORED) as archive:
        for entry in entries:
            with archive.open(entry["filename"], "w", force_zip64=True) as output:
                yield sink.drain()
                with (root / entry["hash"]).open("rb") as image:
                    while chunk := image.read(64 * 1024):
                        output.write(chunk)
                        yield sink.drain()
            yield sink.drain()
    yield sink.drain()

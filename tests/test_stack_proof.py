"""Validate the CI upload helper against Werkzeug's actual multipart parser."""

from werkzeug.formparser import parse_form_data
from werkzeug.test import EnvironBuilder

from scripts.check_stack import multipart, synthetic_png


def test_stack_proof_multipart_round_trip():
    originals = [synthetic_png("red"), synthetic_png("blue")]
    body, content_type = multipart(
        [("synthetic-red.png", originals[0]), ("synthetic-blue.png", originals[1])]
    )
    builder = EnvironBuilder(method="POST", data=body, content_type=content_type)
    try:
        _, form, files = parse_form_data(builder.get_environ())
        assert not form
        uploads = files.getlist("files")
        assert [file.filename for file in uploads] == [
            "synthetic-red.png",
            "synthetic-blue.png",
        ]
        assert [file.read() for file in uploads] == originals
    finally:
        builder.close()

"""Output-aligned feedback reads and snapshot-bound validation."""

from sqlalchemy import select
from werkzeug.exceptions import BadRequest

from image_studio.api import serial
from image_studio.schema import output_feedback


def empty_feedback():
    return {"verdict": None, "asset_ratings": [], "note": "", "updated_at": None}


def generation_record(connection, row):
    result = serial(row)
    saved = {
        r["output_index"]: {
            k: v
            for k, v in serial(r).items()
            if k not in ("generation_id", "output_index")
        }
        for r in connection.execute(
            select(output_feedback).where(output_feedback.c.generation_id == row["id"])
        ).mappings()
    }
    result["feedback"] = [
        saved.get(i, empty_feedback()) for i in range(len(row["outputs"]))
    ]
    return result


def validate_feedback(value, references):
    if (
        "verdict" in value
        and value["verdict"] is not None
        and value["verdict"] not in ("good", "not_good")
    ):
        raise BadRequest("verdict must be good, not_good or null")
    if "note" in value and not isinstance(value["note"], str):
        raise BadRequest("note must be text")
    if "asset_ratings" in value:
        ratings = value["asset_ratings"]
        available = {r["asset_id"] for r in references if r.get("asset_id") is not None}
        seen = set()
        if not isinstance(ratings, list):
            raise BadRequest("asset_ratings must be a list")
        for rating in ratings:
            if (
                not isinstance(rating, dict)
                or set(rating) != {"asset_id", "rating"}
                or type(rating["asset_id"]) is not int
                or rating["asset_id"] not in available
                or rating["asset_id"] in seen
                or rating["rating"] not in ("kept", "partly", "lost")
            ):
                raise BadRequest(
                    "Rate each snapshot-referenced asset at most once "
                    "with kept, partly or lost"
                )
            seen.add(rating["asset_id"])
    return value


def model_tallies(rows):
    result = {}
    for row in rows:
        tally = result.setdefault(row["model"], {"rated": 0, "good": 0})
        for feedback in row["feedback"]:
            tally["rated"] += feedback["verdict"] is not None
            tally["good"] += feedback["verdict"] == "good"
    return result

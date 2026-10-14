"""R1 rows survive richer assets upgrade twice and downgrade, in disposable CI."""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from image_studio.database import database_engine

TABLES = (
    "assets",
    "projects",
    "compositions",
    "variants",
    "composition_assets",
    "asset_images",
    "stored_files",
    "generations",
)
ADDITIONS = {
    "type",
    "preserve",
    "style_asset_id",
    "style_deselected_images",
    "selected_originals",
}


def snapshot(engine):
    with engine.connect() as c:
        return {
            table: [
                dict(r)
                for r in c.execute(
                    text(
                        f"SELECT * FROM {table} ORDER BY "
                        + ("hash" if table == "stored_files" else "id")
                    )
                ).mappings()
            ]
            for table in TABLES
        }


def main():
    config = Config("alembic.ini")
    command.upgrade(config, "0006")
    engine = database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO assets (name, type_tag, description) VALUES "
                "('Synthetic legacy person', 'character', 'Synthetic person'), "
                "('Synthetic legacy lamp', 'lamp', 'Synthetic lamp'), "
                "('Synthetic legacy unknown', 'unmapped label', 'Synthetic unknown')"
            )
        )
    before = snapshot(engine)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    after = snapshot(engine)
    assert {r["type_tag"]: r["type"] for r in after["assets"] if r["type_tag"]} == {
        "character": "person",
        "lamp": "object_vehicle",
        "unmapped label": "other",
    }
    assert {
        t: [{k: v for k, v in r.items() if k not in ADDITIONS} for r in rows]
        for t, rows in after.items()
    } == before
    assert all(r["preserve"] == "" for r in after["assets"])
    assert all(
        r["style_asset_id"] is None
        for t in ("projects", "compositions")
        for r in after[t]
    )
    print(
        "PROOF RICH MIGRATION character→person, lamp→object_vehicle, "
        "unknown→other; labels and all R1 rows retained",
        after,
        flush=True,
    )
    command.downgrade(config, "0006")
    assert snapshot(engine) == before
    print("PROOF RICH MIGRATION downgrade restores R1 unchanged", before, flush=True)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert snapshot(engine) == after
    engine.dispose()


if __name__ == "__main__":
    main()

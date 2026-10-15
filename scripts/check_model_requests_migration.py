"""R2 snapshots survive nullable request columns, upgrades twice and downgrade."""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from image_studio.database import database_engine


def snapshot(engine):
    with engine.connect() as c:
        return {
            table: [
                dict(r)
                for r in c.execute(
                    text(f"SELECT * FROM {table} ORDER BY id")
                ).mappings()
            ]
            for table in (
                "assets",
                "projects",
                "compositions",
                "variants",
                "generations",
                "asset_images",
                "composition_assets",
            )
        }


ADDITIONS = {
    "prompt_family",
    "rendered_prompt",
    "shared_references",
    "settings",
    "request_fields",
    "estimated_cost",
}


def main():
    config = Config("alembic.ini")
    command.upgrade(config, "0007")
    engine = database_engine(os.environ["DATABASE_URL"])
    before = snapshot(engine)
    command.upgrade(config, "0008")
    command.upgrade(config, "0008")
    after = snapshot(engine)
    assert {
        t: [{k: v for k, v in r.items() if k not in ADDITIONS} for r in rows]
        for t, rows in after.items()
    } == before
    assert all(all(row[k] is None for k in ADDITIONS) for row in after["generations"])
    print(
        "PROOF MODEL MIGRATION R2 rows/runs retained, nullable new fields, "
        "upgrade twice",
        after,
        flush=True,
    )
    command.downgrade(config, "0007")
    assert snapshot(engine) == before
    print("PROOF MODEL MIGRATION downgrade restores R2 unchanged", flush=True)
    command.upgrade(config, "0008")
    command.upgrade(config, "0008")
    assert snapshot(engine) == after
    engine.dispose()


if __name__ == "__main__":
    main()

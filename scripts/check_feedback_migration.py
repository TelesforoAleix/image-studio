"""R3 runs survive feedback upgrades twice and downgrade in disposable CI."""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from image_studio.database import database_engine


def snapshot(engine):
    with engine.connect() as connection:
        return {
            table: [
                dict(row)
                for row in connection.execute(
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


def main():
    config = Config("alembic.ini")
    command.upgrade(config, "0008")
    engine = database_engine(os.environ["DATABASE_URL"])
    before = snapshot(engine)
    assert before["generations"], "Proof requires existing R3-era runs"
    command.upgrade(config, "0009")
    command.upgrade(config, "0009")
    assert snapshot(engine) == before
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM output_feedback")) == 0
    print(
        "PROOF FEEDBACK MIGRATION R3 rows/runs/finals unchanged; upgrade twice; "
        "empty feedback",
        before,
        flush=True,
    )
    command.downgrade(config, "0008")
    assert "output_feedback" not in inspect(engine).get_table_names()
    assert snapshot(engine) == before
    print("PROOF FEEDBACK MIGRATION downgrade restores R3 unchanged", flush=True)
    command.upgrade(config, "0009")
    command.upgrade(config, "0009")
    assert snapshot(engine) == before
    engine.dispose()


if __name__ == "__main__":
    main()

"""U4 upgrade twice and downgrade with exact retained history on disposable CI."""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from image_studio.database import database_engine


def snapshot(engine):
    with engine.connect() as connection:
        return {
            table: list(
                connection.execute(
                    text(f'SELECT * FROM "{table}" t ORDER BY to_jsonb(t)::text')
                ).mappings()
            )
            for table in inspect(engine).get_table_names()
            if table != "alembic_version"
        }


def main():
    config = Config("alembic.ini")
    command.upgrade(config, "0011")
    engine = database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        comp = connection.scalar(
            text(
                "INSERT INTO compositions (name, kind, brief) VALUES ('Synthetic "
                "chain migration', 'storyboard', 'Synthetic') RETURNING id"
            )
        )
        frames = [
            connection.scalar(
                text(
                    "INSERT INTO variants (composition_id, position) VALUES (:id, "
                    ":position) RETURNING id"
                ),
                {"id": comp, "position": i},
            )
            for i in range(3)
        ]
        for frame in frames:
            g = connection.scalar(
                text("""INSERT INTO generations
                (kind, variant_id, run_id, model, model_info, prompt,
                 assembled_prompt, edited, "references", placeholder,
                 count, state, outputs)
                VALUES ('composition', :frame, :run, 'synthetic', '{}',
                'Synthetic retained', 'Synthetic retained', false, '[]',
                true, 1, 'done', '["synthetic-chain-output"]') RETURNING id"""),
                {"frame": frame, "run": f"synthetic-chain-{frame}"},
            )
            connection.execute(
                text(
                    "UPDATE variants SET final_generation_id = :g, final_output = 0 "
                    "WHERE id = :frame"
                ),
                {"g": g, "frame": frame},
            )
    before = snapshot(engine)
    command.upgrade(config, "head")
    after = snapshot(engine)
    assert not after["frame_sequences"]
    for table, rows in before.items():
        extra = (
            {"use_previous_frame"}
            if table == "variants"
            else {"sequence_id"}
            if table == "generations"
            else set()
        )
        assert [
            {k: v for k, v in row.items() if k not in extra} for row in after[table]
        ] == rows
    assert all(r["use_previous_frame"] for r in after["variants"])
    assert all(r["sequence_id"] is None for r in after["generations"])
    command.upgrade(config, "head")
    assert snapshot(engine) == after
    command.downgrade(config, "0011")
    assert snapshot(engine) == before
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert snapshot(engine) == after
    print(
        "PROOF CHAIN migration: U4 storyboard, runs, finals unchanged; "
        "default on; upgrade twice, downgrade restores U4, reupgrade "
        "unchanged",
        flush=True,
    )
    engine.dispose()


if __name__ == "__main__":
    main()

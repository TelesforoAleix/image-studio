"""Synthetic S8 migration proof, run in the disposable CI app before startup."""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from image_studio.database import database_engine


def snapshot(engine):
    with engine.connect() as connection:
        return {
            table: [
                dict(r)
                for r in connection.execute(
                    text(f"SELECT * FROM {table} ORDER BY id")
                ).mappings()
            ]
            for table in (
                "projects",
                "compositions",
                "assets",
                "variants",
                "generations",
            )
        }


def main():
    config = Config("alembic.ini")
    command.upgrade(config, "0005")
    engine = database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        for statement in [
            "INSERT INTO projects (name, instructions) VALUES ('Synthetic S8 "
            "folder', 'Synthetic S8 direction')",
            "INSERT INTO assets (name, project_id) VALUES ('Synthetic formerly "
            "limited asset', 1)",
            "INSERT INTO compositions (name, project_id, scene) VALUES ('Synthetic "
            "S8 single', 1, 'Synthetic scene'), ('Synthetic S8 storyboard', 1, "
            "'Synthetic scene')",
            "INSERT INTO variants (composition_id, name, position) VALUES (1, "
            "'Frame 1', 0), (2, 'Frame 1', 0), (2, 'Frame 2', 1)",
            "INSERT INTO variants (composition_id, name, position, deleted_at) "
            "VALUES (1, 'Hidden frame', 1, now())",
            """INSERT INTO generations (kind, variant_id, run_id,
                model, model_info, prompt,
                assembled_prompt, edited, "references",
                placeholder, count, state, outputs)
                VALUES ('composition', 1, 'synthetic-s8-run', 'placeholder-a', '{}',
                'Synthetic past prompt', 'Synthetic past prompt', false, '[]', true, 1,
                'done', '["synthetic-migration-output"]')""",
            "UPDATE variants SET final_generation_id = 1, final_output = 0 WHERE "
            "id = 1",
        ]:
            connection.execute(text(statement))
    before = snapshot(engine)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    after = snapshot(engine)
    assert [r["kind"] for r in after["compositions"]] == ["single", "storyboard"]
    assert all(r["direction"] == "" for r in after["compositions"])
    assert after["generations"] == before["generations"]
    assert after["variants"] == before["variants"]
    assert after["projects"] == before["projects"]
    assert [
        {k: r[k] for k in before["compositions"][0]} for r in after["compositions"]
    ] == before["compositions"]
    assert after["assets"] == [
        {k: v for k, v in r.items() if k != "project_id"} for r in before["assets"]
    ]
    print(
        "PROOF STRUCTURE migration twice: kinds single/storyboard (hidden frame "
        "excluded); project, frames, runs and final retained:",
        after,
        flush=True,
    )
    command.downgrade(config, "0005")
    restored = snapshot(engine)
    assert restored == {
        **before,
        "assets": [{**r, "project_id": None} for r in before["assets"]],
    }
    print(
        "PROOF STRUCTURE downgrade restores S8 rows; asset visibility global:",
        restored,
        flush=True,
    )
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert snapshot(engine) == after
    engine.dispose()


if __name__ == "__main__":
    main()

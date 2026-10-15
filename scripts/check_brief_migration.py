"""U3 text migration, idempotence and downgrade proof on disposable Postgres."""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from image_studio import create_app
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
    command.upgrade(config, "0009")
    engine = database_engine(os.environ["DATABASE_URL"])
    previews = {}
    with engine.begin() as connection:
        for kind, direction, scene, action in [
            ("single", "", "Synthetic scene", "Synthetic action"),
            ("single", "Synthetic direction", "", ""),
            ("storyboard", "Synthetic look", "Synthetic story", "Synthetic frame"),
            ("single", "", "", ""),
        ]:
            identifier = connection.scalar(
                text(
                    "INSERT INTO compositions (name, kind, direction, scene) "
                    "VALUES ('Synthetic brief migration', :kind, :direction, :scene) "
                    "RETURNING id"
                ),
                dict(kind=kind, direction=direction, scene=scene),
            )
            frame = connection.scalar(
                text(
                    "INSERT INTO variants (composition_id, instructions) "
                    "VALUES (:id, :action) RETURNING id"
                ),
                dict(id=identifier, action=action),
            )
            previews[frame] = "\n\n".join(p for p in [direction, scene, action] if p)
            connection.execute(
                text(
                    "INSERT INTO variants (composition_id, instructions, deleted_at) "
                    "VALUES (:id, 'Synthetic hidden action', now())"
                ),
                dict(id=identifier),
            )
            generation = connection.scalar(
                text("""INSERT INTO generations (kind, variant_id, run_id, model,
                    model_info, prompt, assembled_prompt, edited, "references",
                    placeholder, count, state, outputs)
                    VALUES ('composition', :frame, 'synthetic-brief-run', 'synthetic',
                    '{}', 'Synthetic past prompt', 'Synthetic past prompt', false,
                    '[]', true, 1, 'done', '["synthetic-brief-output"]')
                    RETURNING id"""),
                dict(frame=frame),
            )
            connection.execute(
                text(
                    "UPDATE variants SET final_generation_id = :generation, "
                    "final_output = 0 WHERE id = :frame"
                ),
                dict(generation=generation, frame=frame),
            )
    before = snapshot(engine)
    expected = []
    single_ids = {c["id"] for c in before["compositions"] if c["kind"] == "single"}
    for c in before["compositions"]:
        actions = [
            v["instructions"]
            for v in sorted(before["variants"], key=lambda v: (v["position"], v["id"]))
            if v["composition_id"] == c["id"] and v["deleted_at"] is None
        ]
        parts = [c["direction"], c["scene"]] + (
            actions if c["kind"] == "single" else []
        )
        expected.append(
            {
                **{k: v for k, v in c.items() if k not in ("direction", "scene")},
                "brief": "\n\n".join(p for p in parts if p),
            }
        )
    command.upgrade(config, "0010")
    after = snapshot(engine)
    assert sorted(after["compositions"], key=lambda r: r["id"]) == sorted(
        expected, key=lambda r: r["id"]
    )
    assert {
        k: v for k, v in after.items() if k not in ("compositions", "variants")
    } == {k: v for k, v in before.items() if k not in ("compositions", "variants")}
    assert sorted(after["variants"], key=lambda r: r["id"]) == sorted(
        [
            {**v, "instructions": ""}
            if v["composition_id"] in single_ids and v["deleted_at"] is None
            else dict(v)
            for v in before["variants"]
        ],
        key=lambda r: r["id"],
    )
    command.upgrade(config, "head")
    app = create_app()
    with app.test_client() as client:
        for frame, old_text in previews.items():
            preview = client.get(f"/api/variants/{frame}/preview")
            assert preview.status_code == 200, preview.json
            assert preview.json["prompt"] == old_text
    app.extensions["database"].dispose()
    command.downgrade(config, "0010")
    command.upgrade(config, "0010")
    assert snapshot(engine) == after
    command.downgrade(config, "0009")
    restored = snapshot(engine)
    assert sorted(restored["compositions"], key=lambda r: r["id"]) == sorted(
        [
            {
                **{k: v for k, v in c.items() if k != "brief"},
                "scene": c["brief"],
                "direction": "",
            }
            for c in after["compositions"]
        ],
        key=lambda r: r["id"],
    )
    assert {k: v for k, v in restored.items() if k != "compositions"} == {
        k: v for k, v in after.items() if k != "compositions"
    }
    command.upgrade(config, "0010")
    command.upgrade(config, "0010")
    assert snapshot(engine) == after
    print(
        "PROOF BRIEF: U3 singles/storyboard/empty, hidden frames, snapshots/finals; "
        "upgrade twice, downgrade preserves text, reupgrade unchanged",
        flush=True,
    )
    engine.dispose()


if __name__ == "__main__":
    main()

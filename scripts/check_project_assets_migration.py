"""V1 project assets backfill and downgrade on disposable Postgres only."""

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
    command.upgrade(config, "0010")
    engine = database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as c:
        subject, deleted, unused, style, own_style = [
            c.scalar(
                text(
                    "INSERT INTO assets (name, type) VALUES (:name, :type) RETURNING id"
                ),
                {"name": f"Synthetic project migration {i}", "type": kind},
            )
            for i, kind in enumerate(["other", "person", "other", "style", "style"])
        ]
        project, empty = [
            c.scalar(
                text(
                    "INSERT INTO projects (name) VALUES "
                    "('Synthetic folder') RETURNING id"
                )
            )
            for _ in range(2)
        ]
        c.execute(
            text("UPDATE projects SET style_asset_id = :style WHERE id = :project"),
            dict(style=style, project=project),
        )
        c.execute(
            text("UPDATE assets SET deleted_at = now() WHERE id = :asset"),
            dict(asset=deleted),
        )
        for deleted_comp in [False, False, True]:
            comp = c.scalar(
                text(
                    "INSERT INTO compositions "
                    "(name, project_id, style_asset_id, deleted_at) "
                    "VALUES ('Synthetic pack', :project, :style, "
                    "CASE WHEN :deleted THEN now() END) RETURNING id"
                ),
                dict(project=project, style=own_style, deleted=deleted_comp),
            )
            frame = c.scalar(
                text(
                    "INSERT INTO variants (composition_id) VALUES (:comp) RETURNING id"
                ),
                dict(comp=comp),
            )
            generation = c.scalar(
                text("""INSERT INTO generations (kind, variant_id, run_id, model,
                    model_info, prompt, assembled_prompt, edited, "references",
                    placeholder, count, state, outputs)
                    VALUES ('composition', :frame, 'synthetic-project-run',
                    'synthetic', '{}', 'Synthetic retained', 'Synthetic retained',
                    false, '[]', true, 1, 'done', '["synthetic-project-output"]')
                    RETURNING id"""),
                dict(frame=frame),
            )
            c.execute(
                text(
                    "UPDATE variants SET final_generation_id = :generation, "
                    "final_output = 0 WHERE id = :frame"
                ),
                dict(generation=generation, frame=frame),
            )
            for position, asset in enumerate([subject, deleted, unused]):
                c.execute(
                    text(
                        "INSERT INTO composition_assets "
                        "(composition_id, asset_id, role, position, active) "
                        "VALUES (:comp, :asset, 'Subject', :position, :active)"
                    ),
                    dict(
                        comp=comp,
                        asset=asset,
                        position=position,
                        active=deleted_comp or asset != unused,
                    ),
                )
    before = snapshot(engine)
    # Derive the exact complete set, including any earlier compose proofs' rows.
    expected = {
        (p["id"], p["style_asset_id"])
        for p in before["projects"]
        if p["style_asset_id"] is not None
    }
    for comp in before["compositions"]:
        if comp["project_id"] is None or comp["deleted_at"] is not None:
            continue
        expected.update(
            (comp["project_id"], a["asset_id"])
            for a in before["composition_assets"]
            if a["composition_id"] == comp["id"] and a["active"]
        )
        if comp["style_asset_id"]:
            expected.add((comp["project_id"], comp["style_asset_id"]))
    command.upgrade(config, "0011")
    after = snapshot(engine)
    assert {k: v for k, v in after.items() if k != "project_assets"} == before
    assert {
        (r["project_id"], r["asset_id"]) for r in after["project_assets"]
    } == expected
    assert {
        r["asset_id"] for r in after["project_assets"] if r["project_id"] == project
    } == {
        subject,
        deleted,
        style,
        own_style,
    }
    assert not any(r["project_id"] == empty for r in after["project_assets"])
    assert all(
        r["added_at"] and r["removed_at"] is None for r in after["project_assets"]
    )
    command.upgrade(config, "0011")
    assert snapshot(engine) == after
    command.downgrade(config, "0010")
    assert "project_assets" not in inspect(engine).get_table_names()
    assert snapshot(engine) == before
    command.upgrade(config, "0011")
    command.upgrade(config, "0011")
    restored = snapshot(engine)
    assert {k: v for k, v in restored.items() if k != "project_assets"} == before
    assert {
        (r["project_id"], r["asset_id"]) for r in restored["project_assets"]
    } == expected
    print(
        "PROOF PROJECT ASSETS migration: V1 rows unchanged; exact active pack/style "
        "backfill including deleted assets, inactive/hidden excluded, empty folder; "
        "upgrade twice, downgrade restores V1, reupgrade",
        flush=True,
    )
    engine.dispose()


if __name__ == "__main__":
    main()

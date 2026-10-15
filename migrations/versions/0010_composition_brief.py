"""One composition brief, preserving single-frame instructions and past snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "compositions",
        sa.Column("brief", sa.Text(), nullable=False, server_default=""),
    )
    op.execute("""
        UPDATE compositions AS c SET brief = concat_ws(E'\\n\\n',
            nullif(direction, ''), nullif(scene, ''),
            CASE WHEN kind = 'single' THEN (
                SELECT string_agg(v.instructions, E'\\n\\n' ORDER BY v.position, v.id)
                FROM variants AS v WHERE v.composition_id = c.id
                    AND v.deleted_at IS NULL AND v.instructions <> ''
            ) END)
    """)
    op.execute("""
        UPDATE variants AS v SET instructions = '' FROM compositions AS c
        WHERE v.composition_id = c.id AND c.kind = 'single'
            AND v.deleted_at IS NULL
    """)
    op.drop_column("compositions", "direction")
    op.drop_column("compositions", "scene")


def downgrade():
    op.add_column(
        "compositions",
        sa.Column("direction", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "compositions",
        sa.Column("scene", sa.Text(), nullable=False, server_default=""),
    )
    op.execute("UPDATE compositions SET scene = brief")
    op.drop_column("compositions", "brief")

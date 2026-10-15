"""Curated project assets, retaining removals and backfilling current usage."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_assets",
        sa.Column("project_id", sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("asset_id", sa.ForeignKey("assets.id"), primary_key=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
    )
    op.execute("""
        INSERT INTO project_assets (project_id, asset_id)
        SELECT c.project_id, ca.asset_id
        FROM compositions c JOIN composition_assets ca ON ca.composition_id = c.id
        WHERE c.project_id IS NOT NULL AND c.deleted_at IS NULL AND ca.active
        UNION
        SELECT id, style_asset_id FROM projects WHERE style_asset_id IS NOT NULL
        UNION
        SELECT project_id, style_asset_id FROM compositions
        WHERE project_id IS NOT NULL AND deleted_at IS NULL
            AND style_asset_id IS NOT NULL
    """)


def downgrade():
    op.drop_table("project_assets")

"""Create projects, assets, immutable files and image approvals."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type_tag", sa.Text()),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_assets_project_id", "assets", ["project_id"])
    op.create_table(
        "stored_files",
        sa.Column("hash", sa.String(64), primary_key=True),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "stored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "size > 0 AND width > 0 AND height > 0", name="positive_file_metadata"
        ),
    )
    op.create_table(
        "asset_images",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column(
            "file_hash",
            sa.String(64),
            sa.ForeignKey("stored_files.hash"),
            nullable=False,
        ),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(16), nullable=False, server_default="uploaded"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("asset_id", "file_hash", name="one_file_per_asset"),
        sa.CheckConstraint("source IN ('uploaded', 'generated')", name="image_source"),
    )
    op.create_index("ix_asset_images_asset_id", "asset_images", ["asset_id"])


def downgrade():
    raise RuntimeError("Destructive downgrades require an explicit recovery procedure")

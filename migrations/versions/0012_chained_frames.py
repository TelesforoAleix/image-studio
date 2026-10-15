"""Retained storyboard sequences and default-on frame continuity."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "variants",
        sa.Column(
            "use_previous_frame", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.create_table(
        "frame_sequences",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column(
            "composition_id",
            sa.Integer(),
            sa.ForeignKey("compositions.id"),
            nullable=False,
        ),
        sa.Column("frames", JSONB(), nullable=False),
        sa.Column("settings", JSONB(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="running"),
        sa.Column("current_frame", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.CheckConstraint(
            "state IN ('running', 'stopping', 'done', 'failed', 'stopped')",
            name="frame_sequence_state",
        ),
    )
    op.create_index(
        "one_active_frame_sequence",
        "frame_sequences",
        ["composition_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('running', 'stopping')"),
    )
    op.add_column(
        "generations",
        sa.Column(
            "sequence_id",
            sa.Integer(),
            sa.ForeignKey("frame_sequences.id", name="generation_sequence"),
        ),
    )
    op.create_index("ix_generations_sequence_id", "generations", ["sequence_id"])


def downgrade():
    op.drop_index("ix_generations_sequence_id", table_name="generations")
    op.drop_constraint("generation_sequence", "generations", type_="foreignkey")
    op.drop_column("generations", "sequence_id")
    op.drop_table("frame_sequences")
    op.drop_column("variants", "use_previous_frame")

"""Editable feedback for one generation output; earlier rows remain unchanged."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "output_feedback",
        sa.Column(
            "generation_id",
            sa.Integer(),
            sa.ForeignKey("generations.id"),
            primary_key=True,
        ),
        sa.Column("output_index", sa.Integer(), primary_key=True),
        sa.Column("verdict", sa.Text()),
        sa.Column("asset_ratings", JSONB(), nullable=False, server_default="[]"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "output_index BETWEEN 0 AND 3", name="feedback_output_index"
        ),
        sa.CheckConstraint("verdict IN ('good', 'not_good')", name="feedback_verdict"),
    )


def downgrade():
    op.drop_table("output_feedback")

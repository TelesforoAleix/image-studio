"""Nullable per-model request snapshots; past generations remain unchanged."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind in (
        ("prompt_family", sa.Text()),
        ("rendered_prompt", sa.Text()),
        ("shared_references", JSONB()),
        ("settings", JSONB()),
        ("request_fields", JSONB()),
        ("estimated_cost", sa.Numeric(18, 8)),
    ):
        op.add_column("generations", sa.Column(name, kind))


def downgrade():
    for name in (
        "shared_references",
        "estimated_cost",
        "request_fields",
        "settings",
        "rendered_prompt",
        "prompt_family",
    ):
        op.drop_column("generations", name)

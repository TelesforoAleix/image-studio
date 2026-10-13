"""Live ordered frames and frame-only reference deselections."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("variants", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column(
        "variants",
        sa.Column("deselected_images", JSONB, nullable=False, server_default="[]"),
    )


def downgrade():
    raise RuntimeError("Destructive downgrades require an explicit recovery procedure")

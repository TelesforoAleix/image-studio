"""Persist the budget for uncertain paid-request retries."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "image_models",
        sa.Column("listed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "generations",
        sa.Column("service_failures", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    raise RuntimeError("Destructive downgrades require an explicit recovery procedure")

"""Typed assets, preservation, style choices and explicit original selections.

Legacy tags are trimmed and matched case-insensitively as whole keywords;
all other labels become other. The original label is retained unchanged.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

KEYWORDS = {
    "person": "person people character model",
    "garment_product": "garment clothing product shoe",
    "object_vehicle": "object vehicle car lamp furniture",
    "environment": "environment background location place room",
    "style": "style look",
}


def upgrade():
    op.add_column(
        "assets", sa.Column("type", sa.Text(), nullable=False, server_default="other")
    )
    op.add_column(
        "assets", sa.Column("preserve", sa.Text(), nullable=False, server_default="")
    )
    for kind, words in KEYWORDS.items():
        op.execute(
            sa.text(
                "UPDATE assets SET type = :kind "
                "WHERE lower(trim(type_tag)) = ANY(:words)"
            ).bindparams(kind=kind, words=words.split())
        )
    for table in ("projects", "compositions"):
        op.add_column(
            table,
            sa.Column(
                "style_asset_id",
                sa.Integer(),
                sa.ForeignKey("assets.id", name=f"{table}_style_asset"),
            ),
        )
    op.add_column(
        "compositions",
        sa.Column(
            "style_deselected_images", JSONB(), nullable=False, server_default="[]"
        ),
    )
    for table in ("composition_assets", "variants"):
        op.add_column(
            table,
            sa.Column(
                "selected_originals", JSONB(), nullable=False, server_default="[]"
            ),
        )


def downgrade():
    for table in ("variants", "composition_assets"):
        op.drop_column(table, "selected_originals")
    op.drop_column("compositions", "style_deselected_images")
    for table in ("compositions", "projects"):
        op.drop_constraint(f"{table}_style_asset", table, type_="foreignkey")
        op.drop_column(table, "style_asset_id")
    op.drop_column("assets", "preserve")
    op.drop_column("assets", "type")

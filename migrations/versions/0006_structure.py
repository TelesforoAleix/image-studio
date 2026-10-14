"""Global assets and optional project folders with composition direction and kind."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("compositions", "project_id", nullable=True)
    op.add_column(
        "compositions",
        sa.Column("direction", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "compositions",
        sa.Column("kind", sa.Text(), nullable=False, server_default="single"),
    )
    op.execute("""
        UPDATE compositions SET kind = 'storyboard'
        WHERE (SELECT count(*) FROM variants
               WHERE composition_id = compositions.id AND deleted_at IS NULL) > 1
    """)
    op.create_check_constraint(
        "composition_kind", "compositions", "kind IN ('single', 'storyboard')"
    )
    op.execute("UPDATE assets SET project_id = NULL")
    op.drop_index("ix_assets_project_id", table_name="assets")
    op.drop_column("assets", "project_id")


def downgrade():
    # S8 cannot represent stand-alone compositions or a separate direction. Refuse
    # rather than discard new work; the owner's pre-slice rows satisfy this guard.
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT count(*) FROM compositions "
            "WHERE project_id IS NULL OR direction <> ''"
        )
    ):
        raise RuntimeError(
            "S8 cannot represent stand-alone compositions or direction; "
            "preserve and reconcile new work before downgrade"
        )
    op.add_column(
        "assets", sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"))
    )
    op.create_index("ix_assets_project_id", "assets", ["project_id"])
    op.drop_constraint("composition_kind", "compositions", type_="check")
    op.drop_column("compositions", "kind")
    op.drop_column("compositions", "direction")
    op.alter_column("compositions", "project_id", nullable=False)

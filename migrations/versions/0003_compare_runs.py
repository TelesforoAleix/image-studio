"""Run identity, retained retry attempts and a variant's final output."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE generations ADD COLUMN run_id VARCHAR(36)")
    op.execute("UPDATE generations SET run_id = 'legacy-' || id::text")
    op.execute("ALTER TABLE generations ALTER COLUMN run_id SET NOT NULL")
    op.execute("CREATE INDEX ix_generations_run_id ON generations (run_id)")
    op.execute(
        "ALTER TABLE generations ADD COLUMN retry_of INTEGER REFERENCES generations(id)"
    )
    op.execute("ALTER TABLE variants ADD COLUMN final_generation_id INTEGER")
    op.execute(
        "ALTER TABLE variants ADD CONSTRAINT variant_final_generation "
        "FOREIGN KEY (final_generation_id) REFERENCES generations(id)"
    )
    op.execute("ALTER TABLE variants ADD COLUMN final_output INTEGER")
    op.execute(
        "ALTER TABLE variants ADD CONSTRAINT variant_final_pair CHECK "
        "((final_generation_id IS NULL AND final_output IS NULL) OR "
        "(final_generation_id IS NOT NULL AND final_output IS NOT NULL "
        "AND final_output >= 0))"
    )


def downgrade():
    raise RuntimeError("Destructive downgrades require an explicit recovery procedure")

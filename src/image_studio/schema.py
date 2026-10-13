"""SQLAlchemy definitions; only Alembic creates or changes these tables."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
projects = Table(
    "projects",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("name", Text, nullable=False),
    Column("instructions", Text, nullable=False, server_default=""),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
)
assets = Table(
    "assets",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("name", Text, nullable=False),
    Column("type_tag", Text),
    Column("description", Text, nullable=False, server_default=""),
    Column("project_id", ForeignKey("projects.id"), index=True),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column("deleted_at", DateTime(timezone=True)),
)
stored_files = Table(
    "stored_files",
    metadata,
    Column("hash", String(64), primary_key=True),
    Column("media_type", String(32), nullable=False),
    Column("size", BigInteger, nullable=False),
    Column("width", Integer, nullable=False),
    Column("height", Integer, nullable=False),
    Column(
        "stored_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    CheckConstraint(
        "size > 0 AND width > 0 AND height > 0", name="positive_file_metadata"
    ),
)
asset_images = Table(
    "asset_images",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("asset_id", ForeignKey("assets.id"), nullable=False, index=True),
    Column("file_hash", ForeignKey("stored_files.hash"), nullable=False),
    Column("approved", Boolean, nullable=False, server_default=text("false")),
    Column("rejected", Boolean, nullable=False, server_default=text("false")),
    Column("source", String(16), nullable=False, server_default="uploaded"),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    UniqueConstraint("asset_id", "file_hash", name="one_file_per_asset"),
    CheckConstraint("source IN ('uploaded', 'generated')", name="image_source"),
)

compositions = Table(
    "compositions",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("project_id", ForeignKey("projects.id"), nullable=False, index=True),
    Column("name", Text, nullable=False),
    Column("scene", Text, nullable=False, server_default=""),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column("deleted_at", DateTime(timezone=True)),
)
composition_assets = Table(
    "composition_assets",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("composition_id", ForeignKey("compositions.id"), nullable=False, index=True),
    Column("asset_id", ForeignKey("assets.id"), nullable=False),
    Column("role", Text, nullable=False),
    Column("position", Integer, nullable=False),
    Column("deselected_images", JSONB, nullable=False, server_default="[]"),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    UniqueConstraint("composition_id", "asset_id", name="one_asset_per_composition"),
)
variants = Table(
    "variants",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("composition_id", ForeignKey("compositions.id"), nullable=False, index=True),
    Column("name", Text, nullable=False, server_default="Frame 1"),
    Column("instructions", Text, nullable=False, server_default=""),
    Column("position", Integer, nullable=False, server_default="0"),
)
generations = Table(
    "generations",
    metadata,
    Column("id", Integer, Identity(), primary_key=True),
    Column("kind", Text, nullable=False),
    Column("variant_id", ForeignKey("variants.id"), index=True),
    Column("asset_id", ForeignKey("assets.id"), index=True),
    Column("model", Text, nullable=False),
    Column("model_info", JSONB, nullable=False),
    Column("prompt", Text, nullable=False),
    Column("assembled_prompt", Text, nullable=False),
    Column("edited", Boolean, nullable=False),
    Column("references", JSONB, nullable=False),
    Column("placeholder", Boolean, nullable=False),
    Column("count", Integer, nullable=False),
    Column("state", Text, nullable=False, server_default="waiting"),
    Column("outputs", JSONB, nullable=False, server_default="[]"),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("error", Text),
    CheckConstraint(
        "state IN ('waiting', 'running', 'done', 'failed')", name="generation_state"
    ),
    CheckConstraint("count BETWEEN 1 AND 4", name="generation_count"),
    CheckConstraint(
        "(kind = 'composition' AND variant_id IS NOT NULL "
        "AND asset_id IS NULL) OR (kind = 'asset_reference' "
        "AND asset_id IS NOT NULL AND variant_id IS NULL)",
        name="generation_owner",
    ),
)

image_models = Table(
    "image_models",
    metadata,
    Column("name", Text, primary_key=True),
    Column("info", JSONB, nullable=False),
    Column(
        "read_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
)

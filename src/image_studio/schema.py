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
    Column("source", String(16), nullable=False, server_default="uploaded"),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    UniqueConstraint("asset_id", "file_hash", name="one_file_per_asset"),
    CheckConstraint("source IN ('uploaded', 'generated')", name="image_source"),
)

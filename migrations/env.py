"""Database URL comes only from the environment, never migration configuration."""

import os

from alembic import context

from image_studio.database import database_engine
from image_studio.schema import metadata

engine = database_engine(os.environ["DATABASE_URL"])
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()

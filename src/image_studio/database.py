"""Use Psycopg 3 explicitly for SQLAlchemy and Alembic."""

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def database_engine(url):
    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+psycopg")
    return create_engine(parsed, pool_pre_ping=True)

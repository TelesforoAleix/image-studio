"""Idempotent library job-schema initialization after Alembic."""

import os

from image_studio.jobs import ensure_job_schema

if __name__ == "__main__":
    ensure_job_schema(os.environ["DATABASE_URL"])

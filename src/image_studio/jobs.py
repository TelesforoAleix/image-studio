"""Procrastinate owns dispatch, locking and retries; studio owns generation records."""

import asyncio
import logging
import os
from pathlib import Path

import procrastinate
import psycopg
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from werkzeug.exceptions import HTTPException

from image_studio.database import database_engine
from image_studio.files import publish_file
from image_studio.image_client import EndpointUnavailable, ImageClient, ModelFailure
from image_studio.schema import asset_images, generations, stored_files


class ServiceRetry(procrastinate.BaseRetryStrategy):
    def get_retry_decision(self, *, exception, job):
        if isinstance(exception, EndpointUnavailable):
            return procrastinate.RetryDecision(
                retry_in={"seconds": min(300, 10 * 2 ** min(job.attempts, 5))}
            )
        return None


def create_queue(url, *, asynchronous=False):
    connector = (
        procrastinate.PsycopgConnector
        if asynchronous
        else procrastinate.SyncPsycopgConnector
    )(conninfo=url.replace("postgresql+psycopg://", "postgresql://", 1))
    app = procrastinate.App(connector=connector)

    @app.task(
        name="studio.generate",
        queue="images",
        lock="studio-image-endpoint",
        retry=ServiceRetry(),
    )
    async def generate(generation_id):
        await asyncio.to_thread(process_generation, generation_id, url)

    @app.periodic(cron="* * * * *")
    @app.task(name="studio.recover", queue="images")
    async def recover(timestamp):
        for job in await app.job_manager.get_stalled_jobs(task_name="studio.generate"):
            await app.job_manager.retry_job(job)

    return app


def ensure_job_schema(url):
    # Serialize start-up without printing credentials. Library owns all schema SQL.
    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1)) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(8200002)")
        exists = connection.execute(
            "SELECT to_regclass('procrastinate_jobs')"
        ).fetchone()[0]
        if not exists:
            connection.execute(procrastinate.schema.SchemaManager.get_schema())


def defer(connection, identifier):
    app = create_queue("")
    # Same Psycopg transaction as the generation insert: neither can be orphaned.
    app.configure_task(
        "studio.generate", connection=connection.connection.driver_connection
    ).defer(generation_id=identifier)


def process_generation(identifier, url, *, client=None, root=None):
    engine = database_engine(url)
    root = root or Path(os.environ.get("STUDIO_FILES", "data/files"))
    client = client or ImageClient(
        os.environ.get("IMAGE_API_BASE_URL", ""), os.environ.get("IMAGE_API_KEY", "")
    )

    def change(**values):
        with engine.begin() as connection:
            connection.execute(
                update(generations)
                .where(generations.c.id == identifier)
                .values(**values)
            )

    try:
        with engine.begin() as connection:
            row = (
                connection.execute(
                    select(generations).where(generations.c.id == identifier)
                )
                .mappings()
                .one()
            )
            if row["state"] in ("done", "failed"):
                return
            snapshot = dict(row)
            connection.execute(
                update(generations)
                .where(generations.c.id == identifier)
                .values(
                    state="running",
                    started_at=func.now(),
                    attempts=generations.c.attempts + 1,
                    error=None,
                )
            )
        try:
            # Each call is n=1; completed outputs survive retries.
            outputs = list(snapshot["outputs"])
            while len(outputs) < snapshot["count"]:
                data, file = client.generate(snapshot, root)
                publish_file(root, file["hash"], data)
                with engine.begin() as connection:
                    connection.execute(
                        insert(stored_files).values(**file).on_conflict_do_nothing()
                    )
                    if snapshot["kind"] == "asset_reference":
                        connection.execute(
                            insert(asset_images)
                            .values(
                                asset_id=snapshot["asset_id"],
                                file_hash=file["hash"],
                                source="generated",
                            )
                            .on_conflict_do_nothing()
                        )
                    outputs.append(file["hash"])
                    connection.execute(
                        update(generations)
                        .where(generations.c.id == identifier)
                        .values(outputs=outputs)
                    )
            change(state="done", finished_at=func.now(), error=None)
        except EndpointUnavailable as error:
            change(state="waiting", error=str(error))
            raise
        except (ModelFailure, HTTPException) as error:
            change(state="failed", finished_at=func.now(), error=str(error))
        except OSError:
            change(
                state="failed",
                finished_at=func.now(),
                error="Could not read or store an image file",
            )
    finally:
        engine.dispose()


async def run():
    url = os.environ["DATABASE_URL"]
    ensure_job_schema(url)
    app = create_queue(url, asynchronous=True)
    async with app.open_async():
        # Recover jobs whose process disappeared, using the library's heartbeat checks.
        for job in await app.job_manager.get_stalled_jobs(task_name="studio.generate"):
            await app.job_manager.retry_job(job)
        await app.run_worker_async(queues=["images"], concurrency=1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())

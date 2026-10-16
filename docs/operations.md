# Operations

## Compose deployment

Compose runs `app`, `worker`, and `postgres`; the `placeholder` service is enabled with the placeholder profile. The application port is bound to loopback, and PostgreSQL has no published port. The app applies Alembic migrations and initializes Procrastinate's library-owned schema during startup. Use persistent storage for both PostgreSQL data and immutable image files. Empty `POSTGRES_DATA_PATH` and `STUDIO_FILES_PATH` select named volumes; set them to deployment-specific directories when bind mounts are needed.

The Compose configuration expects an external Docker network named `homelab-models` for access to the configured image endpoint. Create the network before bringing up the stack if it does not exist. The placeholder service is available to Compose through the `placeholder` profile. The optional `tunnel` profile runs cloudflared; protect any externally reachable route with an authenticating proxy and keep `TUNNEL_TOKEN` secret.

## Health and logs

The app health endpoint is `/api/health`; it reports PostgreSQL connectivity and returns HTTP 503 when the database is unavailable. Compose health checks gate worker startup on the app becoming healthy. Review app, worker and placeholder logs through Docker Compose without printing environment dumps or resolved Compose configuration, which may expose credentials.

## Dumps and restore

Use PostgreSQL's `pg_dump` custom format for database backups. Preserve a matching copy of the immutable files directory; a database dump alone does not contain image bytes. Do not overwrite or remove content-addressed files as part of restore.

Verify a dump by restoring it into a new scratch database and checking its tables and row counts. Keep the active database unchanged during verification. For recovery, stop writes, preserve the current database, restore into a new database, verify it, and plan a deliberate cutover. Retain multiple known-good dumps and test the restore procedure periodically.

`deploy/dump.py` is the repository's dump helper. It writes through a temporary file and atomically renames a successful dump; concurrent invocations serialize, and older dumps are pruned only after a successful dump. CI exercises dump restore against disposable services. Do not remove persistent volumes as part of ordinary shutdown.

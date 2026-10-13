# image studio

A personal web application for making visually consistent AI-generated images.
Reusable assets combine into compositions inside projects, with ordered variants
compared side by side and one result selected per frame; a separate platform
creates the images over HTTP. This repository holds code only; user work lives
outside it.

The current skeleton serves an empty asset library and `/api/health`. No image
models are called and no user data is stored by the app yet.

## Local checks

Use Python 3.13, uv, and Node 24 or newer. Containers are tested in CI; no
container runtime is needed for local checks.

```sh
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_no_data.py
cd frontend
npm ci
npm run build
```

The guard examines tracked files from `git ls-files`. Tests create synthetic
contents at run time and never use committed image or data fixtures.

## Start on a Linux host

With Docker Compose installed, copy `.env.example` to `.env` and replace the
placeholder with a randomly generated hex password. Keep `.env` outside git;
hex characters also keep the database URL safe from reserved URL characters.

```sh
cp .env.example .env
# Edit .env before starting.
docker compose up -d --build --wait --wait-timeout 120
```

Open `http://127.0.0.1:8200/` on the host. Only this loopback port is published;
Postgres 17 has no published port. The app runs as an unprivileged user and
serves both the React build and API on one origin. `/api/health` returns
`{"postgres": "ok"}` when Postgres is reachable, or HTTP 503 otherwise. Unknown
API routes return a JSON 404.

`DATABASE_URL` and `FRONTEND_DIST` configure the Flask app through its environment;
Compose supplies the database URL, and the container sets the built-file path.
Postgres persists in the `postgres-data` named volume. Stop the stack with
`docker compose down`, which preserves that volume. CI alone removes its
throwaway volume after verifying the page, health and unknown API route.

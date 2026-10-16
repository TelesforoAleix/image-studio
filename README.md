# Image Studio

Image Studio is a self-hosted web app for creating consistent images from reusable
visual assets. Build single images or storyboards inside optional projects, generate
with one to three image models side by side, review and select finals, and export
portable packages.

## Features

- Reusable people, garments and products, objects and vehicles, environments, and style assets, with descriptions, preservation rules, and approved references.
- Single image compositions and ordered storyboards, including frames that can use the previous frame as a reference.
- Optional projects for shared creative direction and curated asset navigation.
- Per-model prompt previews, settings and references; queued runs retain exact inputs and partial successes.
- Compare results, rate outputs, choose finals, and revisit complete generation history.
- Stream asset and composition packages, plus storyboard sequences, on request.

## How it works

The app is a Flask JSON API and React 19/Vite interface served by Gunicorn from one
container and one origin. PostgreSQL 17 stores records through SQLAlchemy Core; Alembic
owns schema changes. A Procrastinate worker processes the generation queue. The browser
never receives the image endpoint key. The app has no login, so put it behind an
authenticating proxy.

Compose runs the API and front end together as `app`. The worker uses the same database
and file volume. PostgreSQL is private to the Compose network, and the optional
placeholder service is enabled with its profile.

The configured image endpoint is OpenAI-compatible and supplies `/model/info` with image
model names and capability profiles. The app uses those names and profiles to render
prompts, references, settings, prices and request fields, and calls the advertised
endpoint shape. Set the endpoint base URL (including `/v1`) and optional bearer key in
the server environment. A placeholder image service is provided for local use and CI.

Uploaded and generated image bytes live outside the database in immutable files named by
SHA-256. PostgreSQL records metadata and links assets to those files. Generations
preserve their prompt, model metadata, settings and ordered reference inputs; rows and
files are retained. Exports stream ZIP packages without writing storage or changing
records.

Uploads accept JPEG, PNG and WebP based on decoded bytes. A file can be up to 25 MiB; a
complete multipart request can be up to 90 MiB. Identical bytes share one stored file.
Approved, non-rejected images are canonical references, while original uploads remain
available for review.

The JSON API covers projects, assets, compositions, frames, model discovery, runs,
generations, storage summaries and exports. Image uploads use multipart requests.
Unknown API routes return JSON 404 responses. See the topic guides for the full workflow
and package details.

See [workflows](docs/workflows.md), [architecture](docs/architecture.md), [data and
formats](docs/data-and-formats.md), and [operations](docs/operations.md) for details.

## Run locally

Prerequisites: Docker Compose, Git, and a Docker network shared with the configured
model endpoint. The default `.env.example` points to the local placeholder service. The
shared external network is named `homelab-models` by default; create it once if it does
not already exist.

```sh
cp .env.example .env
```

Replace `POSTGRES_PASSWORD` in `.env` with a randomly generated hex password. Keep
`.env` out of Git. Then start the stack with the placeholder profile:

```sh
docker network create homelab-models
docker compose --profile placeholder up -d --build --wait --wait-timeout 120
```

If the shared network already exists, the create command may report that; continue with
Compose. Open <http://127.0.0.1:8200/>. The app publishes only on loopback; PostgreSQL
has no published port. Check readiness at <http://127.0.0.1:8200/api/health>.

To stop the stack while retaining the named database and file volumes:

```sh
docker compose down
```

## Configuration

Values below are the Compose inputs from `.env.example` and `compose.yaml`.

| Variable | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | Required PostgreSQL password; Compose builds the app database URL from it. |
| `STUDIO_FILES_PATH` | Optional host directory bind-mounted for immutable image files; empty uses the named `studio-files` volume. |
| `POSTGRES_DATA_PATH` | Optional host directory bind-mounted for PostgreSQL data; empty uses the named `postgres-data` volume. |
| `COMPOSE_PROFILES` | Optional profile selection, such as `placeholder` for local use or `tunnel` for the configured tunnel service. |
| `TUNNEL_TOKEN` | Token required by the optional `tunnel` profile. Keep it secret. |
| `IMAGE_API_BASE_URL` | Image endpoint base URL, including `/v1`; use `http://placeholder:8300/v1` with the placeholder profile. |
| `IMAGE_API_KEY` | Optional bearer key for the image endpoint; it stays server-side. |
| `DATABASE_URL` | Set by Compose for the app and worker using `POSTGRES_PASSWORD`; the endpoint is PostgreSQL on the Compose network. |

The app container uses `/app/files` for immutable files and `/app/static` for the built
front end. The development defaults for file storage and front-end assets are
`data/files` and `frontend/dist`.

The Dockerfile builds the front end and Python application into one image. At startup,
the app applies Alembic migrations and initializes Procrastinate's library-owned schema
before Gunicorn starts serving requests.

## Development and checks

Local Python checks require Python 3.13 and uv. Front-end checks require Node 24 or
newer. Database integration tests use a disposable test database when configured and
skip otherwise.

```sh
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_no_data.py
cd frontend
npm ci
npm run build
npx playwright install chromium
npm run check
```

`npm run check` runs Playwright checks against synthetic intercepted API responses; it
does not need a backend or call image models. CI has `test` and `compose` jobs. The
`test` job runs Python checks, front-end build and browser checks, deployment unit
validation, the no-data-files guard and gitleaks. The `compose` job builds and exercises
the container stack, migrations, generation workflows, persistence and dump restore
using disposable services and volumes.

For interface development, run `npm run dev` from `frontend/`. The API still needs a
configured database and image endpoint, or the Compose stack. Python dependencies and
the Docker runtime target Python 3.13; the front end targets Node 24.

Tests avoid committed media. Python tests build synthetic image bytes at runtime, and
browser checks use intercepted synthetic API responses. Database integration tests use
isolated schemas or a disposable database when configured.

The Python checks can also be run separately:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_no_data.py
```

The front-end checks can be run separately from `frontend/`:

```sh
npm ci
npm run build
npx playwright install chromium
npm run check
```

## Deploying

Run the app behind an authenticating proxy and keep its published port on loopback. Do
not publish a database port. Keep `.env` and all credentials outside Git; supply the
model endpoint base URL and key through the server environment. Use persistent storage
for PostgreSQL and the immutable files directory. Choose directories appropriate to your
deployment and ensure the container user can access them.

Back up PostgreSQL with `pg_dump` and preserve the matching immutable files directory.
Restore a dump into a new database for verification before planning a cutover. See
[operations](docs/operations.md) for the Compose services, dump and restore
considerations.

## Repository contents and licence

This repository contains code, configuration and documentation only. Never add images
(uploaded, reference, generated or screenshots), data files, prompts or real records,
database dumps, exports, model weights, application state, secrets or `.env` files. Do
not add personal paths, private addresses, hostnames or account names. CI checks tracked
files with the no-data-files guard and scans for secrets with gitleaks.

Image Studio is licensed under the [MIT License](LICENSE).

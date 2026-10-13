# image studio

A personal web application for making visually consistent AI-generated images.
Reusable assets combine into compositions inside projects, with ordered variants
compared side by side and one result selected per frame; a separate platform
creates the images over HTTP. This repository holds code only; user work lives
outside it.

The app manages projects with shared creative instructions and a reusable asset
library. Assets have descriptions, optional type tags, global or project visibility,
and uploaded images that can be approved as canonical references. Duplicate assets
share their files and approvals; deletion hides assets while preserving their rows
and files. No image models are called.

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

Database integration tests use real Postgres. Set `TEST_DATABASE_URL` to a disposable
test database to run them; without it, they skip cleanly. Each test creates its own
schema, runs `alembic upgrade head` twice, and removes only that test schema.
The normal app database is never used by these tests.

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

The app reads these environment variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | Postgres connection URL; also required by Alembic | Unset (health returns 503) |
| `STUDIO_FILES` | Immutable files directory, outside git and the container image | `data/files` locally; `/app/files` in the container |
| `FRONTEND_DIST` | Built React files | `frontend/dist` locally; `/app/static` in the container |

Compose supplies `DATABASE_URL` using `POSTGRES_PASSWORD` from `.env`. The container
runs `alembic upgrade head` before starting Gunicorn. Every later schema change must
be an Alembic migration. Postgres persists in `postgres-data`, and images persist in
`studio-files`; both are named volumes. `docker compose down` preserves both. CI
alone removes its throwaway volumes after verifying persistence through an app restart.

Uploads accept JPEG, PNG and WebP, determined by Pillow decoding the bytes, regardless
of filename or browser content type. HEIC/HEIF and other content are refused with a
JSON 400 naming the file and asking for JPEG, PNG or WebP. The browser file picker
advertises these three formats. Limits are 25 MiB per file and 90 MiB per complete
request, including multipart overhead, with JSON 413 errors. Pillow's decompression
bomb protection is retained. Accepted bytes are stored unchanged under their SHA-256;
repeated bytes share one stored file. File metadata lives in Postgres.

The text and form interface uses `#library`, `#projects` and `#asset/<id>` routes.
The API uses JSON, except multipart uploads with one or more `files` fields:

| Routes | Methods / behaviour |
| --- | --- |
| `/api/projects` | GET list, POST create (`name`, `instructions`) |
| `/api/projects/<id>` | GET read, PATCH edit |
| `/api/assets` | GET list, POST create (`name`, `type_tag`, `description`, `project_id`) |
| `/api/assets/<id>` | GET with images, PATCH edit, DELETE soft-delete |
| `/api/assets/<id>/duplicate` | POST copy fields, visibility and image approvals |
| `/api/assets/<id>/images` | POST multipart upload |
| `/api/assets/<id>/images/<image-id>` | PATCH `{"approved": true}` or `false` |
| `/api/files/<sha256>` | GET original bytes with stored media type and immutable caching |

A null `project_id` means global visibility. List filtering accepts `type_tag` and
`project_id` (a project ID includes global assets plus that project's assets;
`global` shows only global assets). Assets are live by default; `include_deleted=true`
includes deleted assets in list and read responses. Deleted assets cannot be edited,
duplicated or uploaded to, but their files remain fetchable. Unknown files return JSON
404. The app has no login; keep its published port on loopback and use Cloudflare
Access to gate the server's tunnel hostname.

## Running on the server

The encrypted volume is mounted at `/srv/homelab`. Unlocking it starts
`homelab-data.target`; the studio and its dump timer are enabled under that target,
so they wait for the volume after boot. Nothing pulls that target into boot.
The root-owned clone is `/srv/homelab/image-studio`. Data lives separately:

| Path under `/srv/homelab/image-studio-data/` | Purpose / permissions |
| --- | --- |
| `originals/` | Weekly encrypted copy includes this real directory; root:10001, mode 2770 |
| `originals/files/` | Immutable image files, mounted at `/app/files`; root:10001, mode 2770 |
| `originals/db/` | Daily database dumps; root:root, mode 0750, dumps mode 0640 |
| `postgres/` | Live Postgres data; initially root:root, mode 0700; the image manages its owner |

Create these directories on the mounted volume before starting. Keep all studio
files on that volume except the installed systemd units. The weekly copy already
includes every real `*-data/originals` directory; it needs no configuration change.

The clone's ignored `.env` must be root:root, mode 0600. Generate a hex database
password directly into it on the server and move the owner-supplied tunnel token
into it without displaying either value; remove the original token file after
the move. `.env.example` documents the variables:

| Variable | Server value |
| --- | --- |
| `POSTGRES_PASSWORD` | Generated random hex password |
| `STUDIO_FILES_PATH` | `/srv/homelab/image-studio-data/originals/files` |
| `POSTGRES_DATA_PATH` | `/srv/homelab/image-studio-data/postgres` |
| `COMPOSE_PROFILES` | `tunnel` |
| `TUNNEL_TOKEN` | Owner-supplied tunnel token |

Empty storage variables select the existing named volumes for local use and CI.
The tunnel profile runs pinned `cloudflared`, sharing a separate network with
`app`, reachable there as `app:8200`. Postgres stays on the other network. Configure
the public tunnel route to that service and protect the whole hostname with an
owner-only Cloudflare Access application before enabling it. The only published
port remains `127.0.0.1:8200`; Postgres publishes none. Never print `docker compose
config` or container environment details on the server: they contain secrets.

After reviewing the deployment on `main`, install and enable the units:

```sh
cd /srv/homelab/image-studio
sudo systemd-analyze verify deploy/image-studio.service deploy/image-studio-dump.service deploy/image-studio-dump.timer
sudo install -o root -g root -m 0644 deploy/image-studio.service deploy/image-studio-dump.service deploy/image-studio-dump.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now image-studio.service
sudo systemctl enable --now image-studio-dump.timer
```

The service attempts a fast-forward pull of `main`, then builds and starts Compose;
stopping it runs `compose down` without deleting data. It follows the volume target
and starts after the existing homelab service. Check `/api/health` on the local
published port, container health and mount permissions. Do not create test records
or uploads on the server.

The timer runs at 03:30 in the server's timezone, with missed runs caught up by
`Persistent=true`. Its service skips unless the studio service is active.
`deploy/dump.py` invokes `pg_dump --format=custom`, writes through a temporary file,
and atomically renames it to `originals/db/studio-YYYY-MM-DD.dump`, mode 0640.
Concurrent runs serialize with a file lock. A rerun replaces that day's dump;
only after a successful dump are older dumps removed, keeping the seven newest
dates. Image files are never removed. Run a dump and inspect the schedule with:

```sh
sudo systemctl start image-studio-dump.service
systemctl list-timers image-studio-dump.timer
```

To check a dump, restore into a new scratch database, leaving `studio` alone:

```sh
sudo docker compose exec -T postgres createdb -U studio studio_restore_check
sudo sh -c 'docker compose exec -T postgres pg_restore -U studio -d studio_restore_check --exit-on-error < /srv/homelab/image-studio-data/originals/db/studio-YYYY-MM-DD.dump'
sudo docker compose exec -T postgres psql -U studio -d studio_restore_check -c '\dt'
sudo docker compose exec -T postgres dropdb -U studio studio_restore_check
```

For actual recovery, stop app and tunnel writes first, preserve the current database,
restore to a new database, verify it, and arrange an explicit maintenance cutover.
Pair the dump with its copied immutable files; never overwrite or delete images.
CI runs the same dump script in a temporary directory and proves a scratch restore
has exactly the source tables and row counts.

To remove the deployment while retaining its data for recovery:

```sh
sudo systemctl disable --now image-studio-dump.timer image-studio.service
sudo rm /etc/systemd/system/image-studio.service /etc/systemd/system/image-studio-dump.service /etc/systemd/system/image-studio-dump.timer
sudo systemctl daemon-reload
```

This also rolls back a failed startup. The clone, `.env`, images, Postgres directory
and dumps remain on the encrypted volume. Removing those, or volumes from a local
deployment, requires explicit owner approval after verifying a recoverable copy;
never run `compose down -v` on the server. Leave other projects and the volume
unlock chain untouched.

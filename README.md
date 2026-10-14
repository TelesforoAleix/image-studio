# image studio

A personal web application for making visually consistent AI-generated images.
Global assets combine into stand-alone compositions or project storyboards,
with ordered frames and retained generation history. A separate endpoint creates
the images over HTTP. This repository holds code only; user work lives
outside it.

The app manages projects with shared creative instructions and a reusable asset
library. All assets are global, with fixed types, descriptions, preservation rules, optional labels,
and uploaded images that can be approved as canonical references. Duplicate assets
share their files and approvals; deletion hides assets while preserving their rows
and files. Compositions and asset reference views can queue image generations.

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
# Create once for local/CI use; the shared network already exists on the server.
docker network create homelab-models
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

The top-level sections are **Assets**, **Compositions** and **Projects**; Storage
is a secondary link. Routes are `#assets`, `#asset/<id>`, `#compositions`,
`#composition/<id>/frame/<frame-id>/<setup|generate|history>`, `#projects`,
`#project/<id>` and `#storage`. `#library` redirects to Assets; `#frame/<id>`
redirects to that frame's composition Setup tab. Opening `#composition/<id>`
selects its first live frame and Setup.

A project is a folder with creative direction. Its page lists compact composition
rows and links to `#assets?used_by_project=<id>` for assets used by its live
compositions. The Compositions section lists every live composition with its kind,
project (or “No project”), first ordered final image or latest output thumbnail,
and last generation activity (creation time before any runs), filterable by project.
New compositions choose single or storyboard and an optional project. Singles hold
one live frame. Turn a single into a storyboard to add frames; a storyboard can
return to single only with one live frame.

The composition header holds name, kind, changeable project, export buttons,
Duplicate and inline Delete. Storyboards also show ordered frames with final
thumbnails, selection, add, reorder and inline deletion. One tab is shown at a time:
Setup edits direction, scene, shared asset pack and selected frame instructions and
reference toggles; Generate shows per-model rendered/editable prompts, format, priced quality or
resolution, Advanced settings, cost estimates, pinned reuse and newly queued runs; History shows that frame's runs,
snapshots, finals, reuse and retry. Reuse opens Generate. Duplicate copies composition
fields, retained pack selections and live frames without runs, generations or finals.

The API uses JSON, except multipart uploads with one or more `files` fields:

| Routes | Methods / behaviour |
| --- | --- |
| `/api/projects` | GET list, POST create (`name`, `instructions`, optional `style_asset_id`) |
| `/api/projects/<id>` | GET read, PATCH edit |
| `/api/assets` | GET list, POST create (`name`, `type`, `type_tag`, `description`, `preserve`) |
| `/api/assets/<id>` | GET with images, PATCH edit, DELETE soft-delete |
| `/api/assets/<id>/duplicate` | POST copy fields and image approvals |
| `/api/assets/<id>/images` | POST multipart upload |
| `/api/assets/<id>/images/<image-id>` | PATCH `{"approved": true}` or `false` |
| `/api/files/<sha256>` | GET original bytes with stored media type and immutable caching |

Assets expose no visibility field or control. List filtering accepts `type`, `type_tag` and
`used_by_project` (only assets actively used by that project's live compositions).
Assets are live by default; `include_deleted=true`
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
| `IMAGE_API_BASE_URL` | `http://litellm:4000/v1` |
| `IMAGE_API_KEY` | `unused` (the hosted route ignores it) |
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

## First generation

Compositions optionally belong to projects, each starting with a variant named **Frame 1**. Add global
assets with a role, toggle their approved reference images, and write scene and
frame instructions. The fixed shared template combines project instructions (when
present), composition direction, style, scene, asset roles/names/types/descriptions
and preservation rules, then frame instructions. Empty parts are omitted; past
snapshots are never rewritten. Each model's preview renders this shared intent and
ordered references in its family's notation. Edit replaces only that model's
prompt; Reset restores its rendering. Choose one to three image models, each with
one to four outputs, a shared format and each model's priced quality or resolution.
One press of Generate creates a run retaining each model's exact inputs and settings.
Results appear in model columns with paid and placeholder badges, licence and prices; failures keep
their error beside successful outputs. Every result remains in history.
On an asset page, Generate reference views uses its uploaded photos; generated
candidates can be approved or rejected individually. Rejected candidates are hidden
by default, with a toggle to show them; their attachments and files remain stored.

Generations preserve shared content, rendered prompt, prompt actually sent, family,
edit flag, settings, estimated cost, request fields, model name and metadata,
ordered reference hashes with asset descriptions and roles,
output hashes, state, attempts, service failure count, error and timestamps. Later asset edits and approval
changes never alter these snapshots. Generations have no delete endpoint. Placeholder
trial generations carry `placeholder: true` so a later deliberate cleanup can identify
them. This slice provides no cleanup command.

The `worker` service uses Procrastinate and the same Postgres database and immutable
files volume as `app`. App startup applies Alembic, then initializes Procrastinate's
library-owned schema idempotently under a database lock. The worker runs one generation
at a time, enforced by concurrency one and a common Procrastinate lock. Each generation
has one job; its one to four outputs are obtained by sequential `n=1` calls, preserving
completed outputs before any retry. Jobs transition waiting → running → done, or failed.
Connection refusal and DNS failures retry indefinitely with delays of
10, 20, 40, 80, 160, then 300 seconds. Timeouts and service 5xx retry at most twice
more, then fail with the status (or timeout description); a paid request may already
have run. The migrated `service_failures` counter preserves this limit across worker
restarts and is independent of connection-only attempts. Completed outputs stay retained.
HTTP 402 fails on the first attempt with “Monthly image budget reached — resets on the
1st (UTC)”. All other 4xx fail immediately with their status. Malformed image responses
and unsupported profiles are terminal. Calls allow 360 seconds per image; worker
shutdown allows 400 seconds. Compose uses an init process to forward stop signals
during startup as well as normal operation; disposable CI teardown uses a short timeout.
Procrastinate heartbeat checks recover interrupted jobs; a lost HTTP response can
cause that unfinished output to be requested again, since the contract has no idempotency
key. Already stored outputs are retained.

`IMAGE_API_BASE_URL` configures the endpoint base (including `/v1`);
`IMAGE_API_KEY` optionally supplies a Bearer key. Both are server environment variables;
the browser receives neither. The endpoint's `/model/info` supplies the names and
capabilities shown by the UI. Non-image models are ignored (`mode` must be
`image_generation`). The client reads `display_name`, `paid`, `placeholder`,
`seconds_per_image`, `max_references`, `endpoint`, `response`, `reference_max_side`,
`licence` and `price_per_image`; the interface also reads `price_per_reference` and
`price_estimated`. Prices are USD: the lowest configured price is shown as “from $X
per image”, plus reference pricing where supplied, labelled “estimated” where applicable.
All profile fields, including unknown ones, are kept in cached metadata and generation
snapshots. Rendering and run settings also read `prompt_family`, `reference_slots`,
`aspect_ratios`, `qualities`, `resolutions`, `sizes`, `advanced` and
`max_prompt_chars`; `price_checked` remains retained as supplied.

Last successful metadata is persisted to allow queueing during endpoint outages;
retired entries are marked unlisted, never deleted. Queuing and retrying refuse models
no longer listed. Retry retains the original prompt, profile and reference snapshot.
Queueing checks the reference limit and never silently drops an image. Unknown models
and counts outside one to four are refused. Model names are read at runtime.

The model's `endpoint` selects one of two request shapes, one output per call:

- `images/edits`: multipart `model`, `prompt`, `image[]`, `n=1` and
  `response_format=b64_json`; without references, JSON to `images/generations`.
- `chat/completions`: one user message with the prompt text part first, followed by
  ordered `image_url` parts containing image data URLs, `modalities: ["text", "image"]`
  and no `n`. Decode the first `choices[0].message.images` entry's data URL.

`b64_json` and `message_images` responses are decoded locally. A `url` response profile
is refused as an unsupported model failure; the studio never fetches arbitrary output URLs.
References larger than `reference_max_side` on their longer side (2048 when absent)
are resized with Pillow, keeping aspect ratio. Smaller files are sent unchanged;
resized copies are lossless PNGs made in memory, never stored. Each generation's
ordered references retain the original hashes and a `sent_size: [width, height]`
recorded at queue time using the same preparation routine. The originals are immutable;
models in a comparison may therefore have different sent sizes for the same hashes.
Older snapshots remain readable without this field.

Only `app` and `worker` join the external Docker network `homelab-models`; Postgres,
placeholder and cloudflared do not. Create that network before local/CI `compose up`;
on the server it is supplied by the platform. The hosted route is reached at
`http://litellm:4000/v1` without a published host port. Server configuration uses
`COMPOSE_PROFILES=tunnel` and `IMAGE_API_KEY=unused`. The owner makes the first
real generation; deployment checks use GET only.

For local and CI trials, set `COMPOSE_PROFILES=placeholder` and
`IMAGE_API_BASE_URL=http://placeholder:8300/v1` with an empty key. The `placeholder`
service runs from the same image on the internal default network only, with no
published port. It offers Placeholder A (four references, three seconds), Placeholder B
(paid badge, ten references, eight seconds), an always-500 model, `placeholder-chat`
(chat shape, 512 pixel reference limit) and `placeholder-budget` (always 402). All
have full profiles and are explicitly marked simulators. Generated PNG metadata reports
received dimensions for CI. The only published port remains `127.0.0.1:8200`.
PostgreSQL, worker and placeholder publish no ports.

Additional API routes:

| Routes | Methods / behaviour |
| --- | --- |
| `/api/models` | GET image models and endpoint-supplied capabilities |
| `/api/compositions` | GET compact summaries; optional `project_id=<id>` or `none`; POST create (`name`, `kind`, optional `project_id`, `direction`, `scene`) with Frame 1 |
| `/api/projects/<id>/compositions` | GET same summaries for project; POST create (`name`, optional `kind`, `direction`, `scene`) in project with Frame 1 (default single) |
| `/api/compositions/<id>/duplicate` | POST copy fields, retained pack and live frames without history or finals |
| `/api/compositions/<id>` | GET detail, PATCH name/scene/direction/kind/project_id, DELETE soft-delete |
| `/api/compositions/<id>/assets/<asset-id>` | PUT role and `deselected_images` IDs; DELETE deactivates selection |
| `/api/variants/<id>` | GET by ID (including hidden frames); PATCH name, instructions or frame deselections; DELETE soft-delete |
| `/api/variants/<id>/preview` | GET saved preview; POST preview draft optional `direction`, required `scene` and `instructions` without saving |
| `/api/variants/<id>/generations` | GET history, POST queue (`model`, `count`, optional replacement `prompt`) |
| `/api/assets/<id>/reference-preview` | GET fixed reference-view prompt and uploaded references |
| `/api/assets/<id>/generations` | GET history, POST queue reference views |
| `/api/generations/<id>` | GET state, exact snapshot and output hashes |

Image PATCH also accepts `{"rejected": true}`. Approval clears rejection and rejection
clears approval. Asset detail accepts `include_rejected=true`. Hash navigation adds
`#project/<id>` and `#composition/<id>`. Waiting and running records update through
polling. CI's `scripts/check_generation.py` prints proof of the complete placeholder
journey, immutable history after canonical replacement, candidate approval/rejection,
terminal failure after three attempts, service-outage retry/recovery, limit refusal and restart persistence.
`scripts/check_real_route.py` prints both request shapes with three large references,
received dimensions versus original hashes and sent sizes, one-attempt budget failure,
three-attempt HTTP 500 failure and retired-model retry refusal. The earlier proofs and
the dump restore continue to run in CI.


## Compare and iterate

Each frame lists runs newest first and polls their states without reloading. Open any
output at full size and mark it Final; another choice replaces the selection, and
Clear final removes the choice while retaining every output. Each run opens its
prompt, edit flag, model metadata and ordered references with asset names and roles.
Retry on a failed generation creates a new linked row in the same run using exactly
the failed snapshot. The failed record and any successful results stay unchanged.

Reuse settings loads a browser-only pinned draft: the sent prompt as an edit, the
original models/counts and exact reference files in order. Old files resolve after
asset edits, deletion or approval changes. References outside the current pack are
labelled; remove any reference or append current pack images, edit the prompt and
change models/counts before generating. Back to the current pack restores normal
assembly. Drafts are not saved until Generate creates a new run. File metadata and
asset descriptions are rebuilt on the server; draft hashes must belong to images
of global assets, including deleted assets. Unknown and unattached files are refused. Each chosen model's licence, price and limit are shown before Generate
and checked before any row/job is queued; one insufficient limit refuses the run.

| Routes | Methods / behaviour |
| --- | --- |
| `/api/variants/<id>/runs` | GET grouped history; POST `models: [{model, count}]`, optional `prompt`; pinned drafts also supply ordered `references: [{hash, asset_id, role}]` and `prompt` |
| `/api/generations/<id>/retry` | POST only for failed rows; retains snapshot and run, sets `retry_of` |
| `/api/variants/<id>/final` | GET choice or null; PUT `{generation_id, output}` (zero-based output index); DELETE clears |

Single-model generation routes and asset reference views remain compatible. Alembic
0003 assigns each existing generation its own run and adds retry and final-choice
links without changing snapshots. CI's `scripts/check_compare.py` prints Journey D
proof, including refusal without queueing, pinned old files, retained retry history,
final replacement and restart persistence. The subsequent dump restore compares all
tables and row counts, including these records.


## Storyboards

A storyboard's ordered frame strip sits in the composition header. Add frame creates
Frame N; rename it in Setup. Move up / Move down changes the sequence. Deletion asks
inline and hides the frame with its runs and final. At least one live frame remains;
generations, finals and immutable files remain readable by ID. Every frame uses one
shared asset pack and scene, with its own instructions and optional reference
deselections. Shared edits affect later previews and runs; past snapshots and reused
pinned drafts stay intact.

Export sequence names frames with no final before download and skips them. The server
streams an image-only ZIP without writing an archive to storage. Final images use
unchanged stored bytes, in live frame order, named `01-frame-name.png`, `02-…`, with
contiguous numbering and their stored format's extension. Frame/composition filename
slugs use lowercase ASCII letters and digits separated by hyphens, at most 80 characters,
with `untitled` as fallback. The ZIP is named after the composition. Placeholder finals
export unchanged; their generation records keep the placeholder flag.

| Routes | Methods / behaviour |
| --- | --- |
| `/api/compositions/<id>` | GET includes live ordered variants with final choices and the one shared pack |
| `/api/compositions/<id>/variants` | POST optional `name`, `instructions`; defaults to Frame N |
| `/api/compositions/<id>/frame-order` | PUT `{ids: [...]}` with exactly every live frame ID once |
| `/api/variants/<id>` | PATCH `name`, `instructions`, `deselected_images` (unique selected pack image IDs) |
| `/api/compositions/<id>/sequence` | GET export filename, ordered entries and skipped frame IDs/names |
| `/api/compositions/<id>/sequence.zip` | GET streamed ZIP, including an empty ZIP if there are no finals |

Hidden frames refuse editing, queueing, retrying and final changes. Alembic 0004 adds
nullable `variants.deleted_at` and default-empty `variants.deselected_images` without
changing existing runs, snapshots or finals. Frame add/delete/reorder serialize on the
composition row. CI's `scripts/check_storyboard.py` prints Journey C proofs for shared
references, per-frame snapshots, byte-exact exports, reorder refusals, soft deletion and
restart persistence; the subsequent dump restore includes all these rows.

## Portable packages and storage

**Export asset** on an asset page downloads every attached image, including earlier
canonical references and rejected generated candidates. The storyboard offers
**Export images**, the existing images-only sequence with skipped frame names,
and **Export complete package**, which also retains hidden frames and their history.
Exports build and stream ZIPs on request, without storing archives, changing records
or rewriting image bytes. Import and permanent deletion are not available.

| Route | Behaviour |
| --- | --- |
| `/api/assets/<id>/export.zip` | GET asset package, including soft-deleted assets |
| `/api/compositions/<id>/export.zip` | GET complete composition package, including retained hidden frames |
| `/api/storage` | GET image bytes and unique file counts, total and split by origin |

Both portable package kinds contain one UTF-8 `manifest.json`. Its top-level
`format` is `image-studio-asset` or `image-studio-composition`, `format_version`
is `2` for assets and `4` for compositions, and `exported_at` is an ISO 8601 UTC timestamp. `files` is a deduplicated
list of file records: `hash`, `media_type`, `size` (bytes), `width`, `height`,
`stored_at`, and `filename`. Each file is the exact stored bytes at
`files/<sha256>.<ext>`; extensions are `png`, `jpg` and `webp`. The SHA-256 of its
contents equals the filename's hash. Every referenced file is present once, with
no extra image files. Downloads use `<name-slug>-package.zip` with the same safe
ASCII slug rules as sequence exports. The images-only S6 ZIP keeps its ordered
frame filenames and contains no manifest.

The asset manifest adds `asset`: `id`, `name`, `type`, `type_tag` (label), `description`, `preserve`,
`project_id` (always null; all assets are global), `created_at`, `deleted_at`, and
`images`. Every attachment is listed, regardless of approval or rejection. Image
records contain `id`, `asset_id`, `file_hash`, `approved`, `rejected`, `source`,
`created_at` (attachment time), and the stored file metadata (`hash`, `media_type`,
`size`, `width`, `height`, `stored_at`). All its attached files are included.

The complete composition manifest adds:

- `project`: null for stand-alone compositions, otherwise `id`, `name`, `instructions`, `created_at`.
- `composition`: `id`, nullable `project_id`, `name`, `kind`, `direction`, `scene`, `created_at`, `deleted_at`.
- `asset_pack`: retained selections in position/ID order, with `id`,
  `composition_id`, `asset_id`, `role`, `position`, `deselected_images`, `active`,
  and `asset`. Asset records have the same fields as the asset package but only
  list images used by the runs or pack: historical reference hashes, current
  approved/non-rejected images of active selections, and images named by pack
  or frame deselections. Removed selections remain with `active: false`.
- `referenced_assets`: asset records for pinned references outside the pack,
  listing only the referenced images.
- `frames`: every frame in position/ID order, with `id`, `composition_id`, `name`,
  `instructions`, `position`, `deselected_images`, `deleted_at`, `deleted`,
  `final_generation_id`, `final_output`, `final`, and `runs`. `final` is null or
  `{generation_id, output, hash}`; `output` is zero-based. Hidden frames have
  `deleted: true` and keep their finals and runs.
- Each run contains `run_id` and `generations`, in creation/ID order, including
  retries. Every generation contains its complete database snapshot: `id`,
  `run_id`, `retry_of`, `kind`, `variant_id`, `asset_id`, `model`, `model_info`,
  `prompt` (as sent), `assembled_prompt`, `edited`, ordered `references`,
  `placeholder`, `count`, `state`, `outputs` (ordered hashes), `attempts`, `service_failures`, `error`,
  `created_at`, `started_at`, `finished_at`. References retain `hash`, `asset_id`,
  `asset_name`, `type`, `description`, `preserve`, `type_tag`, `role`, `media_type` and, for new runs, `sent_size` as snapshotted.

The complete package includes every file used by these asset records, references,
outputs and finals. Current asset fields and flags describe export-time records;
run snapshots still describe the exact earlier inputs. `placeholder` flags in
snapshots and model metadata remain intact. Package manifests are built in a
consistent read-only database transaction. Files are immutable, so streaming can
continue after the transaction closes. Packages contain application records and
images only: no endpoint credentials, environment values, configuration or server
paths are added.

**Storage** in the secondary navigation shows the bytes and `file_count` in `stored_files`,
including deleted assets, hidden frames, rejected candidates and historical outputs.
`/api/storage` returns `total`, `uploaded`, `generated`, `placeholder`, each with
`bytes` and `file_count`. Shared hashes count once. For bytes that appear in several
origins, uploaded attachments take precedence, then non-placeholder generation
outputs, then placeholder outputs; a stored file without matching origin records
is counted as generated. These disjoint categories sum to the total. The figure
covers image files only, excluding database size and backups, and is computed from
the database on each request. Refresh updates it. Exporting adds no storage.

CI's `scripts/check_portability.py` prints Journey E proof of canonical replacement,
byte-checkable packages, duplication, soft deletion, retained generation snapshots
and files, complete frame/run contents, storage totals verified independently through
SQL, and unchanged row counts. The following dump proof restores all these records.

Alembic 0006 makes project assignment optional, adds empty direction and backfills
kind from live frame count, and removes asset visibility (all attachments and files
remain). Composition package version 2 adds `kind` and `direction` and permits
`project: null`; asset packages keep version 1 and report `project_id: null`.
Downgrading 0006 restores the S8 schema and rows with global asset visibility.
It refuses if new stand-alone compositions or nonempty directions exist, rather
than discarding new work S8 cannot represent; reconcile such work before downgrade.
Rollback deploys a revert through a new PR and restarts the service. Migration
upgrades preserve the owner's existing project, single composition, frame, runs and
final unchanged. CI prints the S8 migration/downgrade retention proof and the
stand-alone/move/kind/list/duplicate/export journey in `check_structure*.py`, then
runs dump restore alongside the retained earlier journeys.


## Types, preservation, styles and originals

Assets have the same fields for every type: **Person** (`person`),
**Garment/Product** (`garment_product`), **Object/Vehicle** (`object_vehicle`),
**Environment** (`environment`), **Style** (`style`) and **Other** (`other`).
The required stored `type` defaults to `other` for older API clients; the form always
supplies it. Types are validated by the API and adding a type extends the value map.
The old optional `type_tag` remains a free label. Assets filters by type.
**What must stay the same** (`preserve`, empty by default) holds preservation rules
beside the description, such as face shape and eyebrows or button count and lapel
proportions. Duplicate copies all these fields and shares immutable files.

A Style is a normal asset with a description, optional preservation rules and
approved reference images. Choose a style on a project page or a composition's
Setup tab. A composition's own style replaces its project's; an empty choice uses
the project's style. Only live Style assets appear in the style picker, and Style
assets cannot be pack subjects. Changing a picked style's type requires clearing
its choices first; changing a subject to Style requires removing it from packs.
Deleting a style hides it from choices and future assembly; existing snapshots
remain readable. A deleted composition style does not fall back to the project
until its own choice is cleared.

An asset page separates **References**, **Originals**, and generated candidates
waiting for review, followed by **Generate reference views**. Originals are all
uploads; References are approved, non-rejected images of either source. An approved
upload appears in both lists. Approve makes an upload or candidate a Reference;
Unapprove retains the attachment and bytes. Generated references show linked
original thumbnails in the order recorded by their producing generation. Lineage
is read from that snapshot, never stored again on the image. For identical output
hashes the earliest producing generation identifies the attachment's lineage;
duplicated attachments share it. Rejected images stay hidden unless requested.

In a composition, References are on by default. Unapproved Originals are off until
ticked in the shared pack or for an individual frame. Frame toggles can exclude
pack images, including selected Originals. Each asset sends References first and
then selected unapproved Originals, without sending an approved upload twice.
The style's References come first in request order, with role `style reference`;
subjects follow pack order. Style references can be switched off per composition
and per frame and count against each model's `max_references`.

The fixed template is project instructions, composition direction, the optional
style line, scene, one line per subject, then frame instructions. Empty parts are
omitted. Subject lines are `role: name (Type) — description`, followed by
`Keep: <preserve>` when nonempty and the ordered reference numbers. The style line
is `Style: <name> — <description>`, followed by its optional `Keep: <preserve>` and
reference numbers. Reference views use the asset's type and `keep: <preserve>` and
send all its Originals. Earlier generation prompts and reference snapshots are
never rewritten; new reference snapshots also include `type` and `preserve`.

Project and composition create/PATCH accept nullable `style_asset_id`. Composition
PATCH also accepts `style_deselected_images`; GET includes the effective `style`
and its images. Pack PUT and frame PATCH accept `selected_originals` (unique image
IDs); `deselected_images` excludes references or pack-selected Originals. Asset
GET includes `originals`, `references` and `images`; generated image records include
`lineage: {generation_id, originals}` from the producing snapshot.

Alembic 0007 adds these columns with empty selections and no style choice. For
existing labels it trims and matches whole keywords case-insensitively:

| Type | Legacy label keywords |
| --- | --- |
| Person | person, people, character, model |
| Garment/Product | garment, clothing, product, shoe |
| Object/Vehicle | object, vehicle, car, lamp, furniture |
| Environment | environment, background, location, place, room |
| Style | style, look |
| Other | every other label, including empty |

The exact label text is retained. Descriptions, attachments, files, generations,
frames, runs and final choices are unchanged. Downgrade removes only the new
columns and restores R1 rows. CI proves a fresh upgrade and R1 upgrade twice,
downgrade and re-upgrade with `character`, `lamp` and an unknown label.

Asset package **version 2** adds `type`, label and `preserve` plus Originals,
References and generated lineage. Composition package **version 4** adds these
asset fields, project/composition `style_asset_id`, effective `style`, style
selections, pack/frame `selected_originals` and new reference metadata. Historical
style inputs remain in run snapshots and `referenced_assets` after style deletion.
Packages retain the files used by selections and history and still stream without
storing an archive or changing any record. `scripts/check_richer_assets.py` prints
the complete placeholder journey, reference order and limits, lineage, style
inheritance/replacement/deletion, both package versions and unchanged snapshots.


## Per-model requests and run settings

The shared R2 template remains project instructions, direction, style, scene,
subject lines with preservation rules, then frame instructions. Rendering is
fixed and deterministic in the studio; no model rewrites it. `openai` puts a
numbered `Image 1: <name>, <role>, <type>` legend before the content. `gemini`
puts content before the legend and stably orders Person references first, then
all other references. Template reference numbers are remapped to that order.
Unknown or missing `prompt_family` keeps the shared text and order unchanged.
No references are dropped. A run exceeding `max_references`, `reference_slots`
(`character` means Person; `object` means every other type), or `max_prompt_chars`
is refused naming the model, selected count and limit, before any rows or jobs
are inserted.

Format is shared across a run, chosen from the intersection of selected models'
ratios. The picker explains when a model lacks the chosen format. Each model's
quality or resolution offers only priced values and defaults to the cheapest.
A `sizes` profile offers its priced size values for the chosen ratio. Advanced
controls start collapsed and use the profile's defaults, enumerated `values`
or inclusive integer `range`. Edits and Reset affect one model's prompt.
Reference-view generation uses the same rendering and setting controls.
History shows shared content, rendered text, text as sent, ordered references,
settings, request fields and estimated cost. Reuse settings pins reference files,
shared content, each model's sent prompt, output count and settings into a draft.

The client reads profiles from `/model/info` at queue time, retains them in the
snapshot, and builds only named setting fields. `aspect_ratios.field` maps a
ratio through a `values` map, or sends the ratio itself for a list. `qualities`
and `resolutions` use their `field` and priced `values`. Alternatively, `sizes`
is a list of `{value, aspect_ratio, resolution, price}`; its matching `value`
is sent as `size`. Advanced entries name their request field with `name` (or
explicit `field`) and describe `type`, `default`, and `values` or `range`.
Plain fields are multipart strings on `images/edits`; dotted fields create nested
JSON objects on `chat/completions`. Dotted multipart fields are refused.
The existing protocol fields (model, prompt, one output and base64 response;
or one user message and text/image modalities) remain. Chat image bytes are
added as ordered `image_url` parts only when sending. With no references the
existing image-generation JSON route is retained. No seed or unadvertised
setting is sent, and endpoint credentials and image bytes never enter snapshots.

Each model's cost is `count × (selected image price + reference count ×
price_per_reference)`, with a missing reference price treated as zero. Decimal
arithmetic calculates the estimate; Postgres stores it as `NUMERIC(18,8)`.
The page shows price per image, each model's cost, the total, and “estimated”
where `price_estimated` says so. This month's estimated spend is the sum of
all generations created within this UTC calendar month, including failed rows
and retries; past rows with no estimate contribute nothing. It is an estimate
of queued work, not a billing ledger. The displayed budget is $20 a month,
enforced by the platform; the studio adds no budget enforcement.

| Route | Behaviour |
| --- | --- |
| `/api/render` | POST shared `content`, attached `references`, `format`, and `models`; returns per-model previews and costs without queuing |
| `/api/variants/<id>/runs` | POST `models: [{model, count, prompt?, settings?}]`, optional shared `format`; pinned drafts also supply `references` and `content` |
| `/api/spend` | GET `estimated_spend` and UTC month start |

Settings are `{format, quality, advanced}`; `quality` stores the chosen quality,
resolution or size value. The earlier shared `prompt` payload remains accepted
as an explicit edit applying to each model. Generation snapshots add nullable
`prompt_family`, `rendered_prompt`, `shared_references`, `settings`,
`request_fields` (executed non-image fields) and `estimated_cost`; `references`
retains each resized copy's `sent_size`. Shared reference order is retained so
Reuse does not renumber a shared template using Gemini's reordered inputs.
Exports include these fields through the complete snapshot.
Alembic 0008 adds only nullable columns; existing rows, prompts, attachments,
finals and files remain unchanged. Downgrade removes these columns to restore
R2. Production rollback uses a revert PR and restart, preserving the columns
and records rather than downgrading owner data.

CI uses only the marked placeholder. Its OpenAI-shaped profile has mapped
ratios and priced qualities; its Gemini-shaped profile has listed ratios,
resolutions, reference slots and dotted fields; a third profile has `sizes`.
Generated synthetic PNG metadata reports the exact non-image fields and sizes
received. `check_model_requests.py` prints the rendering, field mapping,
Advanced isolation, costs/monthly sum, refusals, local edit and reuse proofs.
`check_model_requests_migration.py` proves R2 upgrade twice, unchanged past
rows and downgrade; fresh database upgrades run twice in Postgres tests.
Earlier journeys and the dump restore continue in the compose job.


## Feedback on every output

History and large output pages offer **Good** and **Not good** under each output.
Click once to set a verdict; click the selected button again to clear it. Feedback
belongs to the generation and its output index, independently of **Final**.
**Provide feedback** opens an inline form with an optional verdict, one optional
**Kept**, **Partly** or **Lost** rating per asset in the generation's saved
references (including the style), and an optional note. **Save feedback** saves
explicitly; Cancel discards form edits. History shows each model's rated output
count and good count for the selected frame, including retries. Nothing is scored.

`PATCH /api/generations/<id>/outputs/<index>/feedback` accepts any nonempty subset
of `verdict` (`good`, `not_good` or `null`), `asset_ratings` (a list of
`{asset_id, rating}`) and `note` (text). Omitted fields remain unchanged; an empty
ratings list or empty note clears that detail. Only unique assets from the saved
reference snapshot can be rated, even after library edits or deletion. Responses
include `updated_at`. Generation and History reads include `feedback`, aligned
with `outputs`; untouched outputs have null verdict/time, empty ratings and note.
`GET /api/variants/<id>/feedback-tally` returns `{model: {rated, good}}`.
Large output pages are `#output/<generation-id>/<output-index>`; generated asset
image lineage includes its output index to link to the same page.

Alembic 0009 adds only `output_feedback`, keyed by generation and output index.
Clearing feedback retains its row; no records or stored files are deleted or
rewritten. Downgrade removes the feedback table and restores R3; production
rollback uses a revert PR and restart to retain owner feedback. Complete
composition packages use **format_version 4** and include each generation's
output-aligned feedback, alongside the full snapshots. Asset packages stay at
version 2. Exports still stream without changing records or storage.

CI's `check_feedback_migration.py` proves R3 runs survive upgrade twice and
restores R3 on downgrade; fresh databases migrate twice in Postgres tests.
`check_feedback.py` prints proof of two models with two outputs each, verdict
changes and clearing, subject/style ratings and a note, refusal of an unreferenced
asset, per-model tallies and version 4 packages with unchanged records/storage.
Earlier placeholder journeys and dump restore run alongside it.

# API reference

The API is JSON except image uploads (`multipart/form-data`, one or more `files`
fields), file downloads, and streamed ZIP exports. Unknown API routes and unknown
file hashes return JSON 404 responses. Request fields shown below are the
principal fields; see the workflow guides for payload details.

## Projects and assets

| Route | Method | Behaviour |
| --- | --- | --- |
| `/api/health` | GET | Readiness and database connectivity; 503 if unavailable |
| `/api/projects` | GET, POST | List projects; create with `name`, `instructions`, optional `style_asset_id` |
| `/api/projects/<id>` | GET, PATCH | Read or edit project fields |
| `/api/projects/<id>/assets` | GET | Curated assets, including deletion state, `added_at`, and thumbnail |
| `/api/projects/<id>/assets/<asset-id>` | PUT, DELETE | Add/re-add a live asset; timestamp membership removal |
| `/api/assets` | GET, POST | List or create (`name`, `type`, `type_tag`, `description`, `preserve`) |
| `/api/assets/<id>` | GET, PATCH, DELETE | Read, edit, or soft-delete asset; GET accepts `include_rejected` |
| `/api/assets/<id>/duplicate` | POST | Copy asset fields and image approvals |
| `/api/assets/<id>/images` | POST | Upload multipart image files |
| `/api/assets/<id>/images/<image-id>` | PATCH | Change `approved` or `rejected` review flags |
| `/api/files/<sha256>` | GET | Fetch immutable stored bytes with stored media type |
| `/api/assets/<id>/reference-preview` | GET | Fixed reference-view prompt and uploaded references |
| `/api/assets/<id>/generations` | GET, POST | Read or queue asset reference-view generations |
| `/api/assets/<id>/export.zip` | GET | Stream asset package, including deleted assets |

Asset lists accept `type`, `type_tag`, `used_by_project`, `q`, `include_deleted`
and `thumbnails` filters. Composition lists accept literal case-insensitive name
search `q`. Deleted assets cannot be edited, duplicated, or uploaded to, but
their attachments and files remain available.

## Compositions, frames, and generation

| Route | Method | Behaviour |
| --- | --- | --- |
| `/api/models` | GET | Endpoint-supplied image models and capability profiles |
| `/api/compositions` | GET, POST | List/filter summaries; create with `name`, `kind`, optional project and brief |
| `/api/projects/<id>/compositions` | GET, POST | List or create project composition (name required; kind defaults to single) |
| `/api/compositions/<id>` | GET, PATCH, DELETE | Read detail, edit fields, or soft-delete |
| `/api/compositions/<id>/duplicate` | POST | Copy fields, retained pack and live frames, without runs/finals |
| `/api/compositions/<id>/assets/<asset-id>` | PUT, DELETE | Set pack role/selections or deactivate selection |
| `/api/compositions/<id>/variants` | POST | Add frame; optional name and instructions, default Frame N |
| `/api/compositions/<id>/frame-order` | PUT | Reorder live frames using `{ids: [...]}` with each live ID exactly once |
| `/api/variants/<id>` | GET, PATCH, DELETE | Read (including hidden), edit frame, or soft-delete |
| `/api/variants/<id>/preview` | GET, POST | Read saved preview or render unsaved draft (`brief`, `instructions`) |
| `/api/variants/<id>/generations` | GET, POST | Read history or queue one model/count with optional prompt replacement |
| `/api/variants/<id>/runs` | GET, POST | Read runs or queue model choices, optional shared format and pinned draft inputs |
| `/api/variants/<id>/final` | GET, PUT, DELETE | Read, select a completed output as final, or clear final |
| `/api/variants/<id>/feedback-tally` | GET | Per-model rated and good output counts |
| `/api/compositions/<id>/sequence` | GET | Sequence export filename, ordered entries and skipped frames |
| `/api/compositions/<id>/sequence.zip` | GET | Stream images-only sequence ZIP |
| `/api/compositions/<id>/frame-sequences` | GET, POST | Read sequences or queue `full`, `next`, or `rest` mode |
| `/api/frame-sequences/<id>/stop` | POST | Stop after current frame; repeat calls are harmless |
| `/api/generations/<id>` | GET | Generation state, exact snapshot and output hashes |
| `/api/generations/<id>/retry` | POST | Retry a failed generation from its original snapshot |
| `/api/generations/<id>/outputs/<index>/feedback` | PATCH | Update output verdict, asset ratings, and/or note |
| `/api/render` | POST | Preview content/references/format per model without queueing |
| `/api/spend` | GET | Estimated spend and UTC month start |
| `/api/compositions/<id>/export.zip` | GET | Stream complete package, including retained hidden frames |
| `/api/storage` | GET | Unique stored bytes and file counts by origin |

Project composition summaries are filtered to that project. On
`/api/compositions`, `project_id=none` selects stand-alone compositions and an
omitted parameter returns all. Frame PATCH may update `name`, `instructions`,
reference selections, and `use_previous_frame`. Hidden frames cannot be edited,
queued, retried, or have their final changed. All deletion endpoints preserve
records as soft-deleted state.

# Data and formats

## Record model

Projects hold creative direction and optional style selection. Global assets hold type, description, preservation rules, optional type tag, deletion time, and project memberships. Compositions hold a brief, kind, project, style choice and shared asset pack. Variants are frames, with ordering, instructions, previous-frame behavior, reference overrides and optional final selection.

Image bytes are stored outside PostgreSQL under their SHA-256 digest. The database stores the digest, media type, dimensions and size, with attachment rows linking files to assets. Files are immutable: replacements use new content-addressed files. Deletion and image review change record state without deleting attachments or files.

Runs and generations retain model metadata, prompt content and the exact sent prompt, settings, request fields, ordered reference snapshots, state, attempts, errors and output hashes. Output feedback is stored per output. Generations and frame sequences are retained rather than hard-deleted. Alembic owns schema creation and upgrades; the current migration head is 0012.

## Export packages

Exports are streamed on request and do not modify database records or file storage.

- Asset packages are ZIP archives containing a manifest and the asset's image files. The current asset package format is version 2.
- Composition packages are ZIP archives containing a manifest and retained composition/frame image files. The current composition package format is version 6.
- Storyboard sequence ZIPs contain selected final images in frame order. Frames without a final are represented in sequence metadata as skipped entries.

Package versions describe exported package formats, not Alembic schema revisions. Consumers should check `format_version` in package manifests before interpreting fields.

### ZIP manifest reference

Both package types contain UTF-8 `manifest.json`, `format`, `format_version`,
`exported_at` (ISO 8601 UTC), and `files`. `format` is
`image-studio-asset` or `image-studio-composition`; current versions are 2 and 6.
Each `files` entry has `hash`, `media_type`, `size` (bytes), `width`, `height`,
`stored_at`, and `filename`. The filename is `files/<sha256>.<ext>` (`png`,
`jpg`, or `webp`); the bytes hash to the filename digest. Files are deduplicated
and every referenced file is included once. The download name is
`<safe-name-slug>-package.zip`.

The asset manifest's `asset` contains `id`, `name`, `type`, `type_tag`,
`description`, `preserve`, null `project_id`, `created_at`, `deleted_at`, and
all attached `images`, regardless of approval or rejection. Each image has
`id`, `asset_id`, `file_hash`, `approved`, `rejected`, `source`, attachment
`created_at`, and stored file metadata (`hash`, `media_type`, `size`, `width`,
`height`, `stored_at`).

The composition manifest contains `project` (null or its `id`, `name`,
`instructions`, `created_at`), `composition` (`id`, `project_id`, `name`,
`kind`, `brief`, `created_at`, `deleted_at`), and effective `style`. `asset_pack`
contains retained selections in position/ID order, including selection fields
`id`, `composition_id`, `asset_id`, `role`, `position`, `deselected_images`,
`active`, and `asset`. Pack asset images include run references, current approved
non-rejected images for active selections, and images named by selection/frame
deselections. Removed selections remain with `active: false`. `referenced_assets`
contains pinned referenced assets outside the pack.

`frames` includes every frame in position/ID order, including hidden frames, with
`id`, `composition_id`, `name`, `instructions`, `position`, deselected and
selected-original IDs, deletion fields, final selection and `runs`. A final is
null or `{generation_id, output, hash}`; output indices are zero-based. Runs
contain `run_id` and generations in creation/ID order, including retries. Each
generation preserves its database snapshot: IDs and kind, model and `model_info`,
sent and assembled prompts, edit flag, ordered references, placeholder flag,
count, state, output hashes, attempt counters, error, timestamps, request settings
and feedback when present. References retain their hash, asset identity and
description, role, media type and (for newer snapshots) `sent_size`. `sequences`
retains frame sequence records. Files cover these asset records, references,
outputs and finals. Manifests are produced from a read-only consistent database
snapshot; no endpoint credentials, environment values or server paths are added.

Format evolution: asset v1 introduced the asset manifest and files list; asset
v2 added typed asset metadata, rejected state, and the derived originals and
references lists. Composition v1 introduced composition and frame exports;
v2 added nullable project support; v3 added typed global assets, styles and
explicit original/reference selections; v4 added output feedback; v5 replaced
legacy direction/scene fields with `brief` and its snapshot representation;
v6 added retained sequences and previous-frame reference snapshots. Composition
v6 includes the accumulated fields above. The images-only storyboard sequence ZIP is separate: it has no
manifest, keeps frame order, and names skipped frames in sequence metadata.

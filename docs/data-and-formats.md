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

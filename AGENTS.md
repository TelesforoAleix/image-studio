# Repository guard

This repository describes what exists. Work arrives as self-contained task prompts;
do not look for plans or roadmaps elsewhere.

Keep code, configuration and documentation only. Never commit images (uploaded,
reference or generated), user-written prompts or records, database dumps, exports,
model weights or app state, including fixtures. Tests build synthetic images at
run time. CI enforces this with the no-data-files guard and secret scanning.

No secrets in git or container images. Publish the app only on loopback; publish
no database port. Models are accessed only through the configured endpoint, with
its base URL and key supplied by the environment. The studio holds no model key
and hard-codes no model or provider; display names supplied by that endpoint.

Libraries own machinery: use mature libraries for an ORM, migrations, image
decoding and job execution when a task introduces those needs. Do not hand-roll them.

A stored image file is never overwritten or deleted by the app. A replacement is
a new file; records point at the exact files they used.

No account names, home-directory paths, private addresses or hostnames of the
owner's machines belong in this repository.

Before every commit run `uv run pytest`, `uv run ruff check .`,
`uv run ruff format --check .` and the front-end build when the front end exists.

Proceed without asking, except before a step that cannot be undone or carries a
real security risk: deleting data or volumes, touching a secret, making something
reachable from outside loopback, rewriting main's history or loosening its
protection, or a security concern the task prompt does not address. For those,
stop, explain the risk and recovery, and wait for the owner. Explicit task
authorization governs the bootstrap, publishing and disposable CI cleanup.

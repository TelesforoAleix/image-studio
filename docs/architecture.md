# Architecture

## Services

The single-origin deployment serves a Flask JSON API and the built React 19/Vite application from Gunicorn in the `app` container. PostgreSQL 17 stores application records. SQLAlchemy Core issues database operations; Alembic migrations create and change application tables. The `worker` container uses Procrastinate with the same database and immutable file volume to process queued image jobs. The optional `placeholder` service returns synthetic images for local and CI use. Compose also defines an optional `cloudflared` tunnel profile.

The application port is published on loopback only. PostgreSQL has no published port. The app has no authentication; deployments should place it behind an authenticating proxy.

## Image endpoint contract

Configure `IMAGE_API_BASE_URL` to the endpoint base, including `/v1`, and optionally set `IMAGE_API_KEY` for bearer authentication. The app requests `/model/info`, displays image models supplied by the endpoint, and uses each model's capability profile. Models must advertise image generation mode. The profile supplies endpoint shape and response details, prompt family, reference limits, formats, quality/resolution choices and pricing or timing metadata. The app supports the advertised OpenAI-compatible image endpoint forms; it does not select a provider or model in code.

For multipart image generation the app sends one image per request (`n=1`), retaining completed outputs between calls. Chat-completions style profiles send text and image modalities. Returned image bytes are decoded and validated before storage. The placeholder profile is configured with `IMAGE_API_BASE_URL=http://placeholder:8300/v1` and an empty key.

## Generation pipeline and retries

The API stores a run and its generation records before enqueueing work. Procrastinate processes one generation at a time, and the requested outputs are fetched sequentially. Each generation records the exact assembled content, rendered and sent prompts, model name and metadata, settings, request fields, ordered references, output hashes, attempts, status, errors and timestamps. Placeholder generations are marked explicitly.

Connection refusal and DNS failures retry with delays of 10, 20, 40, 80, 160, then 300 seconds. Timeouts and endpoint 5xx responses retry at most twice more; that failure count persists across worker restarts. Other 4xx errors fail immediately, including a budget 402. Malformed responses and unsupported profiles fail without retry. Completed outputs remain stored if a later output fails. Since the endpoint contract has no idempotency key, a lost response can cause an unfinished output request to be repeated.

## Prompt rendering and capabilities

The prompt renderer creates shared content from project instructions, brief, selected style, asset roles and descriptions, preservation rules, and frame text. It then renders this content with ordered reference legends according to the model's prompt family and endpoint shape. Per-model edits replace that model's rendered prompt only. Run settings and prompt edits are snapshotted, so later changes to assets or approvals do not rewrite history.

The cached model profile is retained with generations, including extra profile fields. The interface uses profile data for model names, paid/placeholder labels, capabilities, reference limits, price estimates and timing estimates. Pricing is displayed as an estimate when the endpoint marks it so.

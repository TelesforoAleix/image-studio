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

### Capability profile fields

The endpoint must provide a model name and `model_info` for image generation
models. Required profile values are `mode: image_generation`, `display_name`,
boolean `paid` and `placeholder`, nonnegative integer `max_references`,
`licence`, `endpoint` (`images/edits` or `chat/completions`), `response`
(`b64_json`, `message_images`, or `url`), and pricing (`price_per_image`, or
`sizes`). Optional `seconds_per_image` is a nonnegative number.

| Field | Use and default |
| --- | --- |
| `reference_max_side` | Maximum sent reference dimension; defaults to 2048, must be positive |
| `prompt_family` | Prompt rendering family; unknown or absent preserves shared order/text |
| `reference_slots` | Per-type slot limits (`character` for Person; `object` for other types) |
| `aspect_ratios` | Supported ratios and endpoint field/value mapping |
| `qualities`, `resolutions` | Priced setting choices and request field mappings |
| `sizes` | Alternative priced `{value, aspect_ratio, resolution, price}` choices |
| `advanced` | Named request controls with type, default, and values or integer range |
| `max_prompt_chars` | Maximum rendered prompt size |
| `price_per_image` | Prices by setting; used for estimates |
| `price_per_reference` | Per-reference estimate addition; absent means zero |
| `price_estimated` | Marks displayed pricing as estimated |
| `price_checked` | Retained endpoint metadata |
| `display_name`, `paid`, `placeholder`, `licence`, `seconds_per_image` | UI labels, badges, licence and timing metadata |
| `endpoint`, `response`, `max_references` | Request shape, decoder, and total reference limit |

Unknown profile fields are retained in cached model metadata and generation
snapshots. `url` responses are refused; the application does not fetch arbitrary
image URLs. If `response` or `endpoint` is absent in an older saved snapshot,
the client defaults to `b64_json` and `images/edits`, respectively.

## Generation failures

Connection refusal and DNS failures retry with delays of 10, 20, 40, 80, 160,
then 300 seconds, without a fixed attempt limit. Timeouts and endpoint 5xx or
uncertain transport failures retry to a maximum of three attempts. Other 4xx
responses fail immediately. HTTP 402 is terminal and shown as “Monthly image
budget reached — resets on the 1st (UTC)”; other HTTP errors use “Image request
failed (HTTP <status>)”. Malformed image responses and unsupported endpoint or
response profiles fail terminally. Model-list connectivity or invalid metadata
returns “Image model list temporarily unavailable”.

Completed outputs remain retained if a later sequential output fails. A lost
response can cause an unfinished output to be requested again because the
endpoint contract has no idempotency key. Retrying a failed generation uses its
original prompt, model profile, and ordered reference snapshot.

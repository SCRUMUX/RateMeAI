# Image-gen tier surface (post Nano-Banana cleanup)

> **Historical context.** Versions v1.21–v1.71 described an A/B setup with
> two models (Nano Banana 2 Edit + GPT Image 2 Edit). The Nano Banana
> cleanup removed the A/B router: one model remains — **GPT Image 2 Edit**.
> Product choice is **Standard / Premium** tiers.

## TL;DR

- Every `/api/v1/analyze` request uses **GPT Image 2 Edit**
  (`openai/gpt-image-2/edit`). Framing uses native portrait sizing
  (e.g. 1024×1536 at medium quality).
- Form field `tier` controls FAL quality only (same prompt + pipeline):
  - **standard** (1 credit) — `image_quality=medium`. ≈ $0.06 / img.
  - **premium** (5 credits) — `image_quality=high` only (no Clarity). ≈ $0.20 / img.
- No cross-model fallback. Failures refund credits; Premium does **not**
  silently downgrade to Standard (v1.75+ hard fail + full 5-credit refund).
- Legacy `image_model` / `image_quality` form fields are accepted for
  old clients but **tier** is the source of truth on the server
  ([`apply_tier_context_fields`](../src/services/analysis_request.py)).

## Contract chain

```
UI tier pill → FormData tier=premium → apply_tier_context_fields → task.context
  → pipeline (edit path) → executor quality=high (premium) | medium (standard)
```

### RU edge (`ailookstudio.ru`, `DEPLOYMENT_MODE=edge`)

Edge `/analyze` applies tier fields locally (credits, `task.context`), then proxies
to primary via [`RemoteAIService`](../src/services/remote_ai.py) →
`POST /api/v1/internal/process-analysis`. **v1.78+** must include `tier` in that
JSON payload. Before v1.78 only `image_quality` was forwarded; primary called
`apply_tier_context_fields(tier="")` and **always** rebuilt **standard** — Premium
in the UI charged 5 credits but the worker rendered medium quality.

```
edge task.context (premium) → remote_ai payload tier=premium → primary ctx → worker
```

| Field | Standard | Premium |
|-------|----------|---------|
| `tier` | `standard` | `premium` |
| `image_model` | `gpt_image_2` | `gpt_image_2` |
| `image_quality` | `medium` | `high` |
| `image_refine` | — | — (v1.79: Clarity not used on product tier) |

## Cost

| Tier | FAL quality | Refiner | Approx USD/img | Credits |
|------|-------------|---------|----------------|---------|
| Standard | medium | — | ≈ $0.06 | 1 |
| Premium | high | — | ≈ $0.20 | 5 |

## Kill-switches and ENV

| Variable | Default | Effect |
|----------|---------|--------|
| `AB_TEST_ENABLED` | `true` | **Legacy.** v1.77+ tier routing does **not** depend on this flag. |
| `CLARITY_REFINER_ENABLED` | `true` | Legacy knob; **not** used for product Premium tier since v1.79. |
| `FAL_API_KEY` | — | Required on **worker** for GPT Image 2. |

## Task result telemetry (v1.77)

Successful generations may include:

- `product_tier`, `fal_quality`
- `output_pixel_dimensions` (final render size)

Use these fields in Storage/admin to verify Premium actually ran.

## Diagnostics

- `/health` — app version
- Internal image-gen probe endpoints accept `provider=gpt_image_2`
- Prometheus: `IMAGE_GEN_BACKEND`, `PREMIUM_REFINE_*`

## Removed in Nano-Banana cleanup

| Artifact | Status |
|----------|--------|
| `fal_nano_banana.py`, `unified.py` | Removed |
| Cross-model fallback | Disabled |

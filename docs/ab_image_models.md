# v1.22 A/B default — Nano Banana 2 Edit vs GPT Image 2 Edit

This doc is the operator / on-call cheat sheet for the image-gen A/B
surface. `1.21.0-ab` shipped it as an opt-in path; **`1.22.0` promotes
it to the default** — every UI-visible request now lands on Nano
Banana 2 or GPT Image 2. The legacy hybrid `StyleRouter` pipeline is
still in-tree as an env-flag-only rollback.

## TL;DR

- The v1.18 hybrid pipeline (PuLID / Seedream / FLUX.2 Pro Edit +
  CodeFormer / ESRGAN / GFPGAN) is **frozen, not deleted** and is
  reachable **only** via `AB_TEST_ENABLED=false` on Railway.
- Every `/api/v1/analyze` request now carries `image_model` +
  `image_quality`. Missing / unknown values fall back to
  `ab_default_model=gpt_image_2` + `ab_default_quality=low` on the
  server side — i.e. the cheapest A/B combo, never back to
  StyleRouter.
- Two models under test:
  - `fal-ai/nano-banana-2/edit` (Google Gemini 3.1 Flash Image)
  - `openai/gpt-image-2/edit`   (OpenAI ChatGPT Images 2.0 via fal)
- Three quality tiers per model: `low` / `medium` / `high`.
- Global kill switch: `AB_TEST_ENABLED=false` on Railway →
  StyleRouter takes over for every request, UI pills become inert.

## How a request flows

```
UI pills        FormData          /analyze                Task.context            Executor
+----------+    +-------------+   +----------------+     +----------------+     +-----------------+
| Model    |--->| image_model |-->| whitelist +    |---->| image_model    |---->| if ab_active: |
| Quality  |--->| image_quality|  | stash into ctx |     | image_quality  |     |   AB provider  |
+----------+    +-------------+   +----------------+     +----------------+     |   + structured |
                                                                                |   prompt       |
                                                                                | else: default  |
                                                                                +-----------------+
```

- `AB_MODELS_ALLOWED = {"nano_banana_2", "gpt_image_2"}`
- `AB_QUALITIES_ALLOWED = {"low", "medium", "high"}`
- Anything else drops on the floor silently — the endpoint keeps the
  202 contract, the request just runs on the hybrid path.

## Cost per generation (FAL invoiced, v1.22)

| Model           | low  (default)         | medium                 | high                   |
|-----------------|------------------------|------------------------|------------------------|
| Nano Banana 2   | $0.08 — `1K` ≈ 1024 px | $0.12 — `2K` ≈ 2048 px | $0.16 — `4K` ≈ 4096 px |
| GPT Image 2     | ~$0.02 — 1024²         | ~$0.06 — 1536²         | ~$0.25 — 2048²         |

GPT Image 2 is token-priced, so the numbers above are empirical
averages, not contractual. The `high` tier is an explicit user
choice — we deliberately gate it behind a pill click rather than
making it the default (GPT Image 2 @ high = $0.25 is ~12× the cost
of the default `low` tier).

**Nano Banana 2 quality floor note (v1.22):** the `low` tier was
previously `0.5K` (~512 px long edge, $0.06). We bumped it to `1K`
because 512-px portraits were too soft for production. The cheapest
Nano Banana 2 output is now a full ~1 MP image at $0.08.

## Enabling / disabling the feature

### Server-side

```
# Railway → ratemeai-app → Variables
AB_TEST_ENABLED=true         # default, routes every /analyze via A/B
AB_DEFAULT_MODEL=gpt_image_2 # fallback when the client omits image_model
AB_DEFAULT_QUALITY=low       # fallback when the client omits image_quality
AB_PROMPT_MAX_LEN=1500       # 8-block prompt budget
```

Flip `AB_TEST_ENABLED=false` to **re-enable the legacy hybrid
StyleRouter** for all traffic. The A/B form fields become inert and
every request routes through PuLID / Seedream / FLUX.2 / CodeFormer
/ ESRGAN / GFPGAN as in v1.21. Redeploy is not required — FastAPI
reads `settings` at call time. This is the designated emergency
rollback path when Nano Banana 2 or GPT Image 2 regresses.

### Client-side (per user)

Two `localStorage` keys carry the selection:

- `ailook_ab_model` — `"nano_banana_2"` | `"gpt_image_2"` (absent →
  defaults to `"gpt_image_2"` on first visit)
- `ailook_ab_quality` — `"low"` | `"medium"` | `"high"` (absent →
  defaults to `"low"`)

There is no longer a **Стандарт** UI pill — v1.22 removed it. To
route an individual user through the legacy hybrid pipeline, flip
`AB_TEST_ENABLED=false` globally (there is no per-user legacy opt-in
anymore).

## Rollback

Cost explosion, quality regression, model drift — any of these:

1. **Kill switch**: `AB_TEST_ENABLED=false` on Railway (app + worker).
   Single env-var change, no redeploy; existing `/analyze` calls with
   `image_model` set will transparently route through the hybrid
   pipeline.
2. **Provider quarantine**: remove just one model from
   `factory.AB_IMAGE_MODELS`. The other stays available.
3. **Full revert**: revert the `1.21.0-ab` merge commit. The new
   provider files / prompt adapter / UI pills come out cleanly —
   everything is additive and nothing in the hybrid pipeline imports
   from the A/B modules.

## Metrics

No new Prometheus label dimensions — the A/B path reuses the existing
counters with a composite `backend` value:

- `ratemeai_image_gen_calls_total{provider="FalNanoBanana2Edit"}`
- `ratemeai_generation_cost_usd{backend="nano_banana_2:medium"}`
- `ratemeai_generation_cost_usd{backend="gpt_image_2:high"}`

Use the `backend` label to split A/B cost from hybrid cost in
Grafana. For a live deploy rate check:

```
sum by (backend) (
  rate(ratemeai_image_gen_calls_total[5m])
)
```

## Smoke tests

CI fires four probes per deploy (cost ≈ $0.05 total):

- `diagnostics/image-gen-probe?mode=scene_preserve` (StyleRouter)
- `diagnostics/image-gen-probe?mode=identity_scene` (StyleRouter)
- `diagnostics/image-gen-probe?provider=nano_banana_2&quality=low`
- `diagnostics/image-gen-probe?provider=gpt_image_2&quality=low`

A failure in either A/B probe fails the Railway deploy the same way
a PuLID regression does — see `.github/workflows/ci.yml`, step
"Live provider smoke".

## Prompt structure

Both models get the 8-block layout from
`src/prompts/ab_prompt.build_structured_prompt`:

```
Subject:  the man in the reference photo, ...
Scene:    <variant.scene or spec.background>
Style:    <aesthetic tone derived from (mode, style)>
Lighting: <variant.lighting or spec.lighting>
Camera:   photorealistic, DSLR, natural depth of field, realistic proportions
Identity & Realism: <identity lock>
Enhancement:        <subtle attractiveness>
Output:             <high detail, clean composition>
```

Model-specific wrappers on top:

- **Nano Banana 2** — prepends
  `"Keep facial features exactly the same as the reference image."`
  to the Identity block (Google / fal reference-edit best practice).
- **GPT Image 2** — appends a `Change: / Preserve: / Constraints:`
  triptych at the bottom (fal GPT Image 2 prompting guide).

The adapter is read-only with respect to the style registry — it
does not modify any of the ~130 existing `StyleVariant` entries, so
rolling back leaves the hybrid prompt builder exactly as it was.

## On-call triage playbook

1. `ratemeai_generation_cost_usd{backend=~"nano_banana.*|gpt_image.*"}`
   spiking above $0.20 / image sustained?
   → set `AB_DEFAULT_QUALITY=low` on Railway, redeploy, monitor.
2. HTTP 422 from one of the A/B providers?
   → check the provider's fal schema page; the most common cause is
   a new required field or a changed enum. Fix in
   `fal_nano_banana.py` / `fal_gpt_image_2.py`, add a regression
   test alongside `test_body_has_expected_*_shape`. Note: Nano Banana
   2 Edit has **no `image_size` field** (uses `resolution` +
   `aspect_ratio` enums instead); GPT Image 2 Edit does accept
   `image_size` with multiples-of-16 constraint.
3. Identity drift complaints on A/B path?
   → the structured prompt adapter does not run the VLM identity
   gate any differently from the hybrid path — all post-gen gates
   are shared. Look at `ratemeai_identity_retry_triggered_total` by
   provider to confirm before investigating the prompt itself.
4. Want to disable only one of the two A/B providers?
   → temporarily remove its key from `factory.AB_IMAGE_MODELS`;
   incoming `image_model=<disabled>` values drop to the default path.

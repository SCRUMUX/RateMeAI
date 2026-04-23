# v1.23 A/B default — Nano Banana 2 Edit vs GPT Image 2 Edit

This doc is the operator / on-call cheat sheet for the image-gen A/B
surface. `1.21.0-ab` shipped it as an opt-in path; `1.22.0` promoted
it to the default; **`1.23.0` tightens the face-fidelity pipeline**
specifically for the two A/B providers (see [Face fidelity
pipeline](#face-fidelity-pipeline-v123) below). The legacy hybrid
`StyleRouter` pipeline is still in-tree as an env-flag-only rollback
and is bit-for-bit unchanged.

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

## Cost per generation (FAL invoiced, v1.23)

| Model           | low  (default)          | medium                            | high                               |
|-----------------|-------------------------|-----------------------------------|------------------------------------|
| Nano Banana 2   | $0.08 — `1K` ≈ 1024 px  | $0.12 — `2K` + thinking=high      | $0.16 — `4K` + thinking=high       |
| GPT Image 2     | ~$0.02 — 1024 × 1024    | ~$0.06 — 1024 × 1536 (HD portrait) | ~$0.25 — 1440 × 2560 (2K portrait) |

GPT Image 2 is token-priced, so the numbers above are empirical
averages, not contractual. The `high` tier is an explicit user
choice — we deliberately gate it behind a pill click rather than
making it the default (GPT Image 2 @ high = $0.25 is ~12× the cost
of the default `low` tier).

**v1.23 size note:** GPT Image 2 now only emits the OpenAI-officially-
supported sizes (`1024×1024`, `1024×1536`, `1536×1024`, `2560×1440`).
The v1.22 forced squares (`1024²` / `1536²` / `2048²`) are gone — the
`2048²` combination was off-spec and had unstable latency on `high`,
which is why `quality=high` was tripping the edge poll timeout. The
executor now forwards a StyleSpec-aware `image_size` and the provider
snaps any off-list size onto the whitelist.

**v1.23 NB2 note:** the medium and high tiers now set
`thinking_level="high"` (Gemini reasoning-guided edit). Adds ~40-60%
latency but is the single biggest lever for face preservation per the
fal.ai / Google prompting guides. Low tier stays on fast mode.

**Nano Banana 2 quality floor note (v1.22):** the `low` tier was
previously `0.5K` (~512 px long edge, $0.06). We bumped it to `1K`
because 512-px portraits were too soft for production. The cheapest
Nano Banana 2 output is now a full ~1 MP image at $0.08.

## Enabling / disabling the feature

### Server-side

```
# Railway → ratemeai-app → Variables
AB_TEST_ENABLED=true           # default, routes every /analyze via A/B
AB_DEFAULT_MODEL=gpt_image_2   # fallback when the client omits image_model
AB_DEFAULT_QUALITY=low         # fallback when the client omits image_quality
AB_PROMPT_MAX_LEN=2000         # prompt budget (v1.23: bumped for the extended GPT-2 Preserve/Constraints)
AB_IDENTITY_RETRY_ENABLED=false  # v1.23: A/B path skips identity retry by default
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

Both wrappers live in `src/prompts/ab_prompt.build_structured_prompt`
and both are re-assembled from the existing `StyleSpec` /
`StyleVariant` fields (no rewrite of the ~130 existing variants).

### GPT Image 2 — 8-block body + triptych

GPT Image 2 handles long structured prompts well, so the 8-block
layout is kept verbatim and the wrapper appends the
`Change: / Preserve: / Constraints:` triptych recommended by
OpenAI's "Generate images with high input fidelity" cookbook:

```
Subject:  the man in the reference photo, ...
Scene:    <variant.scene or spec.background>
Style:    <aesthetic tone>
Lighting: <variant.lighting>
Camera:   photorealistic, DSLR, natural depth of field, realistic proportions
Identity & Realism: <identity lock>
Enhancement:        <subtle attractiveness>
Output:             <high detail, clean composition>

Change:      <scene + style + lighting>
Preserve:    face, facial features, skin tone, skin texture, eye shape,
             nose bridge, jawline, hairline, hair, body shape, pose,
             expression, framing. ...
Constraints: no face change, no airbrushing, no plastic skin, no watermark,
             no logo drift, no extra text, no extra objects, no redesign,
             no identity change
```

v1.23 extended the Preserve inventory with explicit anatomical
anchors (eye shape, nose bridge, jawline, hairline, framing) — GPT
Image 2 responds much better to an inventory than to a single
"preserve identity" clause.

### Nano Banana 2 — concise prose (v1.23)

Nano Banana 2 is backed by Gemini 3.1 Flash Image, a reasoning
model whose sweet spot per the fal.ai / Google prompting guides is
1-3 sentences per idea. v1.23 replaces the 8-block stack with a
3-paragraph prose prompt:

```
Keep the face, facial features, identity, skin tone, and expression
exactly as in the reference photo. Do not alter the person's face
in any way.

Show <subject> in <scene>, with <lighting>. Style: <style_tone>.
Camera: photorealistic, DSLR, natural depth of field, realistic
proportions. natural skin texture with visible pores and subtle
micro-imperfections, no plastic smoothing, no airbrushing.

Change only the environment, clothing styling, and lighting as
described. Preserve the subject's face, pose, hair, body
proportions, and framing exactly.
```

The identity anchor in paragraph 1 is the direct "do not alter
face" phrase from the Google portrait-preservation guide; the
skin-texture clause in paragraph 2 is the canonical anti-plastic /
anti-waxy anchor; paragraph 3 is the explicit change/preserve split
the fal NB2 guide recommends.

The adapter is read-only with respect to the style registry — it
does not modify any of the ~130 existing `StyleVariant` entries, so
rolling back leaves the hybrid prompt builder exactly as it was.

## Face fidelity pipeline (v1.23)

The A/B branch does NOT run the legacy face-restoration chain that
the StyleRouter path still uses. Specifically, on every A/B request:

- **GFPGAN preclean** (`src/services/face_prerestore.py`) is
  skipped. GFPGAN subtly re-renders facial features — when Nano
  Banana 2 or GPT Image 2 then edits a "precleaned" face, the edit
  models encode that slight drift and the final output looks
  unlike the user. Skipping preclean means the edit model sees the
  actual reference photo.
- **CodeFormer polish** (`fal-ai/codeformer`) is skipped. CodeFormer
  is a general face-restoration model, not an identity-preserving
  one; it subtly re-renders features in the output, which is
  exactly the regression we're trying to avoid.
- **Real-ESRGAN x2 upscale** (`fal-ai/real-esrgan`) is skipped. NB2
  at `high` already emits 4K and GPT-2 up to `2560×1440`; upscaling
  an already-native-resolution image only adds compression
  artefacts and doubles FAL spend.
- **Identity retry** (`ImageGenerationExecutor.single_pass`) is
  gated on the new `ab_identity_retry_enabled` flag (default
  `false`). The legacy retry escalates PuLID-specific parameters
  (`pulid_mode`, `id_scale`, `num_inference_steps`) that NB2 and
  GPT-2 silently strip — so a retry only produces a second
  generation on a fresh seed, doubles cost and latency, and does
  nothing to actually improve identity on the A/B models.

What the A/B path still runs:

- `_apply_local_postprocess` — a pure-PIL document-AR crop for CV
  styles. Never touches the face.
- VLM quality gate — identity_match and aesthetic_score are still
  computed and logged for analytics (`ratemeai_identity_score`
  histogram). They no longer trigger a retry, but they remain the
  on-call signal for identity-drift investigations.

Flag reference:

```
AB_IDENTITY_RETRY_ENABLED=false    # v1.23 default; flip to `true` to re-enable
IDENTITY_RETRY_ENABLED=true        # legacy StyleRouter path — independent
```

The legacy StyleRouter path keeps every stage above (GFPGAN
preclean, CodeFormer, Real-ESRGAN, PuLID identity retry) because
those models (PuLID + Seedream) were tuned for the chain and the
retry escalation actually feeds into PuLID's schema.

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
   → v1.23 disables the legacy CodeFormer / Real-ESRGAN / GFPGAN-
   preclean / identity-retry chain on the A/B path
   (see [Face fidelity pipeline](#face-fidelity-pipeline-v123)).
   If drift persists, first check `ratemeai_identity_score` histogram
   split by `backend` to quantify, then inspect the raw provider
   response bytes before any VLM call — the issue is almost
   certainly in the prompt (`src/prompts/ab_prompt.py`) or in the
   NB2 `thinking_level` / `aspect_ratio` parameters. Re-enabling
   retry with `AB_IDENTITY_RETRY_ENABLED=true` is a debugging
   escape hatch, not a fix.
4. Want to disable only one of the two A/B providers?
   → temporarily remove its key from `factory.AB_IMAGE_MODELS`;
   incoming `image_model=<disabled>` values drop to the default path.

# Prompt Pipeline v3 — author guide

_Status: rolled out May 2026 as part of the prompt-pipeline-overhaul.
All 126 styles in `data/styles.json` now ship in `schema_version: 3`._

This document explains what changed, why, and how to add or modify a
style under the new schema. It is the canonical reference for anyone
touching `data/styles.json`, `src/prompts/style_schema_v3.py`,
`src/prompts/slot_sampler.py`, or
`scripts/migrations/2026_05_styles_v3/`.

## TL;DR for style authors

A v3 style is built from three things:

1. **`trigger_pool`** — 3–6 equivalent English formulations of the
   headline motif (e.g. "Burj Khalifa rising in the background",
   "Burj Khalifa landmark visible in sharp detail"). The slot sampler
   picks one per generation. The user **cannot** disable this
   channel — it is the contract that "Burj Khalifa style" actually
   shows Burj Khalifa.

2. **`scene_anchor`** — a dry, language-neutral baseline scene
   description, free of lighting / weather / time-of-day phrases.
   Think "Parisian boulevard, café table, croissant" — *not* "golden
   hour Parisian boulevard with warm rim light".

3. **`ambient` pools** — per-channel whitelists for lighting, weather,
   `time_of_day`, season. Each channel is rolled at generation time
   if the user did not pin it explicitly. Empty pool = channel stays
   silent in the prompt.

That's the entire content surface. Everything else (`clothing`,
`framing`, `expression`, `quality_identity`, `output_aspect`,
`generation_mode`) is structural metadata the prompt engine
consumes mechanically.

## Why v3 exists

The v2 schema (Apr 2026) had three failure modes that we kept
patching ad hoc:

- **Hardcoded lighting in scene description.** `background.base`
  often read as "clean modern minimalist room, indirect lighting,
  warm ambient glow". When the user pinned `lighting=studio` the
  hint was layered on top of the existing description and the prompt
  contained two competing lighting modifiers.
- **Identical first generations.** `variation_engine_v2.apply_variation_v2`
  only randomised a channel when the user provided a hint. With no
  hints, ten different users got ten *identical* first prompts.
- **Missing motifs.** The `trigger` field was declared in
  `StyleSpecV2` but never reached `_assemble`. The "У зеркала"
  style produced prompts without the word "mirror" because the
  motif lived only in `overrides_allowed` (a list the engine
  ignored unless the user picked an alternative scene).

v3 collapses these into one rule: every prompt is a deterministic
function of `(StyleSpecV3, hints, seed)`. No more conditional
branches that silently leave channels empty; no more hidden
overrides from the scene description.

## Pipeline topology

```mermaid
flowchart LR
  Hints[user input_hints] --> Sampler
  Spec[StyleSpecV3] --> Sampler
  Seed[seed: int | None] --> Sampler
  Sampler[slot_sampler.sample] --> Resolved[ResolvedSlots]
  Resolved --> Builder[build_composition_v3]
  Builder --> IR[CompositionIR]
  IR --> Engine[PromptEngine]
  Engine --> Wrapper[model_wrappers]
  Resolved -->|"persisted in result_dict"| API[/api/v1/analyze response/]
  API --> UI[StepGenerate badges]
```

Key seams:

- **`src/prompts/slot_sampler.py::sample`** — the only place that
  consumes `(spec, hints, seed)` and decides which formulation /
  lighting / weather etc. ends up in the prompt. A pinned hint always
  beats a random pick from the pool. Out-of-pool hints fall back to
  soft substitution (we keep the user's free-text but flag it as a
  substitution so the UI can show "we couldn't honour exactly that").
- **`src/prompts/composition_builder.py::build_composition_v3`** —
  takes `ResolvedSlots`, builds a `CompositionIR`, and guarantees the
  trigger lands in `scene_line` even if the scene anchor itself does
  not contain it (defence in depth — the slot sampler already drops
  the trigger first, but the assertion catches authoring bugs).
- **`src/prompts/engine.py::build_image_prompt_v2`** — accepts
  `seed: int | None` and an `out_resolved_slots: dict` output param.
  When the v3 spec is registered for the requested style and the
  feature flag is on, this branch is taken; otherwise we fall back
  to the legacy v2 path.
- **`src/orchestrator/executor.py::single_pass`** — threads `seed`
  from the API request into the engine and copies the populated
  `out_resolved_slots` into `result_dict["resolved_slots"]`. The
  pipeline reads `seed` from the task `context`, which the API
  endpoint stores from the HTTP form field.

## Adding a new style

1. **Pick the headline motif.** Write 3–6 equivalent English
   formulations. They should be interchangeable for the model — if
   one of them visibly changes the composition, it's a separate
   style. Put them in
   `scripts/migrations/2026_05_styles_v3/curated.json` under your
   style key.
2. **Write the scene anchor.** One sentence. No lighting, no
   weather, no time-of-day. Use commas to separate independent
   clauses ("Parisian boulevard, café table, croissant"); the
   migration script and the runtime both treat commas as fragment
   boundaries.
3. **Decide which `ambient` channels apply.** Outdoor styles
   typically populate all four (lighting, weather, time_of_day,
   season). Indoor styles often skip weather. A studio style might
   skip everything except lighting. Fewer entries in a pool ⇒ less
   diversity but tighter brand fit.
4. **Add the row to `data/styles.json`.** The entry must include the
   v2 fields too (the v2 loader still reads them as a fallback view —
   see the design note in the next section). The migration script
   in `scripts/migrations/2026_05_styles_v3/migrate.py` shows the
   expected layout; running it against a v2-only entry produces the
   v3 fields automatically.
5. **Add tests.** Schema-level invariants are pinned by
   `tests/test_styles_v3_data.py`; per-style behaviour by the
   regression test in `tests/test_prompts/test_v2_motif_in_prompt.py`
   (extended in Stage 4 to cover all 126 styles).

## Backwards compatibility (v2 / v1 callers)

Stage 2 of the migration kept every v2 field intact alongside the
new v3 fields, so the v2 loader and v1 catalog endpoint continue
to work for any consumer that has not been updated:

- **`src/services/style_loader_v2.py::_to_v2`** accepts
  `schema_version in (2, 3)` and produces a v2 view from the
  preserved fields.
- **`src/services/style_catalog.py`** ships three projection
  helpers (`_v1_options_from_raw`, `_v2_slots_from_raw`,
  `_v3_slots_from_raw`) and the `/api/v1/catalog/styles/{id}/options`
  endpoint downgrades gracefully (`v3 → v2 → v1`) if the requested
  schema is not authored for that style. Today every row is v3, so
  the downgrade is a no-op — but the contract is in place for future
  admin imports.

## Per-channel UX contract

| Channel       | UI control (StyleSettingsModal) | Behaviour                                                                  |
|---------------|---------------------------------|----------------------------------------------------------------------------|
| `trigger`     | Read-only badge                 | Always rendered, never user-overridable                                    |
| `lighting`    | `<select>` (Авто + pool)        | Empty selection ⇒ random pick from `ambient.lighting`                       |
| `weather`     | Pill group (Авто + pool)        | Hidden when `ambient.weather` is empty                                     |
| `time_of_day` | Pill group (Авто + pool)        | Hidden when `ambient.time_of_day` is empty                                 |
| `season`      | Pill group (Авто + pool)        | Hidden when `ambient.season` is empty                                      |
| `clothing`    | Free text + chips               | Free text wins; chips are quick-pick suggestions from `clothing.allowed`   |
| `scene`       | Free text + chips               | Hidden when `background_lock == 'locked'` (passport / document styles)     |
| `framing`     | Pill group (По умолчанию + pool)| "По умолчанию" inherits the wizard step's framing                          |

## Available channels (1.29.0)

The "non-empty pool ⇒ visible" heuristic above is the **fallback**.
Curated styles use an explicit whitelist instead:

```jsonc
{
  "id": "mirror_aesthetic",
  "schema_version": 3,
  "available_channels": ["lighting", "time_of_day"],
  "location_type": "indoor",
  "ambient": {
    "lighting": ["soft ambient", "warm directional"],
    "time_of_day": ["morning", "evening"],
    "season": [],     // ignored — channel not whitelisted
    "weather": []
  }
}
```

Effect:

- The `StyleSettingsModal` renders **only** the channels listed in
  `available_channels` (lighting + time_of_day above). Season and
  weather are hidden — even if their pools were populated, the
  modal would still skip them.
- The `slot_sampler.sample()` call returns `""` for every channel
  outside the whitelist, regardless of pool contents and user hints.
  This is the defence-in-depth gate for cases where the modal
  somehow sends a hint for a disabled channel (legacy clients,
  curl experiments, ...).
- An empty `available_channels` (or an absent key) means **the
  style has not been curated yet**. The fallback heuristic kicks
  in: every channel with a non-empty pool stays visible. This
  preserves 1.28 behaviour for the 126 styles that landed before
  the field existed.

`location_type` is the lint engine's hint, not a runtime knob:

| `location_type` | Lint rules                                                         |
|-----------------|--------------------------------------------------------------------|
| `indoor`        | `season` and `weather` channels must NOT be in `available_channels`|
| `outdoor`       | (no extra rules)                                                   |
| `mixed`         | (no extra rules — used for styles that span both)                  |
| `document`      | No ambient channels at all (passport / id photos)                  |
| `""` (empty)    | Skip location-sensitive rules                                      |

## Admin curation workflow

Operators curate `available_channels` and `location_type` through
the web admin (`/admin/styles`):

1. **Open the catalog.** The list page shows lint badges per row
   (`clean` / `NE` / `NW`) and a top banner with the totals.
2. **Edit a style.** The "v3 / channels" tab in the editor exposes:
   - `location_type` dropdown
   - 7 channel checkboxes (one per `CONFIGURABLE_CHANNELS` entry)
   - `trigger_pool` array editor with per-row TRIGGER_DIRTY warnings
   - `scene_anchor` + `scene_overrides` editors
   - 4 ambient pool editors (CSV input each)
   - "Fill 4 seasons" shortcut when `season` is enabled
3. **Watch the live lint banner.** Every save round-trip refreshes
   `GET /api/v1/admin/styles/{id}/lint`; current issues render in
   an amber strip at the top of the modal.
4. **Resolve naming clashes.** Click "Conflicts report" in the
   header to view duplicate `display_label`s, similar labels
   (Levenshtein ≤ 2), and duplicate `id`s.

The lint engine itself lives in `src/services/style_lint.py`.
See `docs/admin-styles.md` for the operator-facing guide.

The "Другой вариант" button under a generated image fires
`StepGenerate.handleReroll`, which randomises a fresh 32-bit seed
client-side and resubmits the same `(style, hints)` pair. The
backend's slot sampler is guaranteed to produce a different
combination with overwhelming probability (the same-tuple birthday
collision rate is < 1% across the curated pools).

## Future work

- **`quality_identity.base` coverage.** Still empty for every style
  (Category C in `audit_report.md`). The plan is to bind it to model
  family rather than per-style: FLUX / GPT-Image / SD each get a
  curated quality block, and the prompt engine picks based on
  `target_model`. Tracked separately because it touches model
  routing, not slot sampling.
- **`expression` as a v3 channel.** Currently a single string on
  `StyleSpecV3` (the user can't roll between "smile" and "neutral").
  Promotable to an `ambient.expression` pool the moment we get a
  user request — the slot sampler is already shape-compatible.
- **Deprecation of `variation_engine_v2`.** The v2 path remains for
  unmigrated styles; today the codebase has none, but the v2 loader
  still emits v2 specs because the catalog API exposes them as a
  fallback. Once we are sure no external admin import path produces
  v2 rows, the legacy module can be deleted.

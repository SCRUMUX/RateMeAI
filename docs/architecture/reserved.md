# Reserved code — map, activation, and roadmap

This document describes the "reserved" parts of the codebase: modules
that are **not executed by the current runtime**, but are kept
deliberately as the foundation for future premium scenarios, provider
routing, and the Scenario Engine.

Everything outside this document is runtime and should stay runtime.
Everything listed here is *off by default*, isolated in well-named
files, and activated via explicit feature flags.

## 1. What "reserved" means here

- Not imported from the hot request path (`/analyze`, `/pre-analyze`,
  worker tasks, bot handlers).
- Exercised by unit tests where meaningful, to keep the interfaces
  stable as production code evolves.
- Documented with a module-level docstring stating that the module is
  reserved, why it is kept, and how to switch it on.

## 2. Map of reserved modules

> **History note (v1.71, May 2026).** The dormant
> `src/orchestrator/advanced/` subpackage (`planner.py`,
> `execute_plan.py`, `model_router.py`, `enhancement_levels.py`) was
> retired in the v1.71 cleanup — none of its modules were ever wired
> into the runtime, and the only artefact still consumed in production
> (`EnhancementLevel` / `LEVELS` / `level_for_depth`, used by the bot
> for the cartoon depth ladder) was inlined into
> `src/orchestrator/enhancement_matrix.py`. Multi-pass / compliance-loop
> orchestration will be reintroduced from scratch when the Scenario
> Engine epic lands (see §5 below).

### Reserved providers

No image-gen provider is currently reserved-but-unused.
`src/providers/image_gen/replicate.py`, `chain.py`, `fal_pulid.py`,
`fal_seedream.py` and `reve_provider.py` were all removed by
v1.70.7 — `UnifiedImageGen` handles GPT Image 2 + Nano Banana 2
fallback internally and the historical FAL adapters have no
runtime consumers.

Mock providers live under `src/providers/_testing/` and are **not**
reserved — they are the runtime for dev/CI and explicitly off the
production path (see `IMAGE_GEN_PROVIDER=mock`).

### Reserved services

| Module | Status |
|---|---|
| `src/services/segmentation.py` | `SegmentationService` — MediaPipe region masks (face / body / background / clothing). Not instantiated by `AnalysisPipeline` after Phase 1; reactivated by the Scenario Engine together with `SEGMENTATION_ENABLED=true` and a scenario whose `pipeline_profile = "advanced"`. |

## 3. How to activate reserved code

All switches are environment variables read through `src.config.settings`.

| Flag | Default | What it unlocks |
|---|---|---|
| `SEGMENTATION_ENABLED` | `false` | Enables MediaPipe region masks. Will be consumed by the future Scenario-Engine advanced pipeline. |
| `IMAGE_GEN_PROVIDER` | `mock` (dev) / `unified` (prod) | Switches between image-gen providers for debugging. |

## 4. Use cases this code is preserved for

1. **Premium HD retouch** — multi-step pipeline with per-region gates
   (face/skin/hair/background), N-variant generation, budget cap.
2. **Document compliance scenarios** — e.g. `passport_rf`, `visa_eu`:
   one-shot generation cannot satisfy both anatomy + neutral
   background + aspect ratio simultaneously; a compliance-loop with
   per-step gate retries is the intended design.
3. **Marketplace / meme content** — scenario-specific fallback chains
   depending on whether realism or graphics-heavy generation is needed.
4. **Inpaint masks** — region-scoped prompts (face-only, clothing-only)
   remain the long-term plan for document fix-ups and were what the
   retired planner's `region` field was designed around.

## 5. Roadmap

- **Phase 1 — done.** Hard-remove unequivocally dead code, document
  what is reserved and why (this file).
- **Phase 2 — Scenario Engine.** Introduce `src/scenarios/` with a
  `Scenario` dataclass (`pipeline_profile = "simple" | "advanced"`,
  `delta_keys`, `preferred_provider_hint`). Migrate the existing five
  `AnalysisMode` values into scenarios 1:1; pilot `document_passport_rf`
  as proof-of-concept. `pipeline_profile = "advanced"` will introduce
  a fresh multi-pass executor scoped to that scenario only.
- **Phase 3 — Capability-based provider routing.** Add a `ModelRouter`
  / `ModelSpec` layer once the Scenario Engine ships, scoped to the
  Scenario Engine surface and not to the legacy runtime path.
- **Phase 4 — Edge isolation.** Fold the `settings.uses_remote_ai`
  branches into a dedicated `LocalComputeRouter` / `RemoteComputeRouter`
  abstraction.

Each phase ships as its own plan and is reviewed independently.

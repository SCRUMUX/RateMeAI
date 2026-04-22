# Reserved code — map, activation, and roadmap

This document describes the "reserved" parts of the codebase: modules
that are **not executed by the current runtime**, but are kept
deliberately as the foundation for future premium scenarios, provider
routing, and the Scenario Engine. They are not dead code.

Everything outside this document is runtime and should stay runtime.
Everything listed here is *off by default*, isolated in well-named
subpackages, and activated via explicit feature flags.

## 1. What "reserved" means here

- Not imported from the hot request path (`/analyze`, `/pre-analyze`,
  worker tasks, bot handlers).
- Exercised by unit tests where meaningful, to keep the interfaces
  stable as production code evolves.
- Documented with a module-level docstring stating that the module is
  reserved, why it is kept, and how to switch it on.
- Lives under a clearly marked location:
  - `src/orchestrator/advanced/` for multi-pass orchestration;
  - specific provider files under `src/providers/image_gen/` (with
    per-file docstrings).

## 2. Map of reserved modules

### `src/orchestrator/advanced/`

| Module | Purpose |
|---|---|
| `planner.py` | Declares a `PipelinePlan` = N structured `PipelineStep`s per mode/style. Used by advanced scenarios that need per-region gate retries and budget enforcement. |
| `execute_plan.py` | `AdvancedPipelineExecutor` — runs a `PipelinePlan` with intermediate storage, per-step model routing, cost tracking and global quality-gate validation on the final result. |
| `model_router.py` | `ModelRouter` + `ModelSpec` + `build_model_registry`. Capability-based model selection (tier, cost, provider). Foundation for the future FLUX vs Reve router. |
| `enhancement_levels.py` | `EnhancementLevel`, `LEVELS`, `level_for_depth`. Maps user-facing "enhancement depth" to a set of pipeline steps. Consumed exclusively by `planner.py`; the `SCENARIO_STYLES` / `matrix_stats` statistics layer stays in `enhancement_matrix.py` and is runtime. |

Legacy shim files at `src/orchestrator/planner.py` and
`src/orchestrator/model_router.py` have been removed. Import from
`src.orchestrator.advanced.planner` and
`src.orchestrator.advanced.model_router` directly.

### Reserved providers

| Module | Status |
|---|---|
| `src/providers/image_gen/replicate.py` | Disabled in runtime (`IMAGE_GEN_PROVIDER=reve`). Kept as a FLUX/FAL baseline and a manual override for debugging. |
| `src/providers/image_gen/chain.py` | `ChainImageGen` fallback wrapper. Not used today; will be reactivated from the Scenario Engine when `Scenario.preferred_provider_hint` lands. |

Mock providers live under `src/providers/_testing/` and are **not**
reserved — they are the runtime for dev/CI and explicitly off the
production path (see `IMAGE_GEN_PROVIDER=mock`).

### Reserved services

| Module | Status |
|---|---|
| `src/services/segmentation.py` | `SegmentationService` — MediaPipe region masks (face / body / background / clothing). Not instantiated by `AnalysisPipeline` after Phase 1; reactivated by the Scenario Engine together with `SEGMENTATION_ENABLED=true` and a scenario whose `pipeline_profile = "advanced"` (consumed by `AdvancedPipelineExecutor` for per-region steps in document-compliance and HD retouch pipelines). |

## 3. How to activate reserved code

All switches are environment variables read through `src.config.settings`.

| Flag | Default | What it unlocks |
|---|---|---|
| `MULTI_PASS_ENABLED` | `false` | Enables the multi-pass planner/executor in the pipeline. **Note:** today's `AnalysisPipeline` does not wire this in; it will be re-enabled by the Scenario Engine (Phase 2) for scenarios whose `pipeline_profile = "advanced"`. |
| `SEGMENTATION_ENABLED` | `false` | Enables MediaPipe region masks, used by advanced planner steps. |
| `IMAGE_GEN_PROVIDER` | `reve` | Set to `replicate` to fall back to FLUX-on-Replicate for debugging; `mock` for dev. |

Example:

```bash
# Re-enable reserved advanced path (only when the Scenario Engine wires it in)
MULTI_PASS_ENABLED=true
SEGMENTATION_ENABLED=true

# Use reserved Replicate provider for comparison runs
IMAGE_GEN_PROVIDER=replicate
```

## 4. Use cases this code is preserved for

1. **Premium HD retouch** — multi-step pipeline with per-region gates
   (face/skin/hair/background), N-variant generation, budget cap.
2. **Document compliance scenarios** — e.g. `passport_rf`, `visa_eu`:
   one-shot generation cannot satisfy both anatomy + neutral
   background + aspect ratio simultaneously; a compliance-loop with
   per-step gate retries is the intended design.
3. **Marketplace / meme content** — scenario-specific fallback chains
   (Reve → FLUX → Reve stylised) depending on whether realism or
   graphics-heavy generation is needed.
4. **Capability-based provider routing** — the forthcoming
   `FluxFALProvider` plugs into `ModelRouter` as a high-realism tier,
   with Reve kept as the meme / marketplace tier.
5. **Inpaint masks** — region-scoped prompts (face-only, clothing-only)
   remain the long-term plan for document fix-ups and are what the
   planner's `region` field was designed around.

## 5. Roadmap

- **Phase 1 — this cleanup.** Hard-remove unequivocally dead code,
  isolate multi-pass machinery under `orchestrator/advanced/`,
  document what is reserved and why (this file).
- **Phase 2 — Scenario Engine.** Introduce `src/scenarios/` with a
  `Scenario` dataclass (`pipeline_profile = "simple" | "advanced"`,
  `delta_keys`, `preferred_provider_hint`). Migrate the existing five
  `AnalysisMode` values into scenarios 1:1; pilot `document_passport_rf`
  as proof-of-concept. `pipeline_profile = "advanced"` re-enables
  `AdvancedPipelineExecutor` on that scenario only.
- **Phase 3 — FLUX via FAL.ai.** Add `src/providers/image_gen/fal_flux.py`,
  plug it into `ModelRouter` as a high-realism tier, shadow-mode on
  5–10% of dating traffic, compare metrics, roll out gradually.
- **Phase 4 — Edge isolation.** Fold the `settings.uses_remote_ai`
  branches into a dedicated `LocalComputeRouter` / `RemoteComputeRouter`
  abstraction.

Each phase ships as its own plan and is reviewed independently. Phase 1
(current) ships with zero runtime behaviour change.

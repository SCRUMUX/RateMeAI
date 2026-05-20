# v1 Style Registration Audit (Phase 3.4)

**Date:** 2026-05-20  
**App version at audit:** 1.70.18  
**Triggered by:** [Tech Debt Cleanup Roadmap](../../.cursor/plans/tech_debt_cleanup_6d62c6ef.plan.md) — Phase 3, Step 3.4.

## Question

The roadmap asked whether the v1 registration pass in `src/prompts/image_gen.py`
bootstrap (`get_structured_specs() → STYLE_REGISTRY.register(spec)`) is a
removable duplicate, now that v2 bootstrap is gone (Phase 3.3, v1.70.18) and
every entry in `data/styles.json` is natively `schema_version: 3`.

> *Аудит: используется ли `_v1_by_key` / `StructuredStyleSpec` хоть где-то в
> runtime hot path? Если только в legacy fallback'ах (которых уже нет) —
> удалить.*

## Findings — v1 is NOT a duplicate

`STYLE_REGISTRY.get(mode, style)` / `.get_or_default(...)` are called from
**production hot path** code that needs fields v3 does not expose flatly:

| Caller (file:line) | Field(s) consumed | v3 equivalent? |
| --- | --- | --- |
| `src/orchestrator/executor.py:693` (framing resolver) | `needs_full_body`, `needs_torso` | yes (would migrate cleanly) |
| `src/orchestrator/executor.py:857` (output size resolve) | `output_aspect`, `needs_full_body` | yes (would migrate cleanly) |
| `src/services/input_quality.py:646` (CSL gate) | `needs_full_body`, `needs_torso` | yes (would migrate cleanly) |
| `src/bot/handlers/mode_select.py:137,398` (UX warnings) | `needs_full_body`, `needs_torso`, framing | yes (would migrate cleanly) |
| `src/prompts/image_gen.py:706` (`get_style_text`) | `needs_full_body` | yes |
| `src/prompts/image_gen.py:762` (`resolve_style_variant`) | `spec.variant_by_id(variant_id)` | **NO** — v3 has no `variants` |
| `src/prompts/image_gen.py:806` (`build_step_prompt`) | `expression`, `clothing_for(gender)`, `background` | **NO** — v3 splits these into `ClothingSlot` + `scene_anchor` pools |

The two blocking gaps — `variants` (used by the "Другой вариант" UX in the
bot) and the flat `background` / `clothing_for(gender)` surface used by
`build_step_prompt` — mean we cannot drop the v1 registration pass without a
larger refactor that:

1. Adds a `StyleSpecV3.variant_by_id`-equivalent surface, OR migrates the
   bot's "Другой вариант" flow to use v3 `ambient` / `scene_overrides` pools.
2. Either deletes `build_step_prompt` (called only by the dormant multi-pass
   executor, `multi_pass_enabled` retired in v1.70.14) or migrates it to
   pull `default_clothing` / `expression` directly from the raw JSON.

Neither change is in-scope for the Phase 3 cleanup roadmap, which focuses on
the **schema-bootstrap** surface, not the runtime call surface.

## Conclusion

- **Do NOT remove** `get_structured_specs()` / `STYLE_REGISTRY.register(...)`
  / `_by_key` / `StructuredStyleSpec` in this pass.
- The v1 registry path is the **runtime source of truth** for
  `output_aspect` / `needs_full_body` / `needs_torso` / `.variant_by_id(...)`
  / `.clothing_for(gender)` lookups across orchestrator, input-quality gate,
  bot handlers, and prompt builders.
- Phase 3.4 is marked **complete (audit-only)**. The follow-up — migrating
  the seven listed call sites to `StyleSpecV3` so the v1 registration can
  finally be dropped — is captured below and should be scheduled as its own
  multi-step cycle.

## Follow-up tasks (not in this roadmap)

1. Extend `StyleSpecV3` (or `style_loader_v3`) with the legacy fields the
   runtime still needs: `variants`, `default_clothing`, `expression`. Some
   of these are already in `data/styles.json` and only need a thin loader
   shim.
2. Replace `STYLE_REGISTRY.get(mode, style)` callers with `get_v3(...)` and
   inline the new helpers.
3. Drop `StructuredStyleSpec`, `get_structured_specs`,
   `STYLE_REGISTRY.register` / `_by_key` and the v1 fallback block in
   `image_gen.py`. Expected savings: ~120 LoC + one bootstrap pass.

## Code-level signal

To make this finding visible to anyone reading the code, the v1 loader's
module docstring (`src/services/style_loader.py`) was updated to drop the
"unexpected edge cases" framing and explicitly mark the converter as
**runtime authoritative** with a reference to this audit file.

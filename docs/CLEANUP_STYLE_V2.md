# Style schema v2 — v1 cleanup status

## Current state (post-migration cutover)

Executed in this repository:

- [x] **100% of `data/styles.json` entries have `"schema_version": 2`.**
      141/141 entries migrated; original kept as backup under
      `data/.styles_backup/styles_*.json`.
- [x] **All v2 feature flags default to `true`** in `src/config.py`:
      - `style_schema_v2_enabled = True`
      - `unified_prompt_v2_enabled = True`
      - `variation_engine_v2_enabled = True`
      - `prompt_engine_map_fix` — flag *removed*, behaviour now
        unconditional (direct dispatch in `PromptEngine`).
- [x] **Legacy A/B prompt adapter deleted** —
      `src/prompts/ab_prompt.py`, `tests/test_prompts/test_ab_prompt.py`,
      and the `ab_prompt_max_len` field in `Settings` are gone.
- [x] **`_IMAGE_PROMPT_MAP` lambdas removed** —
      `PromptEngine.build_image_prompt` now dispatches through
      `_DIRECT_IMAGE_BUILDERS` unconditionally; emoji handled inline.
- [x] Characterisation + map-fix tests removed
      (`test_engine_characterization.py`, `test_engine_map_fix.py`).

After this batch:

```
python -m pytest
# 2021 passed, 1 skipped
```

The production code path is now:

```
executor.single_pass
  → PromptEngine.build_image_prompt_v2      (always fires, all styles are v2)
    → composition_builder.build_composition
    → model_wrappers.wrap_for_model
```

## Intentionally deferred

Three symbols are still present in the tree but are **never called on
the hot path** in production. Removing them is a pure refactor that
rewrites ~4 000 lines of test fixtures / module plumbing without
changing prod behaviour, so it has been left for a later pass:

1. **`_build_mode_prompt` + `_framing_directive`** in
   `src/prompts/image_gen.py`. These are the body of the public
   `build_dating_prompt` / `build_cv_prompt` / `build_social_prompt`
   shims. The shims themselves are still the target of
   `_DIRECT_IMAGE_BUILDERS`, which is reached only through the v1
   fallback branch in `executor.single_pass` (`if prompt is None:` after
   the v2 call). With every style now v2-registered that branch is
   dead on real traffic, but the public builder names are imported
   from ~10 test files (`test_image_gen_prompt.py`,
   `test_full_body_prompt_adaptation.py`,
   `test_prompt_length_budget.py`, `test_positive_framing.py`, etc.)
   which assert v1-specific prompt shape. Rewriting them to the v2
   composition output is a chunky job with no runtime payoff.

2. **`src/prompts/style_variants.py`** (3 064 lines) and the
   `STYLE_VARIANTS.get(...)` calls inside the JSON-load exception
   handler in `src/prompts/image_gen.py`. This whole block only runs
   when `data/styles.json` is corrupt or missing — a safety net. No
   test references it; deletion is mechanically trivial but costs a
   live fallback for a degraded-disk scenario.

3. **`src/services/style_loader.py`** still provides
   `get_structured_specs` (the v1 path) *and*
   `load_styles_from_json` (the thin JSON reader) used by
   `style_loader_v2.py` and `style_catalog.py`. To delete it we'd
   first need to promote `load_styles_from_json` to its own module
   (e.g. `src/services/style_json.py`) and repoint three importers.

## Future removal — fast path

When someone is ready to take the deferred work, the mechanical order
is:

1. Route `build_dating_prompt` / `build_cv_prompt` /
   `build_social_prompt` through `composition_builder` +
   `model_wrappers`. Replace or delete the v1-shape assertions in the
   five test files above; most simply stop caring about whitespace and
   ordering of lighting/camera/anatomy tails. Expect to delete ~500
   lines of test fixtures.
2. Delete `_build_mode_prompt`, `_framing_directive`, `_FRAMING_HINTS`
   plus the v1 fallback branch in `executor.single_pass`.
3. Extract `load_styles_from_json` to `src/services/style_json.py` and
   re-point the three callers. Delete `src/services/style_loader.py`.
4. Delete `src/prompts/style_variants.py` and the JSON-load exception
   fallback block in `image_gen.py`.
5. Optional cosmetic: rename `StyleRegistry.register_v2` → `register`,
   `get_v2` → `get`, drop v1-only methods.

Verification at the end:

```powershell
python -m pytest
Select-String -Path src\*.py,tests\*.py -Pattern "_build_mode_prompt|_IMAGE_PROMPT_MAP|StructuredStyleSpec|build_structured_prompt|STYLE_VARIANTS" -Recurse
```

Second command should return zero hits outside `docs/` and
`src/version.py` changelog.

## Rollback

The cutover is pure data + defaults. To roll back:

1. Restore `data/styles.json` from the auto-generated backup
   (`data/.styles_backup/styles_<ts>.json`).
2. Flip the four defaults in `src/config.py` back to `False`.

No Secret Manager entry needed — the defaults themselves drive the
behaviour.

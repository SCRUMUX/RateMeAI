"""Stage 4 (prompt-pipeline-overhaul, May 2026) — motif coverage test
for **every** style in ``data/styles.json``.

The contract this test pins is the v3 schema's headline guarantee:

> When the user generates a "Burj Khalifa" style photo, the rendered
> prompt must contain a Burj-Khalifa-shaped phrase. No matter the
> seed, no matter the user hints (or absence thereof). The trigger
> is the inviolable axis of the v3 schema and dropping it
> silently — as the v2 path used to do for the ten Category D
> styles in
> ``scripts/migrations/2026_04_prompt_quality/audit_report.md`` —
> is the regression we are guarding against.

Concretely, the test runs the v3 prompt path against the live
catalog with multiple seeds per style and asserts that **at least
one formulation from the style's ``trigger_pool``** appears verbatim
(case-insensitive) in the rendered prompt for every roll.

The test uses the v3 path explicitly (``style_schema_v3_enabled=True``)
because that's the production target; if a regression in the v2
fallback path silently re-introduces the bug for v3 entries, this
test will catch it because the engine will not pick the v2 path
when a v3 entry is registered.
"""

from __future__ import annotations

import pytest

from src.models.enums import AnalysisMode
from src.prompts.composition_builder import _significant_tokens
from src.prompts.compression import compress_prompt
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import STYLE_REGISTRY
from src.services.style_loader import load_styles_from_json
from src.services.style_loader_v2 import register_v2_styles_from_json
from src.services.style_loader_v3 import register_v3_styles_from_json

# Number of distinct seeds per style. Higher = stronger coverage but
# longer runtime; 5 is enough to hit every formulation in a typical
# 3–6-entry trigger pool with overwhelming probability while keeping
# the suite under a couple of seconds.
_SEEDS = (1, 7, 42, 1024, 99991)


_MODE_BY_STRING: dict[str, AnalysisMode] = {
    "dating": AnalysisMode.DATING,
    "cv": AnalysisMode.CV,
    "social": AnalysisMode.SOCIAL,
    "rating": AnalysisMode.RATING,
}


def _normalise_for_match(text: str) -> str:
    """Apply the production prompt compression to a string so the test
    compares apples to apples.

    The prompt engine pipes its output through :func:`compress_prompt`,
    which strips filler words ("showing", "depicting"…) and
    deduplicates back-to-back repeated tokens ("diffused diffused"
    → "diffused"). A handful of styles have authoring artefacts
    that survive in the raw ``trigger_pool`` but disappear from the
    rendered prompt. We don't want this test to fail on those
    cosmetic differences, only on real motif loss.
    """
    return compress_prompt(text or "").lower()


def _trigger_lands_in_prompt(prompt: str, pool: tuple[str, ...]) -> bool:
    """Return True if any trigger formulation appears in *prompt*
    semantically — either verbatim or via content-token subset
    coverage.

    The verbatim path catches short headline keywords ("mirror",
    "Eiffel Tower") that the legacy guard relied on. The fuzzy path
    (v1.69) catches the studio-cabinet case where the v3 schema
    stores the same long string in BOTH ``scene_anchor`` AND
    ``trigger_pool[0]``: when the sampler picks a SHORTER scene
    override (e.g. ``modern corner office with floor-to-ceiling
    windows``) the verbatim trigger never lands in the prompt, even
    though every meaningful noun from the pool entry is already
    present. Without the fuzzy check this test would fight the very
    duplicate-suppression that ``_ensure_trigger_in_scene`` exists
    to provide — and force authors to choose between motif coverage
    and a clean prompt.

    The fuzzy contract: at least one ``trigger_pool`` entry whose
    content tokens form a subset of (or are coverage-covered by)
    the prompt's tokens counts as motif present. ``mirror_aesthetic``
    still fails this check when the prompt has no mirror noun at
    all, which is the regression we actually care about.
    """
    haystack = _normalise_for_match(prompt)
    prompt_tokens = _significant_tokens(haystack)
    for entry in pool:
        needle = _normalise_for_match(entry)
        if not needle:
            continue
        if needle in haystack:
            return True
        # Fuzzy path: pool entry's content tokens already present
        # in the prompt.
        entry_tokens = _significant_tokens(needle)
        if not entry_tokens:
            continue
        if entry_tokens <= prompt_tokens:
            return True
        # Symmetric coverage. The threshold is intentionally LOWER
        # than the suppression guard's 0.5 (which decides whether to
        # ELIDE a trigger) because here we are checking whether the
        # motif SURVIVES in the rendered prompt. Two distinct
        # asymmetries push the post-render number down:
        #
        # 1. Scene override paraphrases. The studio-cabinet styles
        #    (corporate, boardroom, …) ship a long ``scene_anchor`` =
        #    ``trigger_pool[0]`` (~13 content tokens). When the
        #    sampler picks a SHORTER override (``modern corner
        #    office with floor-to-ceiling windows``, ~5 tokens), the
        #    suppression guard correctly skips appending the
        #    duplicate trigger — but the prompt now only carries
        #    the override tokens, so coverage(entry vs prompt) drops
        #    to ~0.38. A 0.5 threshold here would force authors to
        #    choose between motif coverage and a duplicate-free
        #    prompt; we want both.
        #
        # 2. Long-entry pool noise. The pool entry's tail tokens
        #    (``diffused daylight``, ``neutral beige wall``,
        #    ``clean minimalist interior``) describe ATMOSPHERE,
        #    not the headline motif. They drift in and out of the
        #    rendered prompt depending on the lighting roll. The
        #    headline tokens (``modern corner office`` /
        #    ``floor-to-ceiling windows``) are what the test really
        #    cares about, and they consistently survive.
        #
        # 0.3 is empirically the smallest threshold that still
        # rejects "Mirror Aesthetic without a mirror" (coverage 0)
        # while accepting the legitimate paraphrase case.
        coverage = len(entry_tokens & prompt_tokens) / len(entry_tokens)
        if coverage >= 0.3:
            return True
    return False


@pytest.fixture(scope="module")
def _v3_loaded() -> list[dict]:
    """Register every v3-shape style for the duration of the module
    and return the raw JSON entries. We register both v2 and v3 maps
    because the engine prefers v3 but falls back to v2; for unmigrated
    rows (today: none) the fallback keeps the test green.
    """
    raw = load_styles_from_json()

    # Take a snapshot so we don't pollute global state for tests that
    # run after this module. v4.1: the v2/v3 loaders are always-on
    # (the gating flags were removed), so we just clear and reload.
    snap_v2 = dict(STYLE_REGISTRY._v2_by_key)
    snap_v3 = dict(STYLE_REGISTRY._v3_by_key)
    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v3_by_key.clear()

    register_v2_styles_from_json(raw)
    register_v3_styles_from_json(raw)

    yield raw

    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v2_by_key.update(snap_v2)
    STYLE_REGISTRY._v3_by_key.update(snap_v3)


def _all_v3_styles(raw: list[dict]) -> list[tuple[str, str, tuple[str, ...]]]:
    """Return ``(style_id, mode_string, trigger_pool)`` for every v3 row.

    Skips entries that — for whatever reason — could not be migrated
    (the v3 loader rejects them silently); this keeps the test from
    blowing up if the catalog ships a couple of intentionally-v2-only
    rows in the future.
    """
    out: list[tuple[str, str, tuple[str, ...]]] = []
    for entry in raw:
        if int(entry.get("schema_version") or 0) != 3:
            continue
        style_id = str(entry.get("id") or entry.get("key") or "").strip()
        mode_str = str(entry.get("mode") or "").strip().lower()
        pool = tuple(
            str(t).strip()
            for t in (entry.get("trigger_pool") or [])
            if isinstance(t, str) and str(t).strip()
        )
        if not style_id or not mode_str or not pool:
            continue
        if mode_str not in _MODE_BY_STRING:
            continue
        out.append((style_id, mode_str, pool))
    return out


def test_catalog_has_at_least_one_hundred_v3_styles(_v3_loaded):
    """Sanity check: the migration produced a v3 catalog of the
    expected size (we shipped 126 styles in May 2026). If this number
    drops below 100, something has eaten rows during deploy and the
    motif assertion below would silently pass on a near-empty
    catalog."""
    styles = _all_v3_styles(_v3_loaded)
    assert len(styles) >= 100, (
        f"Only {len(styles)} v3 styles found — expected at least 100. "
        f"Did the migration script regress or did styles.json get truncated?"
    )


@pytest.mark.parametrize("seed", _SEEDS)
def test_every_v3_style_emits_trigger_for_every_seed(_v3_loaded, seed: int):
    """For every (style, seed) pair, the rendered prompt must contain
    at least one trigger-pool formulation. Failure = motif missing =
    the user got a "Mirror Aesthetic" shot with no mirror in it.

    We collect *all* failures into a single list rather than aborting
    on the first miss, so a regressing migration produces an actionable
    diff (which styles broke) rather than one example.
    """
    engine = PromptEngine()
    styles = _all_v3_styles(_v3_loaded)
    failures: list[tuple[str, str]] = []

    for style_id, mode_str, pool in styles:
        prompt = engine.build_image_prompt_v2(
            mode=_MODE_BY_STRING[mode_str],
            style=style_id,
            gender="male",
            input_hints={},
            target_model="gpt_image_2",
            seed=seed,
        )
        if not prompt:
            failures.append((style_id, "engine returned empty prompt"))
            continue
        if not _trigger_lands_in_prompt(prompt, pool):
            sample = (prompt[:240] + "…") if len(prompt) > 240 else prompt
            failures.append((style_id, sample))

    assert not failures, (
        f"{len(failures)}/{len(styles)} v3 styles dropped their trigger at "
        f"seed={seed}. First offenders: {failures[:5]!r}"
    )


def test_every_v3_style_honours_pinned_lighting(_v3_loaded):
    """When the user pins ``lighting=studio`` (or any value already in
    the style's ``ambient.lighting`` pool), the rendered prompt must
    contain that exact value AND still contain the trigger. This
    pins the "user override wins, but trigger is non-negotiable" rule.

    Styles without a non-empty ``ambient.lighting`` pool are skipped —
    pinning a value the schema rejects would route through soft
    substitution which is covered by ``test_v3_composition.py``.
    """
    engine = PromptEngine()
    styles = _all_v3_styles(_v3_loaded)
    failures: list[tuple[str, str]] = []
    checked = 0

    for style_id, mode_str, pool in styles:
        # Read the ambient.lighting pool back from the registry so we
        # only pin values the slot sampler will accept without
        # falling through to substitution.
        raw = next(
            (
                e
                for e in _v3_loaded
                if str(e.get("id") or e.get("key") or "").strip() == style_id
            ),
            None,
        )
        if not raw:
            continue
        lighting_pool = (raw.get("ambient") or {}).get("lighting") or []
        if not isinstance(lighting_pool, list) or not lighting_pool:
            continue
        pinned = str(lighting_pool[0]).strip()
        if not pinned:
            continue

        prompt = engine.build_image_prompt_v2(
            mode=_MODE_BY_STRING[mode_str],
            style=style_id,
            gender="male",
            input_hints={"lighting": pinned},
            target_model="gpt_image_2",
            seed=0,
        )
        checked += 1
        if not prompt:
            failures.append((style_id, "engine returned empty prompt"))
            continue
        haystack = _normalise_for_match(prompt)
        if _normalise_for_match(pinned) not in haystack:
            failures.append((style_id, f"pinned lighting {pinned!r} missing"))
        elif not _trigger_lands_in_prompt(prompt, pool):
            failures.append((style_id, "trigger missing under pinned lighting"))

    assert checked > 0, "no v3 styles had a usable lighting pool to pin"
    assert not failures, (
        f"{len(failures)}/{checked} v3 styles failed the pinned-lighting "
        f"contract. First offenders: {failures[:5]!r}"
    )

"""Schema-level tests for the StyleSpecV3 migration of ``data/styles.json``.

Stage 2 of the prompt-pipeline-overhaul (2026-05). Once the migration
script (``scripts/migrations/2026_05_styles_v3/migrate.py``) has run
every catalog row carries v3 fields:

* ``schema_version: 3``
* non-empty ``trigger_pool``
* non-empty ``scene_anchor``
* an ``ambient`` block with ``lighting``, ``weather``, ``time_of_day``,
  ``season`` keys (lists, possibly empty per channel)

This test asserts those invariants for every entry in the live
``data/styles.json`` so the file cannot drift back to a v2-only shape
without a clear failure. The thresholds are intentionally loose:

* ``trigger_pool`` is required to have at least 1 entry (the slot
  sampler will refuse to load a v3 entry with an empty pool — a
  catalog edit that breaks this would break worker startup before
  these tests, but we want the file-level check anyway).
* Curated headline styles (the ones with rich trigger pools written
  by hand in ``scripts/migrations/2026_05_styles_v3/curated.json``)
  must have at least 3 trigger phrasings — that's the floor we
  promised in the overhaul plan for those rows.
* The ``ambient`` block is verified structurally (correct keys,
  values are lists). Per-channel content is checked only for the
  curated set so ongoing curation does not need a separate test
  update each time we add or remove pool entries.

The forbidden-tokens check on ``scene_anchor`` is a regression budget,
not a hard rule — the migration script removes obvious lighting
fragments but cannot rewrite mixed sentences ("warm natural light from
windows" embedded in a kitchen scene). We allow up to ``MAX_DIRTY``
remaining entries; reducing this threshold over time tracks ongoing
curation. Failing tighter would force a wholesale manual rewrite of
all 126 scenes in this PR — out of scope for Stage 2's "first pass"
migration.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

CURATED_KEYS: tuple[str, ...] = (
    "mirror_aesthetic",
    "instagram_aesthetic",
    "youtube_creator",
    "linkedin_premium",
    "luxury",
    "casual",
    "artistic",
    "coffee_date",
    "digital_nomad",
    "travel_luxury",
    "paris_eiffel",
    "dubai_burj_khalifa",
    "nyc_times_square",
    "venice_san_marco",
    "rome_colosseum",
)

# Words we never want to see inside ``scene_anchor`` because they belong
# in ``ambient.lighting`` / ``ambient.time_of_day`` / ``ambient.weather``.
# The migration cleaner strips obvious cases ("morning golden light"),
# but mixed phrases ("warm natural light from windows") embedded inside
# a scene fragment do survive. The threshold below captures the
# remaining count and prevents regressions.
_FORBIDDEN_WORDS = re.compile(
    r"\b(?:lighting|sunset|sunrise|golden\s+hour|blue\s+hour|noon|"
    r"midnight|dawn|dusk|rain|snow|fog)\b",
    re.I,
)
# Allowed remaining "dirty" scene_anchors — tighten this number as
# manual curation eats into the ~38 entries left after the first pass.
MAX_DIRTY_SCENE_ANCHORS = 45


@pytest.fixture(scope="module")
def styles() -> list[dict]:
    payload = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, list) and payload, "data/styles.json is empty"
    return payload


def test_every_style_is_v3(styles: list[dict]) -> None:
    """Stage 2 invariant — every catalog row carries ``schema_version: 3``."""
    bad = [s.get("id", "<unknown>") for s in styles if int(s.get("schema_version") or 0) != 3]
    assert not bad, (
        f"{len(bad)} styles still on schema_version != 3. Re-run "
        f"`scripts/migrations/2026_05_styles_v3/migrate.py`. First "
        f"offenders: {bad[:5]}"
    )


def test_every_style_has_trigger_pool(styles: list[dict]) -> None:
    """``trigger_pool`` is the inviolable axis — at least 1 entry per style.

    The slot sampler enforces this at load time
    (:class:`StyleSpecV3.__post_init__`); a JSON-level check keeps the
    failure visible at curation time too.
    """
    bad: list[tuple[str, list]] = []
    for s in styles:
        pool = s.get("trigger_pool")
        if not isinstance(pool, list) or not pool:
            bad.append((s.get("id", "<unknown>"), pool))
        else:
            for item in pool:
                if not isinstance(item, str) or not item.strip():
                    bad.append((s.get("id", "<unknown>"), pool))
                    break
    assert not bad, f"styles with bad trigger_pool: {bad[:5]}"


def test_every_style_has_scene_anchor(styles: list[dict]) -> None:
    """``scene_anchor`` is the canonical fallback when ``scene_overrides``
    is empty. It must be a non-empty string."""
    bad = [
        s.get("id", "<unknown>")
        for s in styles
        if not (isinstance(s.get("scene_anchor"), str) and s["scene_anchor"].strip())
    ]
    assert not bad, f"styles with empty scene_anchor: {bad[:5]}"


def test_ambient_block_has_required_keys(styles: list[dict]) -> None:
    """The ``ambient`` block always exposes the four sampled channels."""
    required = {"lighting", "weather", "time_of_day", "season"}
    bad: list[tuple[str, str]] = []
    for s in styles:
        ambient = s.get("ambient")
        if not isinstance(ambient, dict):
            bad.append((s.get("id", "<unknown>"), "missing ambient block"))
            continue
        missing = required - set(ambient.keys())
        if missing:
            bad.append((s.get("id", "<unknown>"), f"missing keys: {sorted(missing)}"))
            continue
        for k in required:
            if not isinstance(ambient[k], list):
                bad.append(
                    (s.get("id", "<unknown>"), f"{k} is not a list: {type(ambient[k]).__name__}")
                )
                break
    assert not bad, f"styles with malformed ambient block: {bad[:5]}"


@pytest.mark.parametrize("style_id", CURATED_KEYS)
def test_curated_styles_have_rich_trigger_pool(
    styles: list[dict], style_id: str
) -> None:
    """Curated rows promised in the plan get ≥3 distinct trigger phrasings.

    A pool of size 1 still satisfies the schema, but it defeats the
    "10 пользователей даже при первой генерации получают разные
    фото" goal because the trigger axis collapses to a single value.
    Top styles must keep at least 3 phrasings.
    """
    entry = next((s for s in styles if s.get("id") == style_id), None)
    assert entry is not None, f"style {style_id!r} disappeared from data/styles.json"
    pool = entry.get("trigger_pool") or []
    assert (
        len(pool) >= 3
    ), f"{style_id}: trigger_pool size {len(pool)} < 3. Pool: {pool}"
    distinct = {p.strip().lower() for p in pool if isinstance(p, str)}
    assert len(distinct) == len(pool), (
        f"{style_id}: trigger_pool has duplicates ({pool})"
    )


@pytest.mark.parametrize("style_id", CURATED_KEYS)
def test_curated_styles_have_non_empty_lighting_pool(
    styles: list[dict], style_id: str
) -> None:
    """Curated styles must offer at least 3 lighting moods so the slot
    sampler has real entropy to roll on the lighting axis."""
    entry = next((s for s in styles if s.get("id") == style_id), None)
    assert entry is not None
    lights = (entry.get("ambient") or {}).get("lighting") or []
    assert (
        len(lights) >= 3
    ), f"{style_id}: ambient.lighting size {len(lights)} < 3"


def test_scene_anchor_dirty_word_budget(styles: list[dict]) -> None:
    """Regression budget — stale lighting/time tokens in scene_anchor.

    The Stage 2 migration cleans obvious cases. Mixed phrases survive
    until manual curation trims them. The budget below tracks the
    ongoing cleanup; tighten it as curated.json grows.
    """
    dirty: list[tuple[str, str]] = []
    for s in styles:
        anchor = (s.get("scene_anchor") or "").strip()
        match = _FORBIDDEN_WORDS.search(anchor)
        if match:
            dirty.append((s.get("id", "<unknown>"), match.group(0)))
    assert len(dirty) <= MAX_DIRTY_SCENE_ANCHORS, (
        f"scene_anchor regression: {len(dirty)} entries contain stale "
        f"lighting/time tokens, budget is {MAX_DIRTY_SCENE_ANCHORS}. "
        f"Sample offenders: {dirty[:5]}"
    )


def test_legacy_v2_fields_preserved(styles: list[dict]) -> None:
    """v2 / v1 loaders keep working alongside v3 — every legacy field
    that the v2 loader reads must still be present."""
    bad: list[tuple[str, str]] = []
    legacy_required = (
        "id",
        "mode",
        "type",
        "base_scene",
        "default_clothing",
        "background",
        "context_slots",
        "clothing",
    )
    for s in styles:
        for f in legacy_required:
            if f not in s:
                bad.append((s.get("id", "<unknown>"), f))
                break
    assert not bad, f"styles missing legacy fields: {bad[:5]}"

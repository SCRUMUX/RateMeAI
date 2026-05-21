"""Pin-test: ``ambient.time_of_day`` × ``ambient.lighting`` must not overlap.

The May 2026 prompt-pipeline audit found that several outdoor styles
listed ``"golden hour"`` and ``"blue hour"`` simultaneously in
``ambient.time_of_day`` *and* ``ambient.lighting``. The slot sampler
treats those channels as independent, so a single style draw could
emit both at once and the assembler would concatenate the same
concept twice into the wire prompt. The
``scripts/migrations/2026_05_tod_lighting_dedup/migrate.py``
migration stripped the lighting tokens from ``time_of_day`` across
the whole catalogue; this test pins that the two pools never share
a token going forward (case-insensitive whole-string compare —
catches both the original ``"golden hour"`` / ``"blue hour"`` case
and any future lighting-vs-time-of-day duplication).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"


def _styles() -> list[dict]:
    return json.loads(STYLES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", _styles(), ids=lambda e: e.get("id", "?"))
def test_tod_lighting_pools_disjoint(entry: dict) -> None:
    ambient = entry.get("ambient")
    if not isinstance(ambient, dict):
        pytest.skip("style has no ambient block")

    tod = {
        v.strip().lower()
        for v in (ambient.get("time_of_day") or [])
        if isinstance(v, str) and v.strip()
    }
    lighting = {
        v.strip().lower()
        for v in (ambient.get("lighting") or [])
        if isinstance(v, str) and v.strip()
    }
    overlap = tod & lighting
    assert not overlap, (
        f"style {entry.get('id')!r}: ambient.time_of_day and "
        f"ambient.lighting share tokens {sorted(overlap)} — see "
        "scripts/migrations/2026_05_tod_lighting_dedup/migrate.py"
    )


@pytest.mark.parametrize("entry", _styles(), ids=lambda e: e.get("id", "?"))
def test_no_lighting_tokens_in_time_of_day(entry: dict) -> None:
    ambient = entry.get("ambient")
    if not isinstance(ambient, dict):
        pytest.skip("style has no ambient block")

    tod_lc = {
        v.strip().lower()
        for v in (ambient.get("time_of_day") or [])
        if isinstance(v, str)
    }
    leaks = {"golden hour", "blue hour"} & tod_lc
    assert not leaks, (
        f"style {entry.get('id')!r}: lighting-quality tokens {sorted(leaks)} "
        "leaked into ambient.time_of_day"
    )

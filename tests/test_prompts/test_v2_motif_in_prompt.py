"""Regression test: the main semantic motif of every v2 style must
appear in the rendered prompt for default (no-hints) generation.

Background. Until v1.27.2 the v2 catalog migration filed
location-shaped strings such as "Times Square crosswalk with
illuminated billboards" under ``context_slots.lighting``. The
``composition_builder._resolve_lighting`` helper returns ``""`` when
``input_hints.lighting`` is empty, so users who did not open
«Другой вариант» got prompts that lacked the headline motif of their
chosen style — Eiffel without the Eiffel Tower, Times Square without
neon, etc. The Phase 2 migration relocated those entries to
``background.overrides_allowed`` and surfaced the motif in
``background.base`` for the styles where the motif had always lived
there. This test guards against any future migration silently
re-introducing the bug.

Stage 0 (prompt-pipeline-overhaul, 2026-04) extends the suite to also
cover the ten **Category D** styles flagged by
``scripts/migrations/2026_04_prompt_quality/audit_report.md`` — styles
whose ``background.base`` lacks the motif keyword. The composition
builder now safely falls back to ``spec.trigger`` for those, so this
test asserts on the rendered prompt regardless of the underlying data
shape. When the Stage 2 rewrite of ``data/styles.json`` lands and
``trigger_pool`` becomes the canonical source, the assertions stay
green.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import STYLE_REGISTRY
from src.services.style_loader import load_styles_from_json
from src.services.style_loader_v2 import register_v2_styles_from_json


@pytest.fixture
def _v2_registered(monkeypatch):
    """Register every v2-shape style from ``data/styles.json`` for the
    duration of a test, then restore the registry snapshot.

    The runtime app does the same registration during startup. We
    re-create that state here without booting the FastAPI app, then
    revert so the rest of the suite is not contaminated by extra v2
    entries.
    """
    monkeypatch.setattr(settings, "style_schema_v2_enabled", True, raising=False)
    monkeypatch.setattr(
        settings, "unified_prompt_v2_enabled", True, raising=False
    )
    snapshot = dict(STYLE_REGISTRY._v2_by_key)
    STYLE_REGISTRY._v2_by_key.clear()

    raw = load_styles_from_json()
    register_v2_styles_from_json(raw)
    yield

    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v2_by_key.update(snapshot)


# (style, mode, motif tokens — at least one must appear, case-insensitive)
_MOTIF_TRIO = [
    ("nyc_times_square", AnalysisMode.DATING, ("times square",)),
    ("venice_san_marco", AnalysisMode.DATING, ("venetian", "san marco")),
    ("paris_eiffel", AnalysisMode.DATING, ("eiffel",)),
]

# Category D from audit_report.md — styles whose background.base lacks
# the motif keyword. With the Stage 0 trigger fallback, the rendered
# prompt should still mention the motif because ``spec.trigger`` is
# appended to the scene if the base doesn't contain it.
_MOTIF_CATEGORY_D = [
    ("travel_luxury", AnalysisMode.DATING, ("travel",)),
    ("coffee_date", AnalysisMode.DATING, ("coffee", "café", "cafe")),
    ("digital_nomad", AnalysisMode.CV, ("digital",)),
    ("mirror_aesthetic", AnalysisMode.SOCIAL, ("mirror",)),
    ("instagram_aesthetic", AnalysisMode.SOCIAL, ("instagram",)),
    ("youtube_creator", AnalysisMode.SOCIAL, ("youtube",)),
    ("linkedin_premium", AnalysisMode.SOCIAL, ("linkedin",)),
    ("luxury", AnalysisMode.SOCIAL, ("luxury",)),
    ("casual", AnalysisMode.SOCIAL, ("casual",)),
    ("artistic", AnalysisMode.SOCIAL, ("artistic", "art ")),
]


@pytest.mark.parametrize("style,mode,motifs", _MOTIF_TRIO + _MOTIF_CATEGORY_D)
def test_default_prompt_contains_motif_keyword(
    _v2_registered, style: str, mode: AnalysisMode, motifs: tuple[str, ...]
):
    engine = PromptEngine()
    prompt = engine.build_image_prompt_v2(
        mode=mode,
        style=style,
        gender="male",
        input_hints={},
        target_model="gpt_image_2",
    )

    assert prompt, f"v2 builder returned empty prompt for {style!r}"
    haystack = prompt.lower()
    assert any(m.lower() in haystack for m in motifs), (
        f"None of motifs {motifs!r} found in default prompt for {style!r}. "
        f"Either the motif fell out of background.base or "
        f"context_slots.lighting was repopulated by a regressing migration. "
        f"Prompt was: {prompt!r}"
    )

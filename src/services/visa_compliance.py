"""Visa compliance helpers.

The Scenario Engine declares per-visa requirements in
``data/scenarios.json`` (`prompt_overrides.analysis_checklist` for the
RU master copy and ``analysis_checklist_en`` for the English mirror).
This module exposes them to the API layer so ``/api/v1/pre-analyze`` can
return a structured checklist for the SPA to render.

We intentionally **do not** add an ML compliance pass here today. The
checklist is currently a static reminder — the actual photo verdict
still relies on the existing pre-analyze LLM judgement. The scaffolding
below lets future work (Phase 5+) bolt on per-bullet pass/fail without
changing call sites.

Localisation (1.59.2)
---------------------

The scenarios JSON is shared across deployments. We pick the right
language at read time via ``MARKET_ID`` (``ru`` → Russian master copy,
anything else → ``analysis_checklist_en`` with a Russian fallback if
the EN translation is still missing).
"""

from __future__ import annotations

from typing import Any, Literal

from src.config import settings
from src.scenarios import Scenario, get_scenario
from src.services.input_quality import InputQualityReport


def is_visa_scenario(scenario: Scenario | None) -> bool:
    return scenario is not None and scenario.kind == "visa"


def is_approval_probability_scenario(scenario: Scenario | None) -> bool:
    """True for scenarios that render approval probability instead of score."""
    if scenario is None:
        return False
    if scenario.analysis_display is not None:
        return scenario.analysis_display.mode == "approval_probability"
    return scenario.kind == "visa" or scenario.slug == "document-photo"


def estimate_approval_probability(
    quality: InputQualityReport,
    scenario: Scenario | None,
) -> float:
    """Detrministic baseline approval probability on a 0..100 scale.

    Pure heuristic over the existing ``InputQualityReport`` — no new
    ML calls. Designed to land in the 40-92 band so the user always
    sees room for improvement before regenerating, then jumps to the
    scenario's ``success_probability_after_pct`` (typically 98.9).
    """

    score = 50.0
    if quality.face_area_ratio >= 0.20:
        score += 22.0
    elif quality.face_area_ratio >= 0.15:
        score += 16.0
    elif quality.face_area_ratio >= 0.10:
        score += 8.0
    else:
        score -= 4.0

    if quality.blur_face is not None and quality.blur_face >= 80.0:
        score += 6.0
    elif 0 <= (quality.blur_face or -1) < 40.0:
        score -= 8.0

    if quality.num_faces == 1:
        score += 4.0
    elif quality.num_faces > 1:
        score -= 12.0

    soft_count = len(quality.soft_warnings)
    score -= soft_count * 7.0

    if is_visa_scenario(scenario):
        # Visa scoring is stricter — the user knows the photo will need
        # a regeneration, so we keep the headline below "passing".
        score -= 4.0

    if score < 40.0:
        score = 40.0
    if score > 92.0:
        score = 92.0
    return round(score, 1)


def _resolve_lang(market_id: str | None = None) -> Literal["ru", "en"]:
    """Pick RU/EN based on the resolved market id (``ru`` → RU, anything else → EN)."""
    market = (market_id or settings.resolved_market_id or "global").lower()
    if market == "ru":
        return "ru"
    return "en"


def compliance_checklist(
    scenario_slug: str | None,
    market_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return ``[{rule, status}]`` pairs for the given visa scenario.

    ``status`` is always ``"pending"`` until an automated check fills
    it in. The shape stays stable so the SPA can render the list as
    soon as the user reaches ``StepAnalysis`` and update individual
    rows when the worker reports back.

    The bullets are picked per ``market_id``: RU edge gets the master
    Russian copy, anything else gets ``analysis_checklist_en`` with a
    Russian fallback if the translation hasn't shipped yet.
    """

    scenario = get_scenario(scenario_slug or "")
    if not is_visa_scenario(scenario) or scenario is None:
        return []
    overrides = scenario.prompt_overrides
    if overrides is None or not overrides.analysis_checklist:
        return []
    lang = _resolve_lang(market_id)
    if lang == "en" and overrides.analysis_checklist_en:
        bullets = overrides.analysis_checklist_en
    else:
        bullets = overrides.analysis_checklist
    return [{"rule": rule, "status": "pending"} for rule in bullets]


def output_spec_payload(scenario_slug: str | None) -> dict[str, Any] | None:
    """Surface the visa output spec (size mm, dpi, background) as JSON.

    Returned to the SPA so it can render the "Schengen 35×45 mm,
    white background" line on the landing/result screens without
    re-parsing the scenarios.json file.
    """

    scenario = get_scenario(scenario_slug or "")
    if scenario is None or scenario.output_spec is None:
        return None
    spec = scenario.output_spec
    return {
        "size_mm": list(spec.size_mm) if spec.size_mm else None,
        "dpi": spec.dpi,
        "background_color": spec.background_color,
        "head_height_mm": (
            list(spec.head_height_mm) if spec.head_height_mm else None
        ),
        "aspect_key": spec.aspect_key,
    }

"""Loader for ``data/scenarios.json``.

Same lifecycle as :mod:`src.services.landing_store`:
- JSON file on disk is the source of truth (one per server).
- Read path is cached in-memory; ``invalidate_cache()`` after admin saves.
- A missing file is fine — the registry just returns an empty list.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from src.models.enums import AnalysisMode
from src.scenarios.models import (
    AnalysisDisplay,
    OutputSpec,
    PaywallConfig,
    PromptOverrides,
    Scenario,
    VisaRequirements,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_PATH = REPO_ROOT / "data" / "scenarios.json"

_LOCK = threading.Lock()
_CACHE: dict[str, Scenario] | None = None

logger = logging.getLogger(__name__)


def invalidate_cache() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = None


def _coerce_tuple_2(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    return None


def _parse_output_spec(raw: Any) -> OutputSpec | None:
    if not isinstance(raw, dict):
        return None
    return OutputSpec(
        size_mm=_coerce_tuple_2(raw.get("size_mm")),
        dpi=int(raw.get("dpi") or 300),
        background_color=str(raw.get("background_color") or "#FFFFFF"),
        head_height_mm=_coerce_tuple_2(raw.get("head_height_mm")),
        aspect_key=(raw.get("aspect_key") or None),
    )


def _parse_requirements(raw: Any) -> VisaRequirements | None:
    if not isinstance(raw, dict):
        return None
    return VisaRequirements(
        expression=raw.get("expression") or "neutral",
        glasses=raw.get("glasses") or "forbidden",
        head_covering=raw.get("head_covering") or "forbidden_except_religious",
        background=str(raw.get("background") or "uniform_white"),
        shadows=raw.get("shadows") or "forbidden",
        compliance_source=str(raw.get("compliance_source") or ""),
    )


def _parse_checklist(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw if isinstance(item, str))


def _parse_overrides(raw: Any) -> PromptOverrides | None:
    if not isinstance(raw, dict):
        return None
    checklist = _parse_checklist(raw.get("analysis_checklist"))
    checklist_en = _parse_checklist(raw.get("analysis_checklist_en"))
    return PromptOverrides(
        analysis_checklist=checklist,
        analysis_checklist_en=checklist_en,
        image_instructions=str(raw.get("image_instructions") or ""),
    )


def _parse_paywall(raw: Any) -> PaywallConfig | None:
    if not isinstance(raw, dict):
        return None
    return PaywallConfig(
        pack_qty=int(raw.get("pack_qty") or 1),
        show_paywall=bool(raw.get("show_paywall", True)),
    )


def _parse_analysis_display(raw: Any) -> AnalysisDisplay | None:
    if not isinstance(raw, dict):
        return None
    mode = raw.get("mode") or "score"
    if mode not in ("score", "approval_probability"):
        mode = "score"
    pct_raw = raw.get("success_probability_after_pct")
    pct: float | None
    if pct_raw is None:
        pct = None
    else:
        try:
            pct = float(pct_raw)
        except (TypeError, ValueError):
            pct = None
    label_key = raw.get("label_key")
    label_key = str(label_key) if isinstance(label_key, str) and label_key else None
    return AnalysisDisplay(
        mode=mode,
        success_probability_after_pct=pct,
        label_key=label_key,
    )


def _parse_scenario(slug: str, raw: dict[str, Any]) -> Scenario | None:
    try:
        api_mode_raw = raw.get("api_mode") or "cv"
        api_mode = AnalysisMode(api_mode_raw)
    except ValueError:
        logger.warning(
            "scenario %s declares unknown api_mode=%s — skipping",
            slug,
            raw.get("api_mode"),
        )
        return None
    kind = raw.get("kind") or "core"
    if kind not in ("core", "document", "visa"):
        logger.warning("scenario %s declares unknown kind=%s — skipping", slug, kind)
        return None
    profile = raw.get("pipeline_profile") or "simple"
    if profile not in ("simple", "advanced"):
        profile = "simple"
    step3_mode = raw.get("step3_mode") or "styles"
    if step3_mode not in ("styles", "document_formats"):
        step3_mode = "styles"

    extra = raw.get("extra")
    return Scenario(
        slug=slug,
        kind=kind,
        api_mode=api_mode,
        pipeline_profile=profile,
        step3_mode=step3_mode,
        output_spec=_parse_output_spec(raw.get("output_spec")),
        requirements=_parse_requirements(raw.get("requirements")),
        prompt_overrides=_parse_overrides(raw.get("prompt_overrides")),
        paywall=_parse_paywall(raw.get("paywall")),
        analysis_display=_parse_analysis_display(raw.get("analysis_display")),
        landing_slug=(raw.get("landing_slug") or None),
        enabled=bool(raw.get("enabled", False)),
        extra=dict(extra) if isinstance(extra, dict) else {},
    )


def load_scenarios() -> dict[str, Scenario]:
    """Return ``{slug: Scenario}`` from ``data/scenarios.json``.

    Caches the parsed registry in-memory across calls; call
    :func:`invalidate_cache` after admin edits.
    """

    global _CACHE
    if _CACHE is not None:
        return _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        if not SCENARIOS_PATH.exists():
            _CACHE = {}
            return _CACHE
        raw_text = SCENARIOS_PATH.read_text(encoding="utf-8")
        if not raw_text.strip():
            _CACHE = {}
            return _CACHE
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.exception("failed to parse %s", SCENARIOS_PATH)
            _CACHE = {}
            return _CACHE
        scenarios_raw = data.get("scenarios") if isinstance(data, dict) else None
        if not isinstance(scenarios_raw, dict):
            _CACHE = {}
            return _CACHE
        out: dict[str, Scenario] = {}
        for slug, raw in scenarios_raw.items():
            if not isinstance(slug, str) or not isinstance(raw, dict):
                continue
            parsed = _parse_scenario(slug, raw)
            if parsed is not None:
                out[slug] = parsed
        _CACHE = out
        return _CACHE


def load_scenarios_fresh() -> dict[str, Scenario]:
    invalidate_cache()
    return load_scenarios()

"""Public scenarios API.

Powers the SPA's progressive migration from the static
``web/src/scenarios/config.ts`` list to a server-driven registry.
Returns only ``enabled`` scenarios so a deployed-but-dark visa scenario
stays invisible until its JSON entry flips.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from src.scenarios import get_scenario, list_enabled_scenarios
from src.services.visa_compliance import (
    compliance_checklist,
    output_spec_payload,
)

router = APIRouter()

_SCENARIO_CACHE_CONTROL = "public, s-maxage=60, stale-while-revalidate=600"


@router.get("")
@router.get("/")
async def list_public_scenarios(response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = _SCENARIO_CACHE_CONTROL
    items = [s.to_public_dict() for s in list_enabled_scenarios()]
    return {"scenarios": items, "count": len(items)}


@router.get("/{slug}")
async def get_public_scenario(slug: str, response: Response) -> dict[str, Any]:
    scenario = get_scenario(slug)
    if scenario is None or not scenario.enabled:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {slug}")
    response.headers["Cache-Control"] = _SCENARIO_CACHE_CONTROL
    return {"scenario": scenario.to_public_dict()}


@router.get("/{slug}/compliance")
async def get_scenario_compliance(slug: str, response: Response) -> dict[str, Any]:
    """Return the public-safe compliance checklist + output spec for a
    visa/document scenario.

    The checklist is non-sensitive (it's already on the official
    consulate page); the SPA renders it on ``StepAnalysis`` so the
    user understands what the system will check. ``output_spec``
    feeds the photo size hint.
    """

    scenario = get_scenario(slug)
    if scenario is None or not scenario.enabled:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {slug}")
    response.headers["Cache-Control"] = _SCENARIO_CACHE_CONTROL
    return {
        "slug": slug,
        "kind": scenario.kind,
        "checklist": compliance_checklist(slug),
        "output_spec": output_spec_payload(slug),
    }

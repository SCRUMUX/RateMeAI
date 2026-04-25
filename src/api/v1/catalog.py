"""Style catalog API — serves catalog data to web / mini-app clients.

The ``?schema=v2`` query parameter opts-in to the slot-based view of a
style (see :mod:`src.prompts.style_schema_v2`). Without the parameter
the endpoints keep returning the legacy payload so existing clients
stay untouched — this is the contract for PR4 of the
style-schema-v2 migration.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from src.services.style_catalog import (
    get_available_modes,
    get_catalog_json,
    get_catalog_json_v2,
    get_scenario_styles_json,
    get_scenario_styles_json_v2,
    get_style_options,
    get_style_options_v2,
)

router = APIRouter()


SchemaParam = Literal["v1", "v2"]


@router.get("/modes")
async def list_modes():
    """Return available analysis modes."""
    return {"modes": get_available_modes()}


@router.get("/styles")
async def list_styles(
    mode: str = Query(..., description="Analysis mode: dating, cv, social"),
    schema: SchemaParam = Query(
        "v1",
        description=(
            "Catalog payload schema. ``v1`` (default) keeps the legacy "
            "shape; ``v2`` adds a per-entry ``schema_version`` field so "
            "clients know which styles expose slot-based options."
        ),
    ),
):
    """Return all styles for the given mode."""
    if schema == "v2":
        items = get_catalog_json_v2(mode)
    else:
        items = get_catalog_json(mode)
    if not items:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {mode}")
    return {"mode": mode, "count": len(items), "styles": items, "schema": schema}


@router.get("/scenario-styles")
async def list_scenario_styles(
    scenario: str = Query(
        ...,
        description=(
            "Scenario slug. Returns styles whose ``scenario`` field "
            "matches this value (e.g. ``document-photo`` or "
            "``tinder-pack``). These styles are intentionally hidden "
            "from the main ``/styles?mode=...`` catalog."
        ),
    ),
    schema: SchemaParam = Query(
        "v1",
        description=(
            "Catalog payload schema. ``v2`` adds a per-entry "
            "``schema_version`` field, otherwise identical to v1."
        ),
    ),
):
    """Return styles bound to a specific scenario page."""
    if schema == "v2":
        items = get_scenario_styles_json_v2(scenario)
    else:
        items = get_scenario_styles_json(scenario)
    if not items:
        raise HTTPException(
            status_code=404, detail=f"Unknown scenario: {scenario}"
        )
    return {
        "scenario": scenario,
        "count": len(items),
        "styles": items,
        "schema": schema,
    }


@router.get("/styles/{style_id}/options")
async def get_options(
    style_id: str,
    schema: SchemaParam = Query(
        "v1",
        description=(
            "Options payload schema. ``v1`` returns the legacy "
            "``allowed_variations`` dict. ``v2`` returns the slot-based "
            "structure (context_slots / weather / clothing / background). "
            "When the style has not been migrated yet and ``v2`` is "
            "requested, the endpoint falls back to the v1 payload with "
            "``schema_version: 1``."
        ),
    ),
):
    """Return allowed variations (or v2 slots) for a specific style."""
    if schema == "v2":
        v2_payload = get_style_options_v2(style_id)
        if v2_payload is not None:
            return {
                "style_id": style_id,
                "schema_version": 2,
                "options": v2_payload,
            }
        legacy = get_style_options(style_id)
        if legacy is None:
            raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")
        return {
            "style_id": style_id,
            "schema_version": 1,
            "options": legacy,
        }

    options = get_style_options(style_id)
    if options is None:
        raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")
    return {"style_id": style_id, "options": options}

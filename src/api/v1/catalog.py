"""Style catalog API — serves catalog data to web / mini-app clients."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from src.services.style_catalog import (
    get_catalog_json,
    get_available_modes,
    get_style_options,
)

router = APIRouter()


@router.get("/modes")
async def list_modes():
    """Return available analysis modes."""
    return {"modes": get_available_modes()}


@router.get("/styles")
async def list_styles(
    mode: str = Query(..., description="Analysis mode: dating, cv, social"),
):
    """Return all styles for the given mode."""
    items = get_catalog_json(mode)
    if not items:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {mode}")
    return {"mode": mode, "count": len(items), "styles": items}


@router.get("/styles/{style_id}/options")
async def get_options(style_id: str):
    """Return allowed variations and options for a specific style."""
    options = get_style_options(style_id)
    if options is None:
        raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")
    return {"style_id": style_id, "options": options}

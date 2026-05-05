from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.v1.admin.auth import require_admin
from src.models.db import User
from src.services import landing_store

router = APIRouter()


class AdminLandingPagePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    # We keep it permissive so blocks can evolve without schema churn.
    page: dict[str, Any] = Field(default_factory=dict)


@router.get("/landing/pages")
async def list_pages(_admin: User = Depends(require_admin)) -> dict[str, Any]:
    data = landing_store.load_landing_content_fresh()
    pages = data.get("pages") or {}
    if not isinstance(pages, dict):
        pages = {}
    return {"slugs": sorted(pages.keys())}


@router.get("/landing/pages/{slug}")
async def get_page(slug: str, _admin: User = Depends(require_admin)) -> dict[str, Any]:
    data = landing_store.load_landing_content_fresh()
    pages = data.get("pages") or {}
    if not isinstance(pages, dict):
        raise HTTPException(status_code=500, detail="Landing content is misconfigured")
    page = pages.get(slug)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Unknown landing page: {slug}")
    if not isinstance(page, dict):
        raise HTTPException(status_code=500, detail="Landing page payload is invalid")
    return {"slug": slug, "page": page}


@router.put("/landing/pages/{slug}")
async def put_page(
    slug: str,
    payload: AdminLandingPagePayload,
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    data = landing_store.load_landing_content_fresh()
    pages = data.get("pages")
    if pages is None or not isinstance(pages, dict):
        pages = {}
    pages[slug] = payload.page
    data["pages"] = pages
    landing_store.save_landing_content(data)
    return {"status": "ok", "slug": slug}


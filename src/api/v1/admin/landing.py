from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from src.api.v1.admin.auth import require_admin
from src.config import settings
from src.models.db import User
from src.services import cms_replication, landing_store

router = APIRouter()


class AdminLandingPagePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    # We keep it permissive so blocks can evolve without schema churn.
    page: dict[str, Any] = Field(default_factory=dict)


def _require_editor() -> None:
    """Variant B guard: every write endpoint must run on the CMS editor.

    On followers (RU edge) the on-disk JSON is rebuilt from the editor's
    push payloads, so accepting a local write would silently diverge
    until the next safety-pull. Rather than corrupting state we 403.
    """
    if not settings.is_cms_editor:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "cms_write_disabled",
                "message": "CMS write disabled on follower deployment.",
                "cms_role": settings.resolved_cms_role,
            },
        )


def _resolve_market(market: str | None) -> str:
    """Pick a market for an admin call, defaulting to the editor's home."""
    if market is None or not market.strip():
        # Editor admin defaults to the global file when no market is
        # passed. This matches the new admin UI: the market switcher
        # is part of the page; legacy clients that omit the param
        # implicitly mean "global".
        return landing_store.DEFAULT_MARKET
    value = market.strip().lower()
    if value not in landing_store.available_markets():
        raise HTTPException(
            status_code=400,
            detail=f"Unknown market '{value}'. Expected one of {landing_store.available_markets()}",
        )
    return value


@router.get("/landing/markets")
async def list_markets(_admin: User = Depends(require_admin)) -> dict[str, Any]:
    """Markets the admin UI can edit. Driven by ``landing_store.available_markets()``."""
    return {
        "markets": list(landing_store.available_markets()),
        "default": landing_store.DEFAULT_MARKET,
        "cms_role": settings.resolved_cms_role,
    }


@router.get("/landing/pages")
async def list_pages(
    market: str | None = Query(default=None),
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    resolved = _resolve_market(market)
    data = landing_store.load_landing_content_fresh(resolved)
    pages = data.get("pages") or {}
    if not isinstance(pages, dict):
        pages = {}
    return {"market": resolved, "slugs": sorted(pages.keys())}


@router.get("/landing/pages/{slug}")
async def get_page(
    slug: str,
    market: str | None = Query(default=None),
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    resolved = _resolve_market(market)
    data = landing_store.load_landing_content_fresh(resolved)
    pages = data.get("pages") or {}
    if not isinstance(pages, dict):
        raise HTTPException(status_code=500, detail="Landing content is misconfigured")
    page = pages.get(slug)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Unknown landing page: {slug}")
    if not isinstance(page, dict):
        raise HTTPException(status_code=500, detail="Landing page payload is invalid")
    return {"market": resolved, "slug": slug, "page": page}


@router.put("/landing/pages/{slug}")
async def put_page(
    slug: str,
    payload: AdminLandingPagePayload,
    market: str | None = Query(default=None),
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    _require_editor()
    resolved = _resolve_market(market)
    data = landing_store.load_landing_content_fresh(resolved)
    pages = data.get("pages")
    if pages is None or not isinstance(pages, dict):
        pages = {}
    pages[slug] = payload.page
    data["pages"] = pages
    landing_store.save_landing_content(data, market=resolved)
    cms_replication.schedule_replication(resolved, data)
    return {"status": "ok", "market": resolved, "slug": slug}

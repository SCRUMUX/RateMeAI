from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from src.services import landing_store

router = APIRouter()

# Public landings tolerate ~minute lag after CMS edits, so we lean on
# shared caches (Cloudflare/Vercel edge). `s-maxage=60` caches for 1 min on
# CDN, `stale-while-revalidate=600` lets stale responses serve up to 10 min
# while we revalidate in the background. Browser cache is intentionally
# left at the default ("public" alone) to avoid stale UX after admin edits.
_LANDING_CACHE_CONTROL = "public, s-maxage=60, stale-while-revalidate=600"


@router.get("/pages/{slug}")
async def get_landing_page(slug: str, response: Response) -> dict[str, Any]:
    data = landing_store.load_landing_content()
    pages = data.get("pages") or {}
    if not isinstance(pages, dict):
        raise HTTPException(status_code=500, detail="Landing content is misconfigured")
    page = pages.get(slug)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Unknown landing page: {slug}")
    if not isinstance(page, dict):
        raise HTTPException(status_code=500, detail="Landing page payload is invalid")
    response.headers["Cache-Control"] = _LANDING_CACHE_CONTROL
    return {"slug": slug, "page": page}

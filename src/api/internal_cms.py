"""Internal CMS replication endpoints (Variant B).

Exposed at the FastAPI app root (``/internal/cms/...``) rather than
under ``/api/v1`` so:

* CORS does NOT apply (browser clients never call these);
* nginx on the RU edge can guard the prefix with an IP allowlist that
  only permits Railway egress + ourselves;
* it stays out of the public OpenAPI schema by default.

Authentication: HMAC-SHA256 signature in the
``X-Replication-Signature`` header. The shared secret comes from
``settings.resolved_cms_replication_secret`` (which falls back to
``INTERNAL_API_KEY``).

* ``POST /internal/cms/replicate`` — follower-only. Receives a signed
  CMS document push and rewrites the local landing JSON.
* ``GET  /internal/cms/snapshot``  — editor-only. Returns the current
  CMS document for the requested market so followers can do an hourly
  safety-pull. The signature here is computed over the full request
  URL bytes (the GET has no body).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from src.config import settings
from src.services import cms_replication, landing_store

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_secret() -> str:
    secret = cms_replication._shared_secret()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="CMS replication secret is not configured",
        )
    return secret


@router.post("/internal/cms/replicate")
async def replicate(
    request: Request,
    x_replication_signature: str | None = Header(default=None, alias="X-Replication-Signature"),
) -> dict[str, Any]:
    """Follower entry point: write a signed CMS document to disk."""
    if not settings.is_cms_follower:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "cms_replicate_disabled",
                "message": "Replication receiver is enabled only on followers.",
                "cms_role": settings.resolved_cms_role,
            },
        )
    secret = _require_secret()

    raw_body = await request.body()
    signature = (x_replication_signature or "").strip()
    if not cms_replication.verify_signature(secret, raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid replication signature")

    try:
        envelope = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(envelope, dict):
        raise HTTPException(status_code=400, detail="Body must be an object")

    market = (envelope.get("market") or "").strip().lower()
    if market not in landing_store.available_markets():
        raise HTTPException(
            status_code=400,
            detail=f"Unknown market '{market}'",
        )
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")

    try:
        rewritten = cms_replication.apply_snapshot(market, payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info(
        "cms_replicate: applied market=%s rewritten=%s incoming_hash=%s",
        market,
        rewritten,
        envelope.get("content_hash"),
    )
    return {
        "status": "ok",
        "market": market,
        "rewritten": rewritten,
    }


@router.get("/internal/cms/snapshot")
async def snapshot(
    request: Request,
    market: str = Query(...),
    x_replication_signature: str | None = Header(default=None, alias="X-Replication-Signature"),
) -> dict[str, Any]:
    """Editor entry point: hand a CMS snapshot to a follower's safety-pull."""
    if not settings.is_cms_editor:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "cms_snapshot_disabled",
                "message": "Snapshot endpoint is enabled only on the CMS editor.",
                "cms_role": settings.resolved_cms_role,
            },
        )
    secret = _require_secret()

    market_value = market.strip().lower()
    if market_value not in landing_store.available_markets():
        raise HTTPException(status_code=400, detail=f"Unknown market '{market_value}'")

    # Sign the full request URL (path + query) — same convention used by
    # ``cms_replication.fetch_snapshot_from_master``.
    full_url = str(request.url)
    signature = (x_replication_signature or "").strip()
    if not cms_replication.verify_signature(secret, full_url.encode("utf-8"), signature):
        raise HTTPException(status_code=403, detail="Invalid replication signature")

    document = landing_store.load_landing_content_fresh(market_value)
    return cms_replication.build_payload(market_value, document)

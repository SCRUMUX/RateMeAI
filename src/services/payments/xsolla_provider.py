"""Xsolla Pay Station token creation (primary / USD)."""

from __future__ import annotations

import base64
import logging
import uuid
from decimal import Decimal

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

XSOLLA_TOKEN_URL = "https://api.xsolla.com/merchant/v2/merchants/{merchant_id}/token"
PAYSTATION_URL = "https://secure.xsolla.com/paystation4/?token={token}"
PAYSTATION_SANDBOX_URL = "https://sandbox-secure.xsolla.com/paystation4/?token={token}"


def _resolve_return_url(channel: str) -> str:
    explicit = (settings.xsolla_return_url or "").strip()
    if explicit:
        return explicit
    if channel == "web" and settings.web_base_url:
        return f"{settings.web_base_url.rstrip('/')}/payment-success"
    return f"{settings.api_base_url.rstrip('/')}/payment-success"


async def create_payment(
    user_id: str,
    pack_qty: int,
    *,
    return_channel: str = "telegram",
) -> tuple[str, str] | None:
    """Request Pay Station token. Returns (token, confirmation_url) or None."""
    from .credit_packs import pack_by_quantity

    pack = pack_by_quantity(pack_qty)
    if pack is None:
        logger.error("Unknown pack quantity: %s", pack_qty)
        return None

    merchant_id = (settings.xsolla_merchant_id or "").strip()
    api_key = (settings.xsolla_api_key or "").strip()
    try:
        project_id = int(str(settings.xsolla_project_id or "").strip() or "0")
    except ValueError:
        project_id = 0

    if not merchant_id or not api_key or project_id <= 0:
        logger.error("Xsolla credentials not configured")
        return None

    external_id = str(uuid.uuid4())
    amount = pack.price.quantize(Decimal("0.01"))
    return_url = _resolve_return_url(return_channel)
    sandbox = bool(settings.xsolla_sandbox_mode)

    # NOTE: ``settings.external_id`` is intentionally omitted — Xsolla
    # rejects it with HTTP 422 unless the "External ID" option is turned
    # on in the project cabinet. Our idempotency is on the transaction
    # id we receive in the webhook, so we keep ``external_id`` only in
    # ``custom_parameters`` for tracing.
    settings_block: dict = {
        "project_id": project_id,
        "currency": "USD",
        "language": "en",
        "return_url": return_url,
        "ui": {"theme": "default_dark"},
    }
    if sandbox:
        # Sandbox mode lets the cabinet skip "project not active" checks
        # and accepts test cards (4111 1111 1111 1111 etc.).
        settings_block["mode"] = "sandbox"

    body = {
        "user": {
            "id": {"value": user_id},
            "name": {"value": "User"},
        },
        "settings": settings_block,
        "purchase": {
            "checkout": {"amount": float(amount), "currency": "USD"},
            "description": {"value": f"RateMeAI: {pack.quantity} photo upgrades"},
        },
        "custom_parameters": {
            "user_id": user_id,
            "pack_qty": str(pack.quantity),
            "external_id": external_id,
        },
    }

    auth = base64.b64encode(f"{merchant_id}:{api_key}".encode()).decode()
    url = XSOLLA_TOKEN_URL.format(merchant_id=merchant_id)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Basic {auth}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code >= 400:
            logger.error(
                "Xsolla token HTTP %s: %s",
                resp.status_code,
                resp.text[:500],
            )
            return None
        data = resp.json()
        token = data.get("token")
        if not token:
            logger.error("Xsolla token missing in response: %s", data)
            return None
        url_template = PAYSTATION_SANDBOX_URL if sandbox else PAYSTATION_URL
        confirmation = url_template.format(token=token)
        logger.info(
            "Xsolla payment token created user=%s pack=%s external_id=%s sandbox=%s",
            user_id,
            pack_qty,
            external_id,
            sandbox,
        )
        return str(token), confirmation
    except Exception:
        logger.exception("Failed to create Xsolla token for user=%s", user_id)
        return None


async def fetch_transactions_by_external_id(external_id: str) -> dict | None:
    """Optional server-side verification (unused by default webhook flow)."""
    merchant_id = (settings.xsolla_merchant_id or "").strip()
    api_key = (settings.xsolla_api_key or "").strip()
    if not merchant_id or not api_key or not external_id:
        return None
    auth = base64.b64encode(f"{merchant_id}:{api_key}".encode()).decode()
    url = (
        f"https://api.xsolla.com/merchant/v2/merchants/{merchant_id}/transactions"
        f"?external_id={external_id}"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Basic {auth}"})
        if resp.status_code >= 400:
            return None
        return resp.json()
    except Exception:
        logger.exception("Xsolla transaction lookup failed")
        return None

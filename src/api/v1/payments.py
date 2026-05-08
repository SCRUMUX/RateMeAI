"""Payment webhooks and checkout API (YooKassa on edge, Xsolla on primary)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid as _uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_auth_user, get_db, get_redis
from src.config import settings
from src.models.db import CreditTransaction, User, UserIdentity

logger = logging.getLogger(__name__)
router = APIRouter()


def _ensure_edge_only() -> None:
    """YooKassa webhooks must hit RU-edge only."""
    if not settings.is_edge:
        raise HTTPException(
            status_code=410,
            detail="payments_disabled_on_primary",
            headers={"X-Payments-Channel": "edge-only"},
        )


def _payment_provider_configured() -> bool:
    if settings.payment_provider == "yookassa":
        return bool(settings.yookassa_shop_id and settings.yookassa_secret_key)
    try:
        pid = int(str(settings.xsolla_project_id or "").strip() or "0")
    except ValueError:
        pid = 0
    return bool(
        (settings.xsolla_merchant_id or "").strip()
        and (settings.xsolla_api_key or "").strip()
        and pid > 0
    )


def _ensure_payment_provider_configured() -> None:
    if not _payment_provider_configured():
        raise HTTPException(
            status_code=503,
            detail="payment_provider_not_configured",
        )


_YOOKASSA_IP_RANGES = (
    "185.71.76.",
    "185.71.77.",
    "77.75.153.",
    "77.75.154.",
    "77.75.156.",
    "2a02:5180:0:",
)


def _is_trusted_ip(ip: str | None) -> bool:
    if not ip:
        return False
    return any(ip.startswith(prefix) for prefix in _YOOKASSA_IP_RANGES)


async def _verify_payment_server_side(payment_id: str) -> dict | None:
    """Verify payment status directly with YooKassa API."""
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        return None
    try:
        from src.services.payments import fetch_payment

        payment = await fetch_payment(payment_id)
        if payment and payment.status == "succeeded":
            meta = payment.metadata or {}
            return {
                "user_id": meta.get("user_id"),
                "pack_qty": meta.get("pack_qty"),
                "status": payment.status,
            }
        logger.warning(
            "Server-side verify: payment %s status=%s",
            payment_id,
            getattr(payment, "status", "?"),
        )
    except Exception:
        logger.exception("Failed to verify payment %s server-side", payment_id)
    return None


async def _grant_purchase_credits(
    db: AsyncSession,
    redis,
    *,
    payment_id: str,
    user_id_str: str,
    pack_qty: int,
) -> dict:
    """Idempotent credit grant used by YooKassa and Xsolla success paths."""
    existing = await db.execute(
        select(CreditTransaction).where(CreditTransaction.payment_id == payment_id)
    )
    if existing.scalar_one_or_none() is not None:
        logger.info("Duplicate webhook for payment=%s, skipping", payment_id)
        return {"status": "duplicate"}

    try:
        user = await db.get(User, _uuid.UUID(user_id_str))
    except (ValueError, TypeError):
        logger.error(
            "Invalid user_id=%r in payment %s metadata", user_id_str, payment_id
        )
        return {"status": "error", "detail": "invalid user_id in metadata"}
    if user is None:
        logger.error(
            "User not found for user_id=%s payment=%s", user_id_str, payment_id
        )
        raise HTTPException(status_code=404, detail="User not found")

    user.image_credits += pack_qty
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=pack_qty,
            balance_after=user.image_credits,
            tx_type="purchase",
            payment_id=payment_id,
        )
    )
    await db.commit()

    logger.info(
        "Credits added: user=%s +%d credits, new_balance=%d, payment=%s",
        user.id,
        pack_qty,
        user.image_credits,
        payment_id,
    )

    try:
        await redis.publish(
            f"ratemeai:payment_done:{user.id}",
            f"{pack_qty}:{user.image_credits}",
        )
    except Exception:
        logger.warning("Failed to publish payment notification for user=%s", user.id)

    await _notify_user_channels(user, pack_qty, user.image_credits, db)

    return {"status": "ok", "credits_added": pack_qty, "balance": user.image_credits}


@router.post("/yookassa/webhook")
async def yookassa_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    _ensure_edge_only()
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.client.host
    )
    body = await request.json()
    event = body.get("event", "")
    payment_obj = body.get("object", {})
    payment_id = payment_obj.get("id", "unknown")
    status = payment_obj.get("status", "")

    logger.info(
        "YooKassa webhook: event=%s payment=%s status=%s ip=%s",
        event,
        payment_id,
        status,
        client_ip,
    )

    if event != "payment.succeeded" or status != "succeeded":
        return {"status": "ignored", "event": event}

    if not _is_trusted_ip(client_ip):
        logger.warning(
            "Untrusted webhook IP %s for payment %s — verifying server-side",
            client_ip,
            payment_id,
        )
        verified = await _verify_payment_server_side(payment_id)
        if not verified:
            logger.error(
                "Payment %s verification failed from IP %s", payment_id, client_ip
            )
            raise HTTPException(status_code=403, detail="Untrusted source")
        user_id_str = verified["user_id"]
        pack_qty_str = verified["pack_qty"]
    else:
        metadata = payment_obj.get("metadata", {})
        user_id_str = metadata.get("user_id")
        pack_qty_str = metadata.get("pack_qty")

    if not user_id_str or not pack_qty_str:
        logger.warning("Webhook missing metadata: payment=%s", payment_id)
        return {"status": "error", "detail": "missing metadata"}

    try:
        pack_qty = int(pack_qty_str)
    except (ValueError, TypeError):
        logger.error(
            "Invalid pack_qty=%r in payment %s metadata", pack_qty_str, payment_id
        )
        return {"status": "error", "detail": "invalid pack_qty in metadata"}

    return await _grant_purchase_credits(
        db,
        redis,
        payment_id=str(payment_id),
        user_id_str=str(user_id_str),
        pack_qty=pack_qty,
    )


def _verify_xsolla_signature(body: bytes, authorization: str | None) -> bool:
    secret = settings.xsolla_project_secret()
    if not secret or not authorization:
        return False
    auth = authorization.strip()
    prefix = "signature "
    if auth.lower().startswith(prefix):
        sig = auth[len(prefix) :].strip().lower()
    else:
        return False
    expected = hashlib.sha1(body + secret.encode()).hexdigest().lower()
    return sig == expected


def _xsolla_nested_id(container: dict | None, key: str = "id") -> str | None:
    if not container:
        return None
    node = container.get(key)
    if isinstance(node, dict):
        v = node.get("value")
        return str(v) if v is not None else None
    if node is not None:
        return str(node)
    return None


@router.post("/xsolla/webhook")
async def xsolla_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    if settings.payment_provider != "xsolla":
        raise HTTPException(
            status_code=410,
            detail="xsolla_disabled_on_edge",
            headers={"X-Payments-Channel": "primary-only"},
        )
    if not settings.xsolla_project_secret():
        raise HTTPException(status_code=503, detail="xsolla_secret_not_configured")

    body_bytes = await request.body()
    if not _verify_xsolla_signature(body_bytes, request.headers.get("authorization")):
        logger.warning("Xsolla webhook signature mismatch")
        raise HTTPException(status_code=403, detail="invalid_signature")

    try:
        body = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="invalid_json") from None

    notification_type = body.get("notification_type") or body.get("type") or ""

    logger.info("Xsolla webhook: type=%s", notification_type)

    if notification_type == "user_validation":
        user_uuid = (
            (body.get("custom_parameters") or {}).get("user_id")
            or _xsolla_nested_id(body.get("user"))
        )
        if not user_uuid:
            return {"status": "ignored", "detail": "no_user_hint"}
        try:
            user = await db.get(User, _uuid.UUID(str(user_uuid)))
        except (ValueError, TypeError):
            return {"status": "invalid_user"}
        if user is None:
            return {"status": "invalid_user"}
        public_id = str(user.id)
        return {"user": {"public_id": public_id}}

    if notification_type in ("refund", "cancel", "partial_refund"):
        logger.info("Xsolla %s notification recorded (no balance action)", notification_type)
        return {"status": "ignored", "event": notification_type}

    if notification_type != "payment":
        return {"status": "ignored", "event": notification_type}

    tx = body.get("transaction") or {}
    payment_id = tx.get("id")
    if payment_id is None:
        logger.warning("Xsolla payment webhook missing transaction.id")
        return {"status": "error", "detail": "missing_transaction_id"}
    payment_id_str = str(payment_id)

    status = (tx.get("status") or "").lower()
    if status != "done":
        return {"status": "ignored", "payment_status": status}

    custom = body.get("custom_parameters") or {}
    user_id_str = custom.get("user_id")
    pack_qty_str = custom.get("pack_qty")

    if not user_id_str or not pack_qty_str:
        logger.warning("Xsolla webhook missing custom_parameters: payment=%s", payment_id_str)
        return {"status": "error", "detail": "missing_custom_parameters"}

    try:
        pack_qty = int(pack_qty_str)
    except (ValueError, TypeError):
        logger.error("Invalid pack_qty=%r in Xsolla payment %s", pack_qty_str, payment_id_str)
        return {"status": "error", "detail": "invalid pack_qty"}

    return await _grant_purchase_credits(
        db,
        redis,
        payment_id=payment_id_str,
        user_id_str=str(user_id_str),
        pack_qty=pack_qty,
    )


@router.get("/packs")
async def list_credit_packs():
    """Public catalog for the active provider on this deployment."""
    from src.services.payments import get_credit_packs

    currency = "RUB" if settings.payment_provider == "yookassa" else "USD"
    packs = get_credit_packs()
    return {
        "provider": settings.payment_provider,
        "currency": currency,
        "packs": [
            {
                "quantity": p.quantity,
                "price": format(p.price, "f"),
                "label": p.label,
            }
            for p in packs
        ],
    }


@router.post("/create")
async def create_payment_link(
    request: Request,
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a checkout session (YooKassa or Xsolla) and return confirmation URL."""
    _ensure_payment_provider_configured()

    result = await db.execute(
        select(UserIdentity).where(
            UserIdentity.user_id == user.id,
            UserIdentity.provider != "web",
        )
    )
    if result.first() is None:
        raise HTTPException(
            status_code=403,
            detail="Registration required before payment",
        )

    body = await request.json()
    pack_qty = body.get("pack_qty")
    if not pack_qty or not isinstance(pack_qty, int):
        raise HTTPException(status_code=400, detail="pack_qty is required (integer)")

    from src.services.payments import create_payment as _create

    created = await _create(str(user.id), pack_qty, return_channel="web")
    if not created:
        raise HTTPException(status_code=500, detail="Payment creation failed")
    payment_id, confirmation_url = created
    return {"payment_id": payment_id, "confirmation_url": confirmation_url}


@router.get("/balance")
async def get_balance(
    user: User = Depends(get_auth_user),
):
    """Get user's credit balance. Accepts Bearer or X-API-Key."""
    return {"user_id": str(user.id), "image_credits": user.image_credits}


async def _notify_user_channels(
    user: User,
    pack_qty: int,
    new_balance: int,
    db: AsyncSession,
) -> None:
    """Send payment confirmation to all linked channels that support push."""
    result = await db.execute(
        select(UserIdentity).where(UserIdentity.user_id == user.id)
    )
    identities = result.scalars().all()

    tg_ids: set[str] = set()
    for ident in identities:
        if ident.provider == "telegram":
            tg_ids.add(ident.external_id)
    if user.telegram_id and str(user.telegram_id) not in tg_ids:
        tg_ids.add(str(user.telegram_id))

    for tg_id in tg_ids:
        await _notify_telegram(int(tg_id), pack_qty, new_balance)


async def _notify_telegram(telegram_id: int, pack_qty: int, new_balance: int) -> None:
    """Send a direct Telegram message to user about successful payment."""
    token = settings.telegram_bot_token
    if not token:
        return
    text = (
        f"✅ Оплата прошла успешно!\n\n"
        f"Начислено: *{pack_qty} образов*\n"
        f"Баланс: *{new_balance} образов*\n\n"
        f"Отправь фото для примерки образа!"
    )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={
                    "chat_id": telegram_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "Telegram notify failed: %s %s", resp.status_code, resp.text[:200]
                )
    except Exception:
        logger.exception(
            "Failed to send Telegram payment notification to %s", telegram_id
        )

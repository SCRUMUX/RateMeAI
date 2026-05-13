"""Telegram Stars (XTR) checkout handlers.

Three update types are involved:

1. ``topup_stars`` callback → send the pack picker keyboard.
2. ``buy_xtr:{qty}`` callback → call ``Bot.send_invoice`` with
   currency ``XTR`` and the priced pack.
3. ``pre_checkout_query`` → revalidate ``payload`` + ``total_amount``
   against ``credit_packs_xtr`` and answer ``ok=True``.
4. ``F.successful_payment`` → POST to
   ``/api/v1/internal/bot/stars/grant`` with the
   ``telegram_payment_charge_id`` so credits are granted exactly
   once (idempotent on charge_id).

We POST back through the API instead of writing directly to the DB
so the bot process keeps the "no DB connection from bot" invariant
that the rest of the codebase relies on; idempotency is handled by
``record_stars_purchase`` on the FastAPI side.
"""

from __future__ import annotations

import logging

import httpx
from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from src.bot.keyboards import back_keyboard, error_keyboard
from src.config import settings
from src.services.payments.credit_packs import (
    CreditPack,
    get_credit_packs_xtr,
    xtr_pack_by_quantity,
)

logger = logging.getLogger(__name__)
router = Router()

# Telegram-Stars-specific invoice payload.  The ``stars`` prefix lets
# pre_checkout_query reject foreign payloads (e.g. left-over RUB
# invoices from older releases) early instead of letting Telegram
# settle a charge we then can't fulfil.
_PAYLOAD_PREFIX = "stars:pack:"


def _payload_for_pack(qty: int) -> str:
    return f"{_PAYLOAD_PREFIX}{qty}"


def _pack_from_payload(payload: str) -> CreditPack | None:
    if not payload or not payload.startswith(_PAYLOAD_PREFIX):
        return None
    try:
        qty = int(payload[len(_PAYLOAD_PREFIX) :])
    except ValueError:
        return None
    return xtr_pack_by_quantity(qty)


def _stars_pack_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for pack in get_credit_packs_xtr():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"\u2b50 {pack.label}",
                    callback_data=f"buy_xtr:{pack.quantity}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="\U0001f4b0 Мой баланс", callback_data="balance")]
    )
    rows.append(
        [InlineKeyboardButton(text="\U0001f4f8 Новое фото", callback_data="new_photo")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "topup_stars")
async def on_topup_stars(callback: CallbackQuery) -> None:
    await callback.answer()
    packs = get_credit_packs_xtr()
    if not packs:
        await callback.message.answer(
            "\u274c Оплата звёздами временно недоступна. Попробуй позже.",
            reply_markup=error_keyboard(),
        )
        return
    await callback.message.answer(
        "\u2b50 *Оплата Telegram Stars*\n\n"
        "Выбери пакет — звёзды спишутся прямо в Telegram, кредиты придут моментально.",
        parse_mode="Markdown",
        reply_markup=_stars_pack_keyboard(),
    )


@router.callback_query(F.data.startswith("buy_xtr:"))
async def on_buy_xtr(callback: CallbackQuery) -> None:
    await callback.answer()
    raw = (callback.data or "").split(":", 1)[1] if ":" in (callback.data or "") else ""
    try:
        qty = int(raw)
    except ValueError:
        await callback.message.answer(
            "\u274c Неверный пакет.", reply_markup=error_keyboard()
        )
        return

    pack = xtr_pack_by_quantity(qty)
    if pack is None:
        await callback.message.answer(
            "\u274c Этот пакет больше не доступен.",
            reply_markup=error_keyboard(),
        )
        return

    try:
        await callback.bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=f"{pack.quantity} образов",
            description=(
                "Кредиты для AI Look Studio — оплата через Telegram Stars. "
                "Зачисление автоматическое."
            ),
            payload=_payload_for_pack(pack.quantity),
            provider_token="",  # XTR requires an empty provider_token
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=f"{pack.quantity} образов",
                    amount=pack.price_stars,
                )
            ],
        )
    except Exception:
        logger.exception(
            "Stars send_invoice failed for tg_id=%s pack=%s",
            callback.from_user.id if callback.from_user else "?",
            pack.quantity,
        )
        await callback.message.answer(
            "\u274c Не удалось создать счёт. Попробуй ещё раз.",
            reply_markup=error_keyboard(),
        )


@router.pre_checkout_query()
async def on_pre_checkout_query(query: PreCheckoutQuery) -> None:
    """Revalidate amount/currency before Telegram captures the payment.

    Telegram lets the *client* construct ``send_invoice``'s payload,
    so a tampered client could try to pay less than the configured
    price.  We re-derive the canonical price from
    ``credit_packs_xtr`` and reject anything that does not match.
    """
    pack = _pack_from_payload(query.invoice_payload or "")
    if pack is None:
        await query.answer(
            ok=False,
            error_message="Этот платёж больше не доступен. Открой /balance и выбери пакет заново.",
        )
        return
    if (query.currency or "").upper() != "XTR":
        await query.answer(ok=False, error_message="Неподдерживаемая валюта.")
        return
    if int(query.total_amount or 0) != int(pack.price_stars):
        logger.warning(
            "pre_checkout_query amount mismatch: tg_id=%s payload=%s expected=%s got=%s",
            query.from_user.id if query.from_user else "?",
            query.invoice_payload,
            pack.price_stars,
            query.total_amount,
        )
        await query.answer(
            ok=False,
            error_message="Цена пакета изменилась. Открой /balance и выбери пакет заново.",
        )
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, api_base_url: str) -> None:
    """Idempotent credit grant after Stars ``successful_payment``."""
    sp = message.successful_payment
    if sp is None or message.from_user is None:
        return

    pack = _pack_from_payload(sp.invoice_payload or "")
    if pack is None:
        logger.error(
            "successful_payment with unknown payload=%r tg_id=%s",
            sp.invoice_payload,
            message.from_user.id,
        )
        await message.answer(
            "\u274c Не удалось распознать платёж. Свяжись с поддержкой.",
            reply_markup=error_keyboard(),
        )
        return

    charge_id = sp.telegram_payment_charge_id or ""
    if not charge_id:
        logger.error(
            "successful_payment without telegram_payment_charge_id tg_id=%s",
            message.from_user.id,
        )
        await message.answer(
            "\u274c Платёж принят, но Telegram не прислал идентификатор. Свяжись с поддержкой.",
            reply_markup=error_keyboard(),
        )
        return

    if not settings.internal_api_key:
        logger.error("INTERNAL_API_KEY is empty — cannot grant Stars credits")
        await message.answer(
            "\u274c Сервис не настроен (internal key). Поддержка уведомлена.",
            reply_markup=error_keyboard(),
        )
        return

    grant_url = f"{api_base_url.rstrip('/')}/api/v1/internal/bot/stars/grant"
    payload = {
        "telegram_id": message.from_user.id,
        "pack_qty": pack.quantity,
        "telegram_payment_charge_id": charge_id,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                grant_url,
                json=payload,
                headers={"X-Internal-Key": settings.internal_api_key},
            )
    except Exception:
        logger.exception(
            "Stars grant HTTP call failed for tg_id=%s charge=%s",
            message.from_user.id,
            charge_id,
        )
        await message.answer(
            "\u274c Платёж получен, кредиты зачислятся в течение нескольких минут. "
            "Если этого не произошло — напиши в поддержку.",
            reply_markup=error_keyboard(),
        )
        return

    if resp.status_code != 200:
        logger.error(
            "Stars grant non-200 status=%s body=%s tg_id=%s charge=%s",
            resp.status_code,
            resp.text[:300],
            message.from_user.id,
            charge_id,
        )
        await message.answer(
            "\u274c Платёж получен, но не удалось зачислить кредиты автоматически. "
            "Напиши в поддержку и приложи этот чек.",
            reply_markup=error_keyboard(),
        )
        return

    try:
        data = resp.json()
    except ValueError:
        data = {}
    status = data.get("status") or "ok"
    balance = data.get("image_credits")

    if status == "duplicate":
        msg = (
            "\u2705 Платёж уже был обработан ранее. Баланс не изменился.\n\n"
            f"Текущий баланс: *{balance if balance is not None else '?'}* образов."
        )
    else:
        msg = (
            f"\u2705 *Оплачено {pack.price_stars} \u2b50*\n\n"
            f"Зачислено: *+{pack.quantity}* образов.\n"
            f"Баланс: *{balance if balance is not None else pack.quantity}*."
        )

    await message.answer(msg, parse_mode="Markdown", reply_markup=back_keyboard())

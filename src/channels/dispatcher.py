"""Omnichannel notification dispatcher.

Given a user_id, resolves all linked identities and sends notifications
through each channel that supports server-initiated push.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db import User, UserIdentity

logger = logging.getLogger(__name__)


async def notify_payment_success(
    user: User,
    pack_qty: int,
    new_balance: int,
    db: AsyncSession,
) -> None:
    text = (
        f"✅ Оплата прошла успешно!\n\n"
        f"Начислено: *{pack_qty} образов*\n"
        f"Баланс: *{new_balance} образов*\n\n"
        f"Отправь фото для примерки образа!"
    )
    await _dispatch_text(user, text, db)


async def notify_task_completed(
    user: User,
    task_id: str,
    mode: str,
    db: AsyncSession,
) -> None:
    text = f"✅ Обработка завершена ({mode}). Результат готов!"
    await _dispatch_text(user, text, db)


async def _dispatch_text(user: User, text: str, db: AsyncSession) -> None:
    """Send text to all push-capable channels for the user."""
    result = await db.execute(
        select(UserIdentity).where(UserIdentity.user_id == user.id)
    )
    identities = result.scalars().all()

    tg_ids: set[str] = set()
    for ident in identities:
        if ident.provider == "telegram":
            tg_ids.add(ident.external_id)

    # Backward compat: User.telegram_id may not have a corresponding identity row yet
    if user.telegram_id and str(user.telegram_id) not in tg_ids:
        tg_ids.add(str(user.telegram_id))

    if tg_ids:
        from src.channels.telegram_notify import send_telegram_message
        for tg_id in tg_ids:
            await send_telegram_message(int(tg_id), text)

    # WhatsApp, OK, VK — extend here as channels are added

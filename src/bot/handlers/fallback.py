"""Catch-all handlers for unrecognized messages and callbacks."""
from __future__ import annotations

from aiogram import Router
from aiogram.types import Message, CallbackQuery

from src.bot.keyboards import back_keyboard

router = Router()


@router.message()
async def catch_all_message(message: Message):
    await message.answer(
        "\U0001f4f8 Отправь мне фото, и я подберу лучший образ!",
        reply_markup=back_keyboard(),
    )


@router.callback_query()
async def catch_all_callback(callback: CallbackQuery):
    await callback.answer("Неизвестная команда. Отправь фото!")

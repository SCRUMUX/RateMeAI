from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.services.style_catalog import STYLE_CATALOG


def scenario_keyboard() -> InlineKeyboardMarkup:
    """Primary 3-button scenario selection (no Rating in main flow)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f495 Знакомства", callback_data="pick_style:dating"
                )
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4bc Карьера", callback_data="pick_style:cv"
                )
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4f8 Соцсети", callback_data="pick_style:social"
                )
            ],
        ]
    )


# Legacy alias — some handlers still reference this
mode_selection_keyboard = scenario_keyboard

_PAGE_SIZE = 6


def style_keyboard(mode: str, page: int = 0) -> InlineKeyboardMarkup:
    """Paginated style selection: 6 per page, 2 per row, with navigation."""
    catalog = STYLE_CATALOG.get(mode, [])
    start = page * _PAGE_SIZE
    end = start + _PAGE_SIZE
    items = catalog[start:end]

    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(items), 2):
        row = [
            InlineKeyboardButton(
                text=items[i][1], callback_data=f"style:{mode}:{items[i][0]}"
            )
        ]
        if i + 1 < len(items):
            row.append(
                InlineKeyboardButton(
                    text=items[i + 1][1],
                    callback_data=f"style:{mode}:{items[i + 1][0]}",
                )
            )
        rows.append(row)

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="\u2b05\ufe0f Назад",
                callback_data=f"styles_page:{mode}:{page - 1}",
            )
        )
    if end < len(catalog):
        nav_row.append(
            InlineKeyboardButton(
                text="Ещё стили \u27a1\ufe0f",
                callback_data=f"styles_page:{mode}:{page + 1}",
            )
        )
    if nav_row:
        rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def dating_style_keyboard() -> InlineKeyboardMarkup:
    return style_keyboard("dating")


def cv_style_keyboard() -> InlineKeyboardMarkup:
    return style_keyboard("cv")


def social_style_keyboard() -> InlineKeyboardMarkup:
    return style_keyboard("social")


def post_result_keyboard(
    mode: str,
    user_id: str,
    bot_username: str,
    next_options: list[dict] | None = None,
    current_style: str = "",
) -> InlineKeyboardMarkup:
    """Post-result: 2 next-level buttons + share + new photo.

    When ``current_style`` is set and the mode supports styles, the primary
    action becomes **«🎲 Другой вариант»** — rotates to the next un-seen
    content variant of the same style (``variant:*`` callback).
    """
    deep_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    rows = []

    if current_style and mode in ("dating", "cv", "social"):
        rows.append(
            [
                InlineKeyboardButton(
                    text="\U0001f3b2 Другой вариант",
                    callback_data=f"variant:{mode}:{current_style}",
                ),
                InlineKeyboardButton(
                    text="\U0001f3a8 Другой стиль",
                    callback_data=f"restyle:{mode}",
                ),
            ]
        )
    elif next_options and len(next_options) >= 2:
        rows.append(
            [
                InlineKeyboardButton(
                    text=next_options[0]["label"],
                    callback_data=next_options[0]["callback_data"],
                ),
                InlineKeyboardButton(
                    text=next_options[1]["label"],
                    callback_data=next_options[1]["callback_data"],
                ),
            ]
        )
    elif mode == "dating":
        rows.append(
            [
                InlineKeyboardButton(
                    text="\U0001f3b2 Другой вариант",
                    callback_data="variant:dating:warm_outdoor",
                ),
                InlineKeyboardButton(
                    text="\U0001f3a8 Другой стиль", callback_data="restyle:dating"
                ),
            ]
        )
    elif mode == "cv":
        rows.append(
            [
                InlineKeyboardButton(
                    text="\U0001f3b2 Другой вариант",
                    callback_data="variant:cv:corporate",
                ),
                InlineKeyboardButton(
                    text="\U0001f3a8 Другой стиль", callback_data="restyle:cv"
                ),
            ]
        )
    elif mode == "social":
        rows.append(
            [
                InlineKeyboardButton(
                    text="\U0001f3b2 Другой вариант",
                    callback_data="variant:social:influencer_urban",
                ),
                InlineKeyboardButton(
                    text="\U0001f3a8 Другой стиль", callback_data="restyle:social"
                ),
            ]
        )
    elif mode == "rating":
        rows.append(
            [
                InlineKeyboardButton(
                    text="\U0001f495 Знакомства", callback_data="pick_style:dating"
                ),
                InlineKeyboardButton(
                    text="\U0001f4bc Карьера", callback_data="pick_style:cv"
                ),
            ]
        )

    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="\U0001f4e4 Друзьям", switch_inline_query=deep_link
                ),
                InlineKeyboardButton(
                    text="\U0001f4f8 Новое фото", callback_data="new_photo"
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# Legacy aliases for backward compatibility
def action_keyboard(bot_username: str, user_id: str) -> InlineKeyboardMarkup:
    return post_result_keyboard("dating", user_id, bot_username)


def loop_keyboard(
    bot_username: str, user_id: str, current_mode: str
) -> InlineKeyboardMarkup:
    return post_result_keyboard(current_mode, user_id, bot_username)


def error_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f504 Попробовать снова", callback_data="retry"
                )
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4f8 Новое фото", callback_data="new_photo"
                )
            ],
        ]
    )


def upgrade_keyboard() -> InlineKeyboardMarkup:
    from src.services.payments import get_credit_packs

    rows = []
    for pack in get_credit_packs():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"\U0001f6d2 {pack.label}",
                    callback_data=f"buy:{pack.quantity}",
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


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f4f8 Загрузить фото", callback_data="new_photo"
                )
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4b3 Пополнить баланс", callback_data="topup"
                )
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f517 Привязать аккаунт", callback_data="link_account"
                )
            ],
        ]
    )


def link_wizard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f310 У меня есть аккаунт на сайте",
                    callback_data="link_have_web",
                )
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f4f2 Хочу войти на сайт через бот",
                    callback_data="link_to_web",
                )
            ],
            [InlineKeyboardButton(text="\u2b05 Назад", callback_data="link_cancel")],
        ]
    )


def link_waiting_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u274c Отмена", callback_data="link_cancel")],
        ]
    )

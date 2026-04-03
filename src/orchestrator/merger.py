from __future__ import annotations

from src.config import settings


class ResultMerger:
    """Merges analysis result with share metadata."""

    def merge(self, result: dict, share_card_url: str | None, user_id: str) -> dict:
        uname = settings.telegram_bot_username.lstrip("@")
        deep_link = f"https://t.me/{uname}?start=ref_{user_id}"

        score = result.get("score")
        if score is not None:
            caption = f"Мой рейтинг: {score}/10 🔥 Узнай свой → @{uname}"
        else:
            caption = f"Смотри мой результат → @{uname}"

        result["share"] = {
            "card_url": share_card_url,
            "caption": caption,
            "deep_link": deep_link,
        }
        return result

from __future__ import annotations

from src.config import settings


class ResultMerger:
    """Merges analysis result with share metadata."""

    def merge(self, result: dict, share_card_url: str | None, user_id: str) -> dict:
        uname = settings.telegram_bot_username.lstrip("@")
        deep_link = f"https://t.me/{uname}?start=ref_{user_id}"

        caption = self._build_caption(result, uname)

        result["share"] = {
            "card_url": share_card_url,
            "caption": caption,
            "deep_link": deep_link,
        }
        return result

    @staticmethod
    def _build_caption(result: dict, bot_username: str) -> str:
        score = result.get("score")
        if score is not None:
            return f"Мой рейтинг: {score}/10 — узнай свой → @{bot_username}"

        dating = result.get("dating_score")
        if dating is not None:
            return f"Стиль для знакомств: {dating}/10 — попробуй → @{bot_username}"

        social = result.get("social_score")
        if social is not None:
            return f"Стиль для соцсетей: {social}/10 — попробуй → @{bot_username}"

        hire = result.get("hireability")
        if hire is not None:
            return f"Карьерный стиль: {hire}/10 — оцени своё фото → @{bot_username}"

        return f"Смотри мой результат → @{bot_username}"

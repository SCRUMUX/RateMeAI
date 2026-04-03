from __future__ import annotations

BOT_USERNAME = "RateMeAIBot"


class ResultMerger:
    """Merges analysis result with share metadata."""

    def merge(self, result: dict, share_card_url: str | None, user_id: str) -> dict:
        deep_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

        score = result.get("score")
        if score is not None:
            caption = f"Мой рейтинг: {score}/10 🔥 Узнай свой → @{BOT_USERNAME}"
        else:
            caption = f"Смотри мой результат → @{BOT_USERNAME}"

        result["share"] = {
            "card_url": share_card_url,
            "caption": caption,
            "deep_link": deep_link,
        }
        return result

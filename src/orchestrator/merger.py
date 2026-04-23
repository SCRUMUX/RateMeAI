from __future__ import annotations

from src.channels.deep_links import (
    build_deep_link,
    build_share_caption,
    PROVIDER_TELEGRAM,
)


class ResultMerger:
    """Merges analysis result with share metadata."""

    def merge(
        self,
        result: dict,
        share_card_url: str | None,
        user_id: str,
        channel: str = PROVIDER_TELEGRAM,
    ) -> dict:
        deep_link = build_deep_link(user_id, channel)
        caption = build_share_caption(result, channel)

        result["share"] = {
            "card_url": share_card_url,
            "caption": caption,
            "deep_link": deep_link,
        }
        return result

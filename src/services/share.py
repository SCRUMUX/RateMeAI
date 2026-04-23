from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

from src.config import settings
from src.providers.base import StorageProvider

if TYPE_CHECKING:
    from src.models.schemas import RatingResult

logger = logging.getLogger(__name__)

BOT_USERNAME = settings.telegram_bot_username.lstrip("@")

CARD_WIDTH = 800
CARD_HEIGHT = 1000
BG_COLOR = (18, 18, 24)
ACCENT_COLOR = (139, 92, 246)
TEXT_COLOR = (255, 255, 255)
SUBTEXT_COLOR = (163, 163, 163)

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "arial.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_ai_watermark(draw: ImageDraw.ImageDraw) -> None:
    """Render the mandatory «AI-generated» pill at top-left of the share card.

    This is the share-card equivalent of the on-preview badge rendered by
    StepGenerate.tsx and fulfils the visible-disclosure clause of EU AI Act
    Art. 50 for the downloadable/shared asset.
    """
    pad_x, pad_y = 16, 10
    label = "AI-generated"
    font = _load_font(22)

    text_bbox = draw.textbbox((0, 0), label, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]

    x = 24
    y = 24
    box = [
        (x, y),
        (x + text_w + 2 * pad_x, y + text_h + 2 * pad_y),
    ]
    draw.rounded_rectangle(
        box, radius=20, fill=(0, 0, 0, 160), outline=(255, 255, 255), width=1
    )
    draw.text(
        (x + pad_x, y + pad_y - 2),
        label,
        fill=(255, 255, 255),
        font=font,
    )


class ShareCardGenerator:
    def __init__(self, storage: StorageProvider):
        self._storage = storage

    async def generate_rating_card(
        self,
        result: RatingResult,
        photo_bytes: bytes,
        user_id: str,
        task_id: str,
    ) -> str:
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(card)

        font_large = _load_font(64)
        font_medium = _load_font(28)
        font_small = _load_font(22)

        # User photo (centered, circular crop effect via rounded rect)
        try:
            photo = Image.open(io.BytesIO(photo_bytes))
            photo = photo.convert("RGB")
            photo.thumbnail((300, 300))
            pw, ph = photo.size
            x_offset = (CARD_WIDTH - pw) // 2
            card.paste(photo, (x_offset, 40))
            photo_bottom = 40 + ph
        except Exception:
            photo_bottom = 40

        y = photo_bottom + 30

        # Score
        score_text = f"{result.score:.1f}/10"
        draw.text(
            (CARD_WIDTH // 2, y),
            score_text,
            fill=ACCENT_COLOR,
            font=font_large,
            anchor="mt",
        )
        y += 80

        # Perception metrics bar
        metrics = [
            ("Доверие", result.perception.trust),
            ("Привлекательность", result.perception.attractiveness),
        ]
        for label, value in metrics:
            draw.text((60, y), label, fill=SUBTEXT_COLOR, font=font_small)

            bar_x = 300
            bar_w = 400
            bar_h = 20
            draw.rounded_rectangle(
                [(bar_x, y + 2), (bar_x + bar_w, y + 2 + bar_h)],
                radius=10,
                fill=(40, 40, 50),
            )
            filled_w = int(bar_w * (value / 10))
            if filled_w > 0:
                draw.rounded_rectangle(
                    [(bar_x, y + 2), (bar_x + filled_w, y + 2 + bar_h)],
                    radius=10,
                    fill=ACCENT_COLOR,
                )
            draw.text(
                (bar_x + bar_w + 15, y),
                f"{value:.1f}",
                fill=TEXT_COLOR,
                font=font_small,
            )
            y += 40

        y += 10
        # Emotion
        draw.text(
            (CARD_WIDTH // 2, y),
            f"Эмоция: {result.perception.emotional_expression}",
            fill=TEXT_COLOR,
            font=font_medium,
            anchor="mt",
        )
        y += 50

        # Top insight
        if result.insights:
            insight = result.insights[0]
            if len(insight) > 70:
                insight = insight[:67] + "..."
            draw.text(
                (CARD_WIDTH // 2, y),
                f"«{insight}»",
                fill=SUBTEXT_COLOR,
                font=font_small,
                anchor="mt",
            )
            y += 40

        # Deep link / branding
        y = CARD_HEIGHT - 60
        draw.text(
            (CARD_WIDTH // 2, y),
            f"Узнай свой рейтинг → @{BOT_USERNAME}",
            fill=ACCENT_COLOR,
            font=font_medium,
            anchor="mt",
        )

        # AI transparency watermark (EU AI Act Art. 50): a small but clearly
        # legible badge at the top-left stating that the hero image is
        # AI-generated. Complemented by the EXIF ``UserComment`` tag injected
        # on the generated JPEG itself (see P1.5).
        _draw_ai_watermark(draw)

        buf = io.BytesIO()
        card.save(buf, format="JPEG", quality=90)
        buf.seek(0)

        key = f"cards/{user_id}/{task_id}.jpg"
        await self._storage.upload(key, buf.read())
        return await self._storage.get_url(key)

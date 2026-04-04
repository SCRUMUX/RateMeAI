from __future__ import annotations

import logging

from src.providers.base import LLMProvider

logger = logging.getLogger(__name__)

NSFW_CHECK_PROMPT = """Проанализируй это изображение и определи, содержит ли оно неприемлемый контент (NSFW).

Верни СТРОГО JSON:
{
  "is_safe": true/false,
  "reason": "краткое объяснение если небезопасно, иначе пустая строка"
}

Считай небезопасным: откровенную наготу, насилие, контент с несовершеннолетними.
Обычные портретные фото, пляжные фото в купальниках — безопасны.
НЕ пиши ничего кроме JSON."""

NSFW_INLINE_PREFIX = """МОДЕРАЦИЯ (обязательно): если фото содержит откровенную наготу, насилие или контент с несовершеннолетними — верни ТОЛЬКО {"is_safe": false, "reason": "описание"} и НИЧЕГО больше.
Обычные портретные фото, пляжные фото в купальниках — безопасны. Если фото безопасно, выполни задание ниже.

"""


async def check_nsfw(llm: LLMProvider, image_bytes: bytes) -> tuple[bool, str]:
    """Returns (is_safe, reason). Uses LLM vision for content moderation."""
    try:
        result = await llm.analyze_image(image_bytes, NSFW_CHECK_PROMPT)
        is_safe = result.get("is_safe", True)
        reason = result.get("reason", "")
        return bool(is_safe), str(reason)
    except Exception:
        logger.exception("NSFW check failed, blocking content as precaution")
        return False, "Не удалось проверить содержимое фото. Попробуйте ещё раз."


def extract_nsfw_from_analysis(result: dict) -> tuple[bool, str]:
    """Check if LLM returned an NSFW-only response (inline moderation)."""
    if "is_safe" in result and not result.get("is_safe", True):
        return False, result.get("reason", "Content policy violation")
    return True, ""

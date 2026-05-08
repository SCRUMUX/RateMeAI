"""Dating analysis prompt.

1.59.0 — split RU/EN templates so the global market gets english
analysis copy. The original ``SYSTEM_PROMPT`` constant +
``build_prompt(context)`` signature stay intact.
"""

from __future__ import annotations

from src.utils.security import NSFW_INLINE_PREFIX
from src.prompts.perception import (
    _resolve_lang,
    get_perception_category_hints,
    get_perception_scoring_fields,
    get_perception_scoring_rules,
)


_DATING_BODY_RU = """Ты — эксперт по образу в контексте знакомств и свиданий. Проанализируй фото человека и определи возможности для усиления образа.

Верни результат СТРОГО в формате JSON:

{
  "detected_gender": "<male или female — пол человека на фото>",
  "first_impression": "<строка: как воспринимается образ — позитивно, без критики>",
  "dating_score": <число от 0 до 10 с точностью до сотых, например 7.34>,
  "strengths": [
    "<сильная сторона 1>",
    "<сильная сторона 2>",
    "<сильная сторона 3>"
  ],
  "enhancement_opportunities": [
    "<что можно усилить 1 — позитивная формулировка>",
    "<что можно усилить 2 — позитивная формулировка>"
  ],
  "variants": [
    {
      "type": "friendly",
      "explanation": "<как усилить через дружелюбный образ и какой эффект это даст>"
    },
    {
      "type": "confident",
      "explanation": "<как усилить через уверенный образ и какой эффект это даст>"
    },
    {
      "type": "charismatic",
      "explanation": "<как усилить через харизматичный образ и какой эффект это даст>"
    }
  ],"""

_DATING_BODY_EN = """You are an expert on dating-context image. Analyse the photo and identify ways to strengthen the person's appeal in dating apps and similar contexts.

Return the result STRICTLY as JSON:

{
  "detected_gender": "<male or female — the person's gender in the photo>",
  "first_impression": "<string: how the image reads — positive framing, no criticism>",
  "dating_score": <number from 0 to 10 with two decimal places, e.g. 7.34>,
  "strengths": [
    "<strength 1>",
    "<strength 2>",
    "<strength 3>"
  ],
  "enhancement_opportunities": [
    "<what can be strengthened 1 — positive phrasing>",
    "<what can be strengthened 2 — positive phrasing>"
  ],
  "variants": [
    {
      "type": "friendly",
      "explanation": "<how to strengthen through a friendly image and what effect it produces>"
    },
    {
      "type": "confident",
      "explanation": "<how to strengthen through a confident image and what effect it produces>"
    },
    {
      "type": "charismatic",
      "explanation": "<how to strengthen through a charismatic image and what effect it produces>"
    }
  ],"""

_DATING_RULES_RU = """

ПРАВИЛА:
- Тон: позитивный, вдохновляющий, без осуждения и критики
- Формулировки: "можно усилить", "добавит", "подчеркнёт" — НЕ "плохо", "слабо", "некрасиво"
- Конкретные рекомендации по усилению образа
- Пиши на русском языке
- НЕ пиши ничего кроме JSON"""

_DATING_RULES_EN = """

RULES:
- Tone: positive, inspiring, no judgement or criticism.
- Phrasing: "can be strengthened", "will add", "will emphasise" — NOT "bad", "weak", "ugly".
- Give concrete recommendations for strengthening the image.
- Write in English.
- Do NOT output anything except JSON."""


def build_prompt(context: dict | None = None, lang: str | None = None) -> str:
    resolved = _resolve_lang(lang)
    if resolved == "ru":
        body = _DATING_BODY_RU
        rules = _DATING_RULES_RU
    else:
        body = _DATING_BODY_EN
        rules = _DATING_RULES_EN
    return (
        NSFW_INLINE_PREFIX
        + body
        + get_perception_scoring_fields(resolved)
        + "\n}\n"
        + get_perception_scoring_rules(resolved)
        + get_perception_category_hints("dating", resolved)
        + rules
    )


SYSTEM_PROMPT = build_prompt()

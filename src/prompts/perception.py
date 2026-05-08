"""Shared perception scoring prompt block appended to all analysis prompts.

Defines three scorable parameters (warmth, presence, appeal) that map
to controllable generation steps, plus positive-framing rules.

1.59.0 — extracted RU/EN variants so the global market gets english
``first_impression`` / insight copy instead of forcing the LLM to
write Russian on an English landing.
"""

from __future__ import annotations

PERCEPTION_SCORING_FIELDS_RU = """
  "perception_scores": {
    "warmth": <насколько человек выглядит теплым, открытым, располагающим к доверию — мягкость взгляда, теплота освещения, дружелюбная обстановка>,
    "presence": <насколько человек выглядит уверенным, собранным, харизматичным — прямой взгляд, осанка, стильная одежда, статусный контекст>,
    "appeal": <насколько изображение визуально привлекательно в целом — свет, композиция, стиль, качество кожи, гармония образа>
  },
  "perception_insights": [
    {
      "parameter": "<warmth|presence|appeal>",
      "current_level": "<peak|strong|solid_base|growth_zone>",
      "suggestion": "<позитивная рекомендация>",
      "controllable_by": "<lighting|expression|background|clothing|skin>"
    }
  ]"""

PERCEPTION_SCORING_FIELDS_EN = """
  "perception_scores": {
    "warmth": <how warm, open, and trustworthy the person appears — softness of gaze, warm lighting, friendly atmosphere>,
    "presence": <how confident, composed, and charismatic the person looks — direct gaze, posture, stylish clothing, status context>,
    "appeal": <how visually appealing the image is overall — light, composition, style, skin quality, harmony of the look>
  },
  "perception_insights": [
    {
      "parameter": "<warmth|presence|appeal>",
      "current_level": "<peak|strong|solid_base|growth_zone>",
      "suggestion": "<positive recommendation>",
      "controllable_by": "<lighting|expression|background|clothing|skin>"
    }
  ]"""

PERCEPTION_SCORING_RULES_RU = """
Дополнительно оцени 3 параметра восприятия (от 0 до 10, с точностью до сотых): warmth, presence, appeal.
Добавь perception_insights — позитивные рекомендации по усилению каждого параметра.

ПРАВИЛА ДЛЯ perception_insights:
- ЗАПРЕЩЕНО использовать оценочные «плохо», «слабо», «некрасиво», «не так», «не тот»
- ОБЯЗАТЕЛЬНО использовать позитивные формулировки: «предлагаю», «можно усилить», «добавит», «подчеркнёт», «усилит ощущение»
- Каждый suggestion должен ссылаться на конкретное управляемое изменение (свет, фон, одежда, выражение, кожа)
- current_level: peak (9.0-10.0), strong (7.5-8.99), solid_base (6.0-7.49), growth_zone (0-5.99). Округляй значения до сотых; при ровно 9.00 используй peak, при ровно 7.50 — strong, при ровно 6.00 — solid_base.
- Минимум 2, максимум 3 insight-а — по одному на каждый параметр ниже «peak»
"""

PERCEPTION_SCORING_RULES_EN = """
Additionally score 3 perception parameters (0-10, two decimal places): warmth, presence, appeal.
Add perception_insights — positive recommendations for strengthening each parameter.

RULES FOR perception_insights:
- FORBIDDEN: judgmental words such as "bad", "weak", "ugly", "wrong", "not the right".
- REQUIRED: positive phrasing such as "I suggest", "you can strengthen", "will add", "will emphasise", "will reinforce the feeling of".
- Each suggestion must point to a concrete controllable change (lighting, background, clothing, expression, skin).
- current_level: peak (9.0-10.0), strong (7.5-8.99), solid_base (6.0-7.49), growth_zone (0-5.99). Round to two decimal places; exactly 9.00 → peak, exactly 7.50 → strong, exactly 6.00 → solid_base.
- Minimum 2, maximum 3 insights — one per parameter below "peak".
"""

PERCEPTION_CATEGORY_HINTS_RU: dict[str, str] = {
    "dating": (
        "\nКОНТЕКСТ ОЦЕНКИ: знакомства. "
        "Теплота и привлекательность — ключевые параметры для этого контекста. "
        "Уверенность важна, но вторична."
    ),
    "cv": (
        "\nКОНТЕКСТ ОЦЕНКИ: карьера и профессиональный образ. "
        "Уверенность и теплота (доверие) — ключевые параметры для этого контекста. "
        "Привлекательность оценивается как общее качество образа."
    ),
    "social": (
        "\nКОНТЕКСТ ОЦЕНКИ: социальные сети. "
        "Привлекательность и уверенность — ключевые параметры для этого контекста. "
        "Теплота добавляет вовлечённость аудитории."
    ),
    "rating": ("\nКОНТЕКСТ ОЦЕНКИ: общее восприятие. Все три параметра равнозначны."),
}

PERCEPTION_CATEGORY_HINTS_EN: dict[str, str] = {
    "dating": (
        "\nSCORING CONTEXT: dating. "
        "Warmth and appeal are the key parameters in this context. "
        "Confidence matters but is secondary."
    ),
    "cv": (
        "\nSCORING CONTEXT: career and professional image. "
        "Confidence and warmth (trust) are the key parameters in this context. "
        "Appeal is treated as the overall quality of the look."
    ),
    "social": (
        "\nSCORING CONTEXT: social media. "
        "Appeal and confidence are the key parameters in this context. "
        "Warmth boosts audience engagement."
    ),
    "rating": ("\nSCORING CONTEXT: general perception. All three parameters carry equal weight."),
}


def _resolve_lang(lang: str | None = None) -> str:
    """Resolve which prompt language to use.

    Explicit ``lang`` arg wins. Otherwise we look at
    ``settings.resolved_market_id``:
      - ``ru`` (RU edge) → Russian prompts;
      - ``global`` / ``en`` → English prompts;
      - anything else (incl. unset / tests) → Russian, because the
        original prompt corpus was Russian and existing tests assert
        Russian phrasing. This keeps backward compatibility while
        letting the global market opt into EN explicitly.
    """
    if isinstance(lang, str):
        normalised = lang.strip().lower()
        if normalised in {"ru", "russian"}:
            return "ru"
        if normalised in {"en", "english", "global"}:
            return "en"
    try:
        from src.config import settings  # local import — avoid bootstrap cycles

        market = (settings.resolved_market_id or "").strip().lower()
    except Exception:
        market = ""
    if market in {"global", "en"}:
        return "en"
    return "ru"


def get_perception_scoring_fields(lang: str | None = None) -> str:
    return PERCEPTION_SCORING_FIELDS_RU if _resolve_lang(lang) == "ru" else PERCEPTION_SCORING_FIELDS_EN


def get_perception_scoring_rules(lang: str | None = None) -> str:
    return PERCEPTION_SCORING_RULES_RU if _resolve_lang(lang) == "ru" else PERCEPTION_SCORING_RULES_EN


def get_perception_category_hints(category: str, lang: str | None = None) -> str:
    table = PERCEPTION_CATEGORY_HINTS_RU if _resolve_lang(lang) == "ru" else PERCEPTION_CATEGORY_HINTS_EN
    return table.get(category, "")


# Backwards-compatible aliases — keep the module-level constants working
# for callers that imported them directly. These resolve the language at
# import time, so mocking `_resolve_lang` after import does not flip
# them; for new code use the getters above.
PERCEPTION_SCORING_FIELDS = get_perception_scoring_fields()
PERCEPTION_SCORING_RULES = get_perception_scoring_rules()
PERCEPTION_SCORING_BLOCK = PERCEPTION_SCORING_FIELDS

# Legacy dict shape — keys are categories, values are RU strings (the
# original behaviour). Kept so existing imports do not break; new code
# should call ``get_perception_category_hints``.
PERCEPTION_CATEGORY_HINTS: dict[str, str] = (
    PERCEPTION_CATEGORY_HINTS_RU if _resolve_lang() == "ru" else PERCEPTION_CATEGORY_HINTS_EN
)

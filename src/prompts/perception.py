"""Shared perception scoring prompt block appended to all analysis prompts.

Defines three scorable parameters (warmth, presence, appeal) that map
to controllable generation steps, plus positive-framing rules.
"""

PERCEPTION_SCORING_FIELDS = """
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

PERCEPTION_SCORING_RULES = """
Дополнительно оцени 3 параметра восприятия (от 0 до 10, с точностью до сотых): warmth, presence, appeal.
Добавь perception_insights — позитивные рекомендации по усилению каждого параметра.

ПРАВИЛА ДЛЯ perception_insights:
- ЗАПРЕЩЕНО использовать оценочные «плохо», «слабо», «некрасиво», «не так», «не тот»
- ОБЯЗАТЕЛЬНО использовать позитивные формулировки: «предлагаю», «можно усилить», «добавит», «подчеркнёт», «усилит ощущение»
- Каждый suggestion должен ссылаться на конкретное управляемое изменение (свет, фон, одежда, выражение, кожа)
- current_level: peak (9.0-10.0), strong (7.5-8.99), solid_base (6.0-7.49), growth_zone (0-5.99). Округляй значения до сотых; при ровно 9.00 используй peak, при ровно 7.50 — strong, при ровно 6.00 — solid_base.
- Минимум 2, максимум 3 insight-а — по одному на каждый параметр ниже «peak»
"""

# Backwards-compatible alias used by existing imports
PERCEPTION_SCORING_BLOCK = PERCEPTION_SCORING_FIELDS

PERCEPTION_CATEGORY_HINTS = {
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
    "rating": (
        "\nКОНТЕКСТ ОЦЕНКИ: общее восприятие. "
        "Все три параметра равнозначны."
    ),
}

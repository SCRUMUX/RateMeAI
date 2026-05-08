"""CV / professional analysis prompt.

1.59.0 — RU/EN templates with a language-aware ``build_prompt``. The
context dict still accepts ``profession`` exactly like before.
"""

from __future__ import annotations

from src.utils.security import NSFW_INLINE_PREFIX
from src.prompts.perception import (
    _resolve_lang,
    get_perception_category_hints,
    get_perception_scoring_fields,
)


_CV_HEADER_RU = (
    "Ты — HR-эксперт и специалист по профессиональному имиджу. "
    "Проанализируй фото человека и определи возможности для усиления "
    "профессионального образа{profession_suffix}.\n\n"
    "Верни результат СТРОГО в формате JSON:\n\n"
    "{{\n"
    '  "detected_gender": "<male или female — пол человека на фото>",\n'
    '  "first_impression": "<короткая емкая фраза (3-5 слов) о первом впечатлении>",\n'
    '  "profession": "{profession}",\n'
    '  "trust": <число от 0 до 10 с точностью до сотых, насколько человек вызывает доверие>,\n'
    '  "competence": <число от 0 до 10 с точностью до сотых, восприятие компетентности>,\n'
    '  "hireability": <число от 0 до 10 с точностью до сотых, вероятность что пригласят на собеседование>,\n'
    '  "analysis": "<как усилить профессиональный образ — позитивные рекомендации>",'
)

_CV_HEADER_EN = (
    "You are an HR expert and professional-image specialist. "
    "Analyse the photo and identify ways to strengthen the person's "
    "professional image{profession_suffix}.\n\n"
    "Return the result STRICTLY as JSON:\n\n"
    "{{\n"
    '  "detected_gender": "<male or female — the person\'s gender in the photo>",\n'
    '  "first_impression": "<a short, punchy phrase (3-5 words) about the first impression>",\n'
    '  "profession": "{profession}",\n'
    '  "trust": <number from 0 to 10 with two decimal places, how trustworthy the person looks>,\n'
    '  "competence": <number from 0 to 10 with two decimal places, perception of competence>,\n'
    '  "hireability": <number from 0 to 10 with two decimal places, probability of being invited to interview>,\n'
    '  "analysis": "<how to strengthen the professional image — positive recommendations>",'
)


_CV_FOOTER_RU_TEMPLATE = (
    "\n}}\n{hints}\n\n"
    "ПРАВИЛА ДЛЯ perception_insights:\n"
    '- ЗАПРЕЩЕНО: "плохо", "слабо", "некрасиво", "не так", "не тот"\n'
    '- ОБЯЗАТЕЛЬНО: "предлагаю", "можно усилить", "добавит", "подчеркнёт", "усилит ощущение"\n'
    "- current_level: peak (9.0-10.0), strong (7.5-8.99), solid_base (6.0-7.49), "
    "growth_zone (0-5.99). Округляй значения до сотых; "
    "при ровно 9.00 используй peak, при ровно 7.50 — strong, при ровно 6.00 — solid_base.\n"
    "- Минимум 2, максимум 3 insight-а\n\n"
    "ПРАВИЛА:\n"
    "- Тон: позитивный, конструктивный\n"
    '- Формулировки: "можно усилить", "добавит доверия", "подчеркнёт компетентность"\n'
    "- Давай конкретные рекомендации по усилению профессионального образа\n"
    "- Пиши на русском языке\n"
    "- НЕ пиши ничего кроме JSON"
)

_CV_FOOTER_EN_TEMPLATE = (
    "\n}}\n{hints}\n\n"
    "RULES FOR perception_insights:\n"
    '- FORBIDDEN: "bad", "weak", "ugly", "wrong", "not the right".\n'
    '- REQUIRED: "I suggest", "you can strengthen", "will add", "will emphasise", "will reinforce the feeling of".\n'
    "- current_level: peak (9.0-10.0), strong (7.5-8.99), solid_base (6.0-7.49), "
    "growth_zone (0-5.99). Round to two decimal places; "
    "exactly 9.00 → peak, exactly 7.50 → strong, exactly 6.00 → solid_base.\n"
    "- Minimum 2, maximum 3 insights.\n\n"
    "RULES:\n"
    "- Tone: positive, constructive.\n"
    '- Phrasing: "can be strengthened", "will add trust", "will emphasise competence".\n'
    "- Provide concrete recommendations for strengthening the professional image.\n"
    "- Write in English.\n"
    "- Do NOT output anything except JSON."
)


def build_prompt(context: dict | None = None, lang: str | None = None) -> str:
    ctx = context or {}
    resolved = _resolve_lang(lang)

    if resolved == "ru":
        profession = ctx.get("profession", "не указана")
        suffix = f' для профессии "{profession}"' if profession != "не указана" else ""
        header = _CV_HEADER_RU.format(profession=profession, profession_suffix=suffix)
        footer = _CV_FOOTER_RU_TEMPLATE.format(
            hints=get_perception_category_hints("cv", resolved)
        )
    else:
        profession = ctx.get("profession", "not specified")
        # When the caller is RU-side but the prompt resolves to EN
        # (mostly tests), still translate the placeholder so the prompt
        # is internally consistent.
        if profession == "не указана":
            profession = "not specified"
        suffix = (
            f' for the profession "{profession}"'
            if profession != "not specified"
            else ""
        )
        header = _CV_HEADER_EN.format(profession=profession, profession_suffix=suffix)
        footer = _CV_FOOTER_EN_TEMPLATE.format(
            hints=get_perception_category_hints("cv", resolved)
        )

    return NSFW_INLINE_PREFIX + header + get_perception_scoring_fields(resolved) + footer

from src.utils.security import NSFW_INLINE_PREFIX
from src.prompts.perception import PERCEPTION_CATEGORY_HINTS, PERCEPTION_SCORING_FIELDS


_CV_HEADER_TEMPLATE = (
    "Ты — HR-эксперт и специалист по профессиональному имиджу. "
    "Проанализируй фото человека и определи возможности для усиления "
    "профессионального образа{profession_suffix}.\n\n"
    "Верни результат СТРОГО в формате JSON:\n\n"
    "{{\n"
    '  "detected_gender": "<male или female — пол человека на фото>",\n'
    '  "profession": "{profession}",\n'
    '  "trust": <число от 0 до 10 с точностью до сотых, насколько человек вызывает доверие>,\n'
    '  "competence": <число от 0 до 10 с точностью до сотых, восприятие компетентности>,\n'
    '  "hireability": <число от 0 до 10 с точностью до сотых, вероятность что пригласят на собеседование>,\n'
    '  "analysis": "<как усилить профессиональный образ — позитивные рекомендации>",'
)

_CV_FOOTER = (
    "\n}\n"
    + PERCEPTION_CATEGORY_HINTS["cv"]
    + "\n\n"
    "ПРАВИЛА ДЛЯ perception_insights:\n"
    "- ЗАПРЕЩЕНО: \"плохо\", \"слабо\", \"некрасиво\", \"не так\", \"не тот\"\n"
    "- ОБЯЗАТЕЛЬНО: \"предлагаю\", \"можно усилить\", \"добавит\", \"подчеркнёт\", \"усилит ощущение\"\n"
    "- current_level: peak (9.0-10.0), strong (7.5-8.99), solid_base (6.0-7.49), "
    "growth_zone (0-5.99). Округляй значения до сотых; "
    "при ровно 9.00 используй peak, при ровно 7.50 — strong, при ровно 6.00 — solid_base.\n"
    "- Минимум 2, максимум 3 insight-а\n\n"
    "ПРАВИЛА:\n"
    "- Тон: позитивный, конструктивный\n"
    "- Формулировки: \"можно усилить\", \"добавит доверия\", \"подчеркнёт компетентность\"\n"
    "- Давай конкретные рекомендации по усилению профессионального образа\n"
    "- Пиши на русском языке\n"
    "- НЕ пиши ничего кроме JSON"
)


def build_prompt(context: dict) -> str:
    profession = context.get("profession", "не указана")
    suffix = f" для профессии \"{profession}\"" if profession != "не указана" else ""
    header = _CV_HEADER_TEMPLATE.format(
        profession=profession, profession_suffix=suffix,
    )
    return NSFW_INLINE_PREFIX + header + PERCEPTION_SCORING_FIELDS + _CV_FOOTER

from src.utils.security import NSFW_INLINE_PREFIX
from src.prompts.perception import PERCEPTION_CATEGORY_HINTS

_PERCEPTION_CV_BLOCK = """
  "perception_scores": {{
    "warmth": <насколько человек выглядит теплым, открытым, располагающим к доверию — мягкость взгляда, теплота освещения, дружелюбная обстановка>,
    "presence": <насколько человек выглядит уверенным, собранным, харизматичным — прямой взгляд, осанка, стильная одежда, статусный контекст>,
    "appeal": <насколько изображение визуально привлекательно в целом — свет, композиция, стиль, качество кожи, гармония образа>
  }},
  "perception_insights": [
    {{
      "parameter": "<warmth|presence|appeal>",
      "current_level": "<peak|strong|solid_base|growth_zone>",
      "suggestion": "<позитивная рекомендация: предлагаю / можно усилить / добавит / подчеркнёт>",
      "controllable_by": "<lighting|expression|background|clothing|skin>"
    }}
  ]
"""

SYSTEM_PROMPT_TEMPLATE = NSFW_INLINE_PREFIX + """Ты — HR-эксперт и специалист по профессиональному имиджу. Проанализируй фото человека и определи возможности для усиления профессионального образа{profession_suffix}.

Верни результат СТРОГО в формате JSON:

{{
  "profession": "{profession}",
  "trust": <число от 0 до 10 с точностью до сотых, насколько человек вызывает доверие>,
  "competence": <число от 0 до 10 с точностью до сотых, восприятие компетентности>,
  "hireability": <число от 0 до 10 с точностью до сотых, вероятность что пригласят на собеседование>,
  "analysis": "<как усилить профессиональный образ — позитивные рекомендации>",""" + _PERCEPTION_CV_BLOCK + """
}}
""" + PERCEPTION_CATEGORY_HINTS["cv"] + """

ПРАВИЛА ДЛЯ perception_insights:
- ЗАПРЕЩЕНО: "плохо", "слабо", "некрасиво", "не так", "неуверенный", "закрытый"
- ОБЯЗАТЕЛЬНО: "предлагаю", "можно усилить", "добавит", "подчеркнёт", "усилит ощущение"
- current_level: peak (9.0-10.0), strong (7.5-8.99), solid_base (6.0-7.49), growth_zone (0-5.99)
- Минимум 2, максимум 3 insight-а

ПРАВИЛА:
- Тон: позитивный, конструктивный
- Формулировки: "можно усилить", "добавит доверия", "подчеркнёт компетентность"
- Давай конкретные рекомендации по усилению профессионального образа
- Пиши на русском языке
- НЕ пиши ничего кроме JSON"""


def build_prompt(context: dict) -> str:
    profession = context.get("profession", "не указана")
    suffix = f" для профессии \"{profession}\"" if profession != "не указана" else ""
    return SYSTEM_PROMPT_TEMPLATE.format(profession=profession, profession_suffix=suffix)

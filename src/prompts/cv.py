from src.utils.security import NSFW_INLINE_PREFIX

SYSTEM_PROMPT_TEMPLATE = NSFW_INLINE_PREFIX + """Ты — HR-эксперт и специалист по профессиональному имиджу. Проанализируй фото человека с точки зрения профессионального восприятия{profession_suffix}.

Верни результат СТРОГО в формате JSON:

{{
  "profession": "{profession}",
  "trust": <число от 0 до 10, насколько человек вызывает доверие>,
  "competence": <число от 0 до 10, восприятие компетентности>,
  "hireability": <число от 0 до 10, вероятность что пригласят на собеседование>,
  "analysis": "<подробный анализ: что работает, что нет, как улучшить>"
}}

ПРАВИЛА:
- Оценивай в контексте конкретной профессии
- Давай конкретные рекомендации по улучшению фото
- Пиши на русском языке
- НЕ пиши ничего кроме JSON"""


def build_prompt(context: dict) -> str:
    profession = context.get("profession", "не указана")
    suffix = f" для профессии \"{profession}\"" if profession != "не указана" else ""
    return SYSTEM_PROMPT_TEMPLATE.format(profession=profession, profession_suffix=suffix)

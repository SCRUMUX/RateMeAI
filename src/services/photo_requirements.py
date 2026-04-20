"""Single source of truth for photo requirements and input-quality issue texts.

Shared between:
  - backend pre-flight gate (src/services/input_quality.py)
  - bot /photo_help and rejection messages
  - web frontend (mirrored in web/src/data/photo-requirements.ts — keep in sync)

Machine codes here match the ones used in the frontend TS file.
"""
from __future__ import annotations


class IssueCode:
    """Machine codes for input-quality issues. Keep in sync with web/src/data/photo-requirements.ts."""

    INVALID_IMAGE = "invalid_image"
    LOW_RESOLUTION = "low_resolution"
    BLURRY_PHOTO = "blurry_photo"
    NO_FACE = "no_face"
    FACE_TOO_SMALL = "face_too_small"
    FACE_BLURRED = "face_blurred"
    MULTIPLE_FACES = "multiple_faces"

    # Soft warnings
    FACE_SMALL_WARN = "face_small_warn"
    FACE_OFF_CENTER = "face_off_center"
    NOT_FRONTAL = "not_frontal"
    HAIR_BG_SIMILAR = "hair_bg_similar"


# Russian-language texts for each code.
# Keep short and actionable: user sees these directly on UI/bot.
ISSUE_TEXTS: dict[str, dict[str, str]] = {
    IssueCode.INVALID_IMAGE: {
        "message": "Не удалось открыть изображение.",
        "suggestion": "Загрузите фото в формате JPG или PNG.",
    },
    IssueCode.LOW_RESOLUTION: {
        "message": "Слишком маленькое разрешение фото.",
        "suggestion": "Загрузите фото не меньше 400×400 пикселей.",
    },
    IssueCode.BLURRY_PHOTO: {
        "message": "Фото слишком размыто.",
        "suggestion": "Сделайте чёткий снимок без движения и замыливания.",
    },
    IssueCode.NO_FACE: {
        "message": "На фото не обнаружено лицо.",
        "suggestion": "Загрузите портрет, где лицо хорошо видно.",
    },
    IssueCode.FACE_TOO_SMALL: {
        "message": "Лицо слишком мелкое на фото.",
        "suggestion": "Сделайте кадр крупнее — лицо должно занимать хотя бы 15% кадра.",
    },
    IssueCode.FACE_BLURRED: {
        "message": "Лицо на фото размыто.",
        "suggestion": "Переснимите в фокусе, при хорошем освещении.",
    },
    IssueCode.MULTIPLE_FACES: {
        "message": "На фото несколько человек.",
        "suggestion": "Загрузите портрет одного человека.",
    },
    # Soft warnings
    IssueCode.FACE_SMALL_WARN: {
        "message": "Лицо небольшое — возможна потеря деталей.",
        "suggestion": "Для лучшего результата подойдите ближе к камере.",
    },
    IssueCode.FACE_OFF_CENTER: {
        "message": "Лицо заметно смещено от центра кадра.",
        "suggestion": "Желательно кадрировать так, чтобы лицо было ближе к центру.",
    },
    IssueCode.NOT_FRONTAL: {
        "message": "Лицо повёрнуто от камеры.",
        "suggestion": "Лучший результат — анфас, взгляд прямо в камеру.",
    },
    IssueCode.HAIR_BG_SIMILAR: {
        "message": "Волосы сливаются с фоном.",
        "suggestion": "Для чистого контура выберите фото с простым однотонным фоном.",
    },
}


# ---------------------------------------------------------------------------
# Human-readable bullet lists for UI/bot
# ---------------------------------------------------------------------------

REQUIREMENTS_BULLETS: list[str] = [
    "Лицо крупно и по центру кадра — минимум 15% площади",
    "Анфас, без сильных поворотов головы",
    "Чёткое фото без размытия и движения",
    "Лицо не перекрыто очками-зеркалками, масками, рукой или волосами",
    "Хорошее освещение, черты лица различимы",
    "Один человек в кадре",
]

REJECT_BULLETS: list[str] = [
    "Фото без лица или лицо слишком мелкое",
    "Размытые или шумные фото, в том числе скриншоты",
    "Несколько людей в кадре",
    "Разрешение меньше 400×400 пикселей",
    "Файл больше 10 МБ",
]


def format_requirements_plaintext() -> str:
    """Plain-text bullets list for bot /photo_help."""
    lines = ["*Требования к фото:*"]
    lines.extend(f"• {b}" for b in REQUIREMENTS_BULLETS)
    lines.append("")
    lines.append("*Не будет обработано:*")
    lines.extend(f"• {b}" for b in REJECT_BULLETS)
    return "\n".join(lines)


def short_requirements_block() -> str:
    """Compact block suitable for WELCOME_TEXT in the bot."""
    return (
        "*Требования к фото:*\n"
        "• Лицо крупно и по центру (не меньше 15% кадра)\n"
        "• Чёткий анфас, без масок и очков-зеркалок\n"
        "• Один человек в кадре, разрешение от 400×400\n"
        "\n"
        "/photo\\_help — подробнее"
    )

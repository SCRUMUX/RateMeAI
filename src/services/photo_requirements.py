"""Single source of truth for photo requirements and input-quality issue texts.

Shared between:
  - backend pre-flight gate (src/services/input_quality.py)
  - bot /photo_help and rejection messages
  - web frontend (mirrored in web/src/data/photo-requirements.ts — keep in sync)

Machine codes here match the ones used in the frontend TS file.

1.58.0: issue texts are now keyed by MARKET_ID (``ru`` / ``global``)
so the EN deployment renders English messages instead of the original
Russian copy. The bot, which always operates on the RU edge, keeps
seeing Russian — there is no runtime language switch.
"""

from __future__ import annotations

from typing import Literal

from src.config import settings


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
    FACE_DETECTOR_UNAVAILABLE = "face_detector_unavailable"
    # Emitted only by the bot pre-generation check (style × reference
    # mismatch), not by analyze_input_quality itself — the input metrics
    # alone cannot know which style the user will pick.
    FACE_TOO_TIGHT_FOR_BODY_SHOT = "face_too_tight_for_body_shot"


# Russian-language texts for each code.
# Keep short and actionable: user sees these directly on UI/bot.
_ISSUE_TEXTS_RU: dict[str, dict[str, str]] = {
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
    IssueCode.FACE_DETECTOR_UNAVAILABLE: {
        "message": "Автопроверка лица временно недоступна.",
        "suggestion": "Обработка продолжится — проверка лица пройдёт на этапе сравнения.",
    },
    IssueCode.FACE_TOO_TIGHT_FOR_BODY_SHOT: {
        "message": "Выбранный стиль предполагает видимое тело, а на фото только лицо крупным планом.",
        "suggestion": "Для стабильного результата загрузите фото, где видны плечи и корпус, или выберите портретный стиль.",
    },
}


# English-language texts for the global market deployment.
# Mirrors the Russian set 1:1 by IssueCode key.
_ISSUE_TEXTS_EN: dict[str, dict[str, str]] = {
    IssueCode.INVALID_IMAGE: {
        "message": "We couldn't open this image.",
        "suggestion": "Upload a JPG or PNG photo.",
    },
    IssueCode.LOW_RESOLUTION: {
        "message": "The photo resolution is too low.",
        "suggestion": "Upload a photo at least 400×400 pixels.",
    },
    IssueCode.BLURRY_PHOTO: {
        "message": "The photo is too blurry.",
        "suggestion": "Take a sharp shot — no motion blur or smudging.",
    },
    IssueCode.NO_FACE: {
        "message": "No face detected in the photo.",
        "suggestion": "Upload a portrait where the face is clearly visible.",
    },
    IssueCode.FACE_TOO_SMALL: {
        "message": "The face is too small in the frame.",
        "suggestion": "Crop closer — the face should take at least 15% of the frame.",
    },
    IssueCode.FACE_BLURRED: {
        "message": "The face in the photo is out of focus.",
        "suggestion": "Reshoot in focus, with good lighting.",
    },
    IssueCode.MULTIPLE_FACES: {
        "message": "Multiple people detected in the photo.",
        "suggestion": "Upload a portrait of a single person.",
    },
    IssueCode.FACE_SMALL_WARN: {
        "message": "The face is small — fine details may be lost.",
        "suggestion": "Move closer to the camera for a better result.",
    },
    IssueCode.FACE_OFF_CENTER: {
        "message": "The face is noticeably off-center.",
        "suggestion": "Try to center the face in the frame.",
    },
    IssueCode.NOT_FRONTAL: {
        "message": "The face is turned away from the camera.",
        "suggestion": "Best results come from a frontal pose, looking straight into the lens.",
    },
    IssueCode.HAIR_BG_SIMILAR: {
        "message": "Hair blends into the background.",
        "suggestion": "For a clean outline, pick a photo with a plain, uniform background.",
    },
    IssueCode.FACE_DETECTOR_UNAVAILABLE: {
        "message": "Automatic face check is temporarily unavailable.",
        "suggestion": "We'll keep processing — the face check will happen later in the pipeline.",
    },
    IssueCode.FACE_TOO_TIGHT_FOR_BODY_SHOT: {
        "message": "The chosen style needs a visible body, but the photo is a tight face crop.",
        "suggestion": "Upload a photo with shoulders and torso visible, or pick a portrait style.",
    },
}


_ISSUE_TEXTS_BY_LANG: dict[str, dict[str, dict[str, str]]] = {
    "ru": _ISSUE_TEXTS_RU,
    "en": _ISSUE_TEXTS_EN,
}


def _resolve_lang(market_id: str | None = None) -> Literal["ru", "en"]:
    """Pick RU/EN based on the resolved market id (``ru`` → RU, anything else → EN)."""
    market = (market_id or settings.resolved_market_id or "global").lower()
    if market == "ru":
        return "ru"
    return "en"


def get_issue_texts(market_id: str | None = None) -> dict[str, dict[str, str]]:
    """Return the IssueCode → {message, suggestion} mapping for the active market."""
    return _ISSUE_TEXTS_BY_LANG[_resolve_lang(market_id)]


def get_issue_text(code: str, market_id: str | None = None) -> dict[str, str]:
    """Return the localised entry for a single IssueCode (empty dict if unknown)."""
    return get_issue_texts(market_id).get(code, {})


# Module-level proxy so legacy callers that read ``ISSUE_TEXTS[code]``
# continue to work — each access reads through the active market.
class _IssueTextsProxy(dict[str, dict[str, str]]):
    def __getitem__(self, code: str) -> dict[str, str]:  # type: ignore[override]
        return get_issue_texts()[code]

    def get(self, code: str, default=None):  # type: ignore[override]
        return get_issue_texts().get(code, default)

    def __iter__(self):  # type: ignore[override]
        return iter(get_issue_texts())

    def items(self):  # type: ignore[override]
        return get_issue_texts().items()

    def keys(self):  # type: ignore[override]
        return get_issue_texts().keys()

    def values(self):  # type: ignore[override]
        return get_issue_texts().values()


ISSUE_TEXTS: dict[str, dict[str, str]] = _IssueTextsProxy()


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

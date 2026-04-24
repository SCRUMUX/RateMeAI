"""Style loader from JSON database."""

import json
import os
import logging
from typing import Any

from src.prompts.style_spec import StructuredStyleSpec, StyleType

logger = logging.getLogger(__name__)

_STYLES_CACHE: list[dict[str, Any]] = []


def load_styles_from_json() -> list[dict[str, Any]]:
    """Load styles from data/styles.json."""
    global _STYLES_CACHE
    if _STYLES_CACHE:
        return _STYLES_CACHE

    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "styles.json",
    )
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            _STYLES_CACHE = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load styles from {json_path}: {e}")
        _STYLES_CACHE = []

    return _STYLES_CACHE


def get_structured_specs() -> list[StructuredStyleSpec]:
    """Convert JSON styles to StructuredStyleSpec objects."""
    styles = load_styles_from_json()
    specs = []

    for s in styles:
        try:
            type_val = StyleType(s.get("type", "flexible"))
        except ValueError:
            type_val = StyleType.FLEXIBLE

        from src.prompts.style_spec import _DOCUMENT_STYLE_KEYS, detect_needs_full_body

        is_doc = s["id"] in _DOCUMENT_STYLE_KEYS
        gen_mode = "scene_preserve" if is_doc else "identity_scene"
        aspect = "square_hd" if is_doc else "portrait_4_3"

        # v1.26: раньше мы плющили per-channel dict в плоский список
        # лайтинга + сцены, из-за чего ``VariationEngine`` не мог
        # проверить, какие поля вообще разрешены в стиле, а UI-модалка
        # «Другой вариант» рисовала все поля одинаково для всех стилей.
        # Теперь пробрасываем dict как есть — поля, которых в стиле
        # нет, фронт прячет, а бэкенд игнорирует некорректные значения.
        raw_variations = s.get("allowed_variations", {})
        if isinstance(raw_variations, dict):
            allowed_variations = {
                k: list(v) if isinstance(v, list) else []
                for k, v in raw_variations.items()
            }
        elif isinstance(raw_variations, list):
            # backward-compat для старого плоского формата
            allowed_variations = {"lighting": list(raw_variations)}
        else:
            allowed_variations = {}

        spec = StructuredStyleSpec(
            name=s["id"],
            type=type_val,
            base_scene=s.get("base_scene", ""),
            allowed_variations=allowed_variations,
            camera="",
            pose="",
            clothing=s.get("default_clothing", ""),
            scene=s.get("base_scene", ""),
            lighting="",
            weather="",
            emotion=s.get("expression", ""),
            energy="",
            photo_style="",
            key=s["id"],
            mode=s["mode"],
            needs_full_body=detect_needs_full_body(s["id"], s["mode"]),
            generation_mode=gen_mode,
            output_aspect=aspect,
        )
        specs.append(spec)

    return specs

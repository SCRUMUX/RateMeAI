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

        from src.prompts.image_gen import _DOCUMENT_STYLE_KEYS

        is_doc = s["id"] in _DOCUMENT_STYLE_KEYS
        gen_mode = "scene_preserve" if is_doc else "identity_scene"
        aspect = "square_hd" if is_doc else "portrait_4_3"

        spec = StructuredStyleSpec(
            name=s["id"],
            type=type_val,
            base_scene=s.get("base_scene", ""),
            allowed_variations=s.get("allowed_variations", {}).get("lighting", [])
            + s.get("allowed_variations", {}).get("scene", []),
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
            needs_full_body="yoga" in s["id"]
            or "running" in s["id"]
            or "beach" in s["id"]
            or "hiking" in s["id"],
            generation_mode=gen_mode,
            output_aspect=aspect,
        )
        specs.append(spec)

    return specs

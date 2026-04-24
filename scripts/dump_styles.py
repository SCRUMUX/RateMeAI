import json

from src.prompts.image_gen import STYLE_REGISTRY
from src.services.style_catalog import STYLE_CATALOG


def main():
    styles_data = []

    for mode, catalog_items in STYLE_CATALOG.items():
        for item in catalog_items:
            style_id = item[0]
            display_label = item[1]
            hook_text = item[2]
            meta = item[3] if len(item) > 3 else {}

            spec = STYLE_REGISTRY.get(mode, style_id)
            if not spec:
                continue

            # Convert StructuredStyleSpec to dict
            style_dict = {
                "id": style_id,
                "mode": mode,
                "category": "General",  # Default category, to be updated manually or by script
                "type": spec.type.value if hasattr(spec, "type") else "flexible",
                "base_scene": getattr(
                    spec, "base_scene", getattr(spec, "background", "")
                ),
                "default_clothing": getattr(
                    spec, "clothing", getattr(spec, "clothing_male", "")
                ),
                "expression": getattr(spec, "emotion", getattr(spec, "expression", "")),
                "allowed_variations": (
                    # v1.26: StructuredStyleSpec.allowed_variations теперь
                    # — per-channel dict (lighting/scene/clothing/framing).
                    # Для обратной совместимости поддерживаем и старый
                    # плоский список (мигрирует в "lighting").
                    dict(getattr(spec, "allowed_variations", {}) or {})
                    if isinstance(
                        getattr(spec, "allowed_variations", None), dict
                    )
                    else {
                        "lighting": list(
                            getattr(spec, "allowed_variations", []) or []
                        ),
                        "clothing": [],
                        "framing": ["portrait", "half_body", "full_body"],
                    }
                ),
                "unlock_after_generations": 0,
                "is_scenario_only": False,
                "display_label": display_label,
                "hook_text": hook_text,
                "meta": meta,
            }
            styles_data.append(style_dict)

    with open("data/styles.json", "w", encoding="utf-8") as f:
        json.dump(styles_data, f, ensure_ascii=False, indent=2)

    print(f"Dumped {len(styles_data)} styles to data/styles.json")


if __name__ == "__main__":
    main()

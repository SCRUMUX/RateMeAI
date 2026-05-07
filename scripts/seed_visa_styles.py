"""Seed visa-scenario styles into ``data/styles.json``.

Idempotent. Each visa scenario needs at least one style so that
``/api/v1/catalog/scenario-styles?scenario=<slug>`` returns a
non-empty bucket and the wizard's StepDocumentFormat has something
to show.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STYLES_PATH = REPO_ROOT / "data" / "styles.json"


VISA_STYLES: list[dict[str, object]] = [
    {
        "id": "visa_schengen",
        "mode": "cv",
        "type": "scene_locked",
        "base_scene": "clean uniform white, evenly lit backdrop",
        "default_clothing": "simple solid-color business top",
        "expression": (
            "Neutral composed expression, mouth closed, eyes open and "
            "looking straight into the camera, formal compliant demeanor."
        ),
        "allowed_variations": {
            "lighting": [],
            "clothing": [],
            "framing": ["portrait", "half_body", "full_body"],
        },
        "unlock_after_generations": 0,
        "is_scenario_only": False,
        "display_label": "🛂 Шенген 35×45",
        "hook_text": "35×45 мм, белый фон, голова 32–36 мм",
        "meta": {"param": "trust", "delta_range": [0.02, 0.05]},
        "schema_version": 3,
        "trigger": "visa",
        "background": {
            "base": "clean uniform white, evenly lit backdrop",
            "lock": "locked",
            "overrides_allowed": [],
        },
        "clothing": {
            "default": {
                "male": "simple solid-color business top",
                "female": "simple solid-color business top",
                "neutral": "simple solid-color business top",
            },
            "allowed": [],
            "gender_neutral": True,
        },
        "weather": {"enabled": False, "allowed": [], "default_na": True},
        "context_slots": {"framing": ["portrait", "half_body", "full_body"]},
        "quality_identity": {"base": "", "per_model_tail": {}},
        "scenario": "visa-schengen",
        "trigger_pool": ["clean uniform white, evenly lit backdrop"],
        "scene_anchor": "clean uniform white, evenly lit backdrop",
        "scene_overrides": [],
        "background_lock": "locked",
        "ambient": {
            "lighting": [],
            "weather": [],
            "time_of_day": [],
            "season": [],
        },
        "location_type": "document",
    }
]


def main() -> None:
    raw = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    arr: list[dict] = raw if isinstance(raw, list) else raw.get("styles", [])
    existing_ids = {s.get("id") for s in arr if isinstance(s, dict)}
    added: list[str] = []
    for style in VISA_STYLES:
        sid = str(style["id"])
        if sid in existing_ids:
            continue
        arr.append(style)
        added.append(sid)
    if not added:
        print("nothing to seed — visa styles already present")
        return
    payload = arr if isinstance(raw, list) else {**raw, "styles": arr}
    STYLES_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"seeded {len(added)} visa style(s): {', '.join(added)}")


if __name__ == "__main__":
    main()

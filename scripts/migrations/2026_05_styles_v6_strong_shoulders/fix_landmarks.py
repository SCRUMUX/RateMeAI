"""v1.71 Landmark scene-anchor normalization.

Aligns the 10 remaining ``dating`` landmark styles (``type=scene_locked``,
``background.lock="locked"``) with the working pattern proven by
``legal_finance`` / ``london_eye`` / ``venice_san_marco`` etc.:

* ``background.lock`` → ``"semi"`` (was ``"locked"``)
* ``background_lock`` (v3 mirror) → ``"semi"``
* ``scene_anchor`` — expanded to a concrete, prop-rich description so
  the edit model has enough context to place the body in the scene
  instead of pasting the head onto the reference torso.
* ``scene_overrides`` — populated with 3-4 concrete alternatives so
  the slot-sampler can vary the backdrop frame-to-frame.
* ``background.overrides_allowed`` mirrors ``scene_overrides``.
* ``available_channels`` gets ``"scene_override"`` appended (idempotent).

The ``type=scene_locked`` legacy field is *not* changed: it only
gates the v1 ``variation_engine`` path which never runs the prompt
that the FAL/edit model receives. The runtime path reads
``background.lock``.

Why this matters: ``rome_colosseum`` produced the "glued head"
pathology because its ``scene_anchor`` ("outdoor Roman terrace or
street") was too vague — the model couldn't infer a body-pose
context, so it stitched the reference head onto a randomly-sized
torso. ``legal_finance`` ("wood-panelled office interior, law books
on shelves, soft daylight wash") gives the model a concrete spatial
anchor, so the body is rendered in proportion.

Usage::

    python scripts/migrations/2026_05_styles_v6_strong_shoulders/fix_landmarks.py --dry-run
    python scripts/migrations/2026_05_styles_v6_strong_shoulders/fix_landmarks.py
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
LOG_PATH = Path(__file__).resolve().parent / "LANDMARKS_LOG.md"


# Per-landmark anchor + overrides recipe. Each entry mirrors the
# ``legal_finance`` template: concrete primary scene + 3-4 scene
# variants. Keep the wording first-person observable (props,
# textures, lighting cues — not adjectives).
LANDMARK_RECIPES: dict[str, dict[str, Any]] = {
    "rome_colosseum": {
        "scene_anchor": (
            "outdoor cafe terrace near the Colosseum, weathered "
            "travertine arches in sharp detail behind, cobblestone "
            "street, terracotta planters, warm Mediterranean afternoon light"
        ),
        "scene_overrides": [
            "Via dei Fori Imperiali walkway with Colosseum looming behind, "
            "pedestrian flagstones, Italian cypress trees",
            "Roman piazza with travertine cobblestones, Colosseum silhouette "
            "in the distance, marble fountain in foreground",
            "rooftop terrace in Monti district with Colosseum and Roman skyline behind",
            "cafe table under a striped awning with Colosseum visible across the street, "
            "espresso cup on a marble counter",
        ],
    },
    "paris_eiffel": {
        "scene_anchor": (
            "Haussmann boulevard intersection with the Eiffel Tower "
            "rising behind wrought-iron balconies, zinc rooftops, "
            "warm afternoon Paris light"
        ),
        "scene_overrides": [
            "Trocadero promenade with the Eiffel Tower head-on, stone balustrade, "
            "muted Paris sky",
            "Pont Alexandre III bridge with the Eiffel Tower in the background, "
            "ornate lampposts in frame",
            "Champ-de-Mars lawn with the Eiffel Tower silhouette, gravel pathway, "
            "linden trees on either side",
            "cafe terrace on Rue Cler with rattan chairs, Eiffel Tower spire "
            "visible above the rooftops",
        ],
    },
    "london_big_ben": {
        "scene_anchor": (
            "Westminster embankment with Big Ben tower and Houses of "
            "Parliament in sharp detail behind, Thames railing, "
            "cool grey London sky"
        ),
        "scene_overrides": [
            "Westminster Bridge with Big Ben silhouette and double-decker buses, "
            "ornate cast-iron lamps in frame",
            "St James's Park pathway with Big Ben rising above the trees, "
            "wet gravel path after rain",
            "South Bank promenade looking back at Big Ben across the Thames, "
            "modern railing in foreground",
        ],
    },
    "sf_golden_gate": {
        "scene_anchor": (
            "Crissy Field shoreline with the Golden Gate Bridge towers "
            "rising behind, fog rolling along the headlands, "
            "weathered driftwood, cool Pacific light"
        ),
        "scene_overrides": [
            "Battery Spencer overlook with the Golden Gate Bridge head-on, "
            "rocky bluffs in foreground",
            "Marshall's Beach with the bridge towers above a rocky shoreline, "
            "Pacific waves breaking on sand",
            "Presidio cycling path with the bridge in the background, "
            "Monterey cypress trees framing the view",
        ],
    },
    "athens_acropolis": {
        "scene_anchor": (
            "Plaka district stone steps with the Acropolis and Parthenon "
            "rising on the hilltop behind, whitewashed walls, "
            "bougainvillea climbing a wall, warm Aegean light"
        ),
        "scene_overrides": [
            "Areopagus rock overlook with the Acropolis Parthenon in sharp detail behind, "
            "marble rubble in foreground",
            "Anafiotika village lane with whitewashed houses and the Acropolis silhouette above",
            "Filopappou Hill pathway with pine trees framing the Parthenon view",
        ],
    },
    "sydney_opera": {
        "scene_anchor": (
            "Circular Quay walkway with the Sydney Opera House sails "
            "in sharp detail behind, harbour railing, sparkling water, "
            "bright Australian daylight"
        ),
        "scene_overrides": [
            "Mrs Macquarie's Point lookout with the Opera House and Harbour Bridge in frame, "
            "sandstone bench in foreground",
            "Royal Botanic Garden pathway with the Opera House visible through trees, "
            "warm afternoon light",
            "ferry terminal pier with the Opera House silhouette across the bay, "
            "weathered timber decking",
        ],
    },
    "dubai_burj_khalifa": {
        "scene_anchor": (
            "modern Dubai boulevard with the Burj Khalifa rising behind "
            "glass-and-steel facades, polished marble walkway, "
            "warm desert afternoon light"
        ),
        "scene_overrides": [
            "Dubai Fountain promenade with the Burj Khalifa in sharp detail behind, "
            "reflecting pool in foreground",
            "Souk Al Bahar bridge with the Burj Khalifa silhouette above the lake, "
            "traditional lanterns in frame",
            "Sheikh Zayed Road overlook with the Burj Khalifa towering above the skyline, "
            "glass barrier in foreground",
        ],
    },
    "barcelona_sagrada": {
        "scene_anchor": (
            "Carrer de Mallorca terrace with the Sagrada Familia "
            "spires rising in sharp detail behind, Modernista wrought-iron "
            "railing, warm Mediterranean afternoon light"
        ),
        "scene_overrides": [
            "Plaça de Gaudi pathway with the Sagrada Familia facade in full view, "
            "reflecting pool in foreground",
            "tree-lined Eixample boulevard with the Sagrada Familia spires above "
            "the canopy, mosaic-tiled bench in frame",
            "rooftop terrace in Gracia with the Sagrada Familia silhouette across the skyline",
        ],
    },
    "nyc_brooklyn_bridge": {
        "scene_anchor": (
            "Brooklyn Bridge walkway with stone arches and steel cables "
            "framing the Manhattan skyline behind, weathered timber planks, "
            "warm golden-hour light"
        ),
        "scene_overrides": [
            "Brooklyn Bridge Park promenade with the bridge towers head-on, "
            "Manhattan skyline behind",
            "DUMBO cobblestone street with the Brooklyn Bridge framed between brick warehouses",
            "Empire Fulton Ferry State Park lawn with the bridge crossing overhead, "
            "Manhattan skyline in the background",
        ],
    },
    "tokyo_tower": {
        "scene_anchor": (
            "minimalist Shiba-koen pathway with Tokyo Tower rising in sharp "
            "detail behind, manicured shrubs, polished stone, "
            "cherry-blossom branches in soft focus"
        ),
        "scene_overrides": [
            "Roppongi crossing with Tokyo Tower silhouette above the city skyline, "
            "modern signage in frame",
            "Zojo-ji Temple courtyard with Tokyo Tower behind the tiled rooftops, "
            "stone lanterns in foreground",
            "Azabu street-level view with Tokyo Tower at the end of the road, "
            "narrow walkway, soft evening light",
        ],
    },
}


def _atomic_write(path: Path, payload: str) -> None:
    tmp_dir = path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=tmp_dir, text=False)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _apply_recipe(entry: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": entry.get("id", "<?>"),
        "changed_fields": [],
        "lock_before": (entry.get("background") or {}).get("lock"),
        "lock_after": None,
        "overrides_before": len(
            (entry.get("background") or {}).get("overrides_allowed") or []
        ),
        "overrides_after": 0,
        "anchor_changed": False,
    }

    background = entry.setdefault("background", {})
    overrides_payload = list(recipe["scene_overrides"])

    if background.get("lock") != "semi":
        background["lock"] = "semi"
        record["changed_fields"].append("background.lock")
    record["lock_after"] = background["lock"]

    if background.get("overrides_allowed") != overrides_payload:
        background["overrides_allowed"] = overrides_payload
        record["changed_fields"].append("background.overrides_allowed")

    # v3 schema mirrors.
    if entry.get("background_lock") != "semi":
        entry["background_lock"] = "semi"
        record["changed_fields"].append("background_lock")

    if entry.get("scene_anchor") != recipe["scene_anchor"]:
        entry["scene_anchor"] = recipe["scene_anchor"]
        record["anchor_changed"] = True
        record["changed_fields"].append("scene_anchor")

    if entry.get("scene_overrides") != overrides_payload:
        entry["scene_overrides"] = list(overrides_payload)
        record["changed_fields"].append("scene_overrides")
    record["overrides_after"] = len(entry["scene_overrides"])

    # available_channels — append scene_override if missing.
    channels = entry.setdefault("available_channels", [])
    if "scene_override" not in channels:
        channels.append("scene_override")
        record["changed_fields"].append("available_channels.scene_override")

    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    if not isinstance(styles, list):
        print("ERROR: data/styles.json is not a JSON array.", file=sys.stderr)
        return 2

    records: list[dict[str, Any]] = []
    changed = False
    for entry in styles:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("id", "")
        recipe = LANDMARK_RECIPES.get(sid)
        if not recipe:
            continue
        before = copy.deepcopy(entry)
        record = _apply_recipe(entry, recipe)
        records.append(record)
        if record["changed_fields"]:
            changed = True

    touched = sum(1 for r in records if r["changed_fields"])
    print(
        f"v1.71 landmark normalisation: applied={touched} "
        f"recipes_total={len(LANDMARK_RECIPES)}"
    )

    if not args.dry_run and changed:
        payload = json.dumps(styles, ensure_ascii=False, indent=2) + "\n"
        _atomic_write(STYLES_PATH, payload)
        print(f"Wrote {STYLES_PATH}")

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# v1.71 Landmark scene-anchor normalization",
        "",
        f"- Timestamp: `{timestamp}`",
        f"- Mode: `{'DRY-RUN' if args.dry_run else 'COMMIT'}`",
        f"- Recipes total: {len(LANDMARK_RECIPES)}",
        f"- Applied (changed at least one field): {touched}",
        "",
        "## Per-landmark report",
        "",
        "| id | lock before → after | overrides before → after | anchor changed | fields touched |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(records, key=lambda x: x["id"]):
        lines.append(
            f"| `{r['id']}` | "
            f"{r['lock_before']} → {r['lock_after']} | "
            f"{r['overrides_before']} → {r['overrides_after']} | "
            f"{'yes' if r['anchor_changed'] else 'no'} | "
            f"{', '.join(r['changed_fields']) or '—'} |"
        )
    lines.append("")
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Log written to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

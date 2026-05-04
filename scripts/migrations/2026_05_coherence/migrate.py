"""Apply cross-channel coherence to ``data/styles.json``.

Idempotent — running it twice produces no diff. Two kinds of edits:

1. **Remove winter** from the ``ambient.season`` pool of styles where
   winter is semantically incoherent (yacht, beach, swimming pool,
   sea balcony, tropical singapore). The audit script flagged these.
2. **Add a coherence rule** for outdoor styles where winter is
   plausible but the default clothing is summer-coded. The rule's
   ``clothing_override`` provides a winter-appropriate alternative
   per gender; user pins still win (see :func:`apply_coherence` in
   ``slot_sampler.py``).

Run::

    python -m scripts.migrations.2026_05_coherence.migrate

Output: number of styles modified + a short diff summary on stdout.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Styles where winter is semantically nonsense — remove from season
# pool so the sampler never rolls it.
REMOVE_WINTER_FROM: tuple[str, ...] = (
    "yacht",
    "beach_sunset",
    "swimming_pool",
    "sea_balcony",
    "singapore_marina_bay",  # tropical climate, winter is meaningless
)


# Per-style coherence rules. Each entry maps style id → list of rules
# matching the ``CoherenceRule`` JSON shape:
# ``{"season": str, "clothing_override": {gender: str}, ...}``.
#
# We only override the clothing channel here — lighting/weather
# filters are conservatively left empty to keep first-roll diversity
# (the user can still get neon-lit Times Square in winter if the
# style allows). Authors add filters case by case.
COHERENCE_RULES: dict[str, list[dict[str, Any]]] = {
    # -- Iconic Mediterranean / warm climate landmarks --------------
    "rome_colosseum": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "wool overcoat over fitted sweater, dark trousers, leather boots, refined Italian winter style",
                "female": "wool overcoat over knit dress or sweater with skirt, dark tights, leather boots, refined Italian winter style",
                "neutral": "wool overcoat, knitwear layers, dark trousers, leather boots, refined Italian winter style",
            },
        }
    ],
    "barcelona_sagrada": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "tailored wool coat over knit sweater, dark chinos, leather boots, Mediterranean winter elegance",
                "female": "tailored wool coat over knit dress or layered top, dark trousers or thick tights, leather boots, Mediterranean winter elegance",
                "neutral": "tailored wool coat, knit layers, dark trousers, leather boots, Mediterranean winter elegance",
            },
        }
    ],
    "athens_acropolis": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "fitted wool coat over light sweater, dark trousers, leather boots, classic Mediterranean winter style",
                "female": "fitted wool coat over knit top or dress, dark trousers or tights, leather boots, classic Mediterranean winter style",
                "neutral": "fitted wool coat, knit layers, dark trousers, leather boots, classic Mediterranean winter style",
            },
        }
    ],
    "sydney_opera": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "smart wool jacket over knit sweater, dark chinos, clean leather shoes, mild winter coastal style",
                "female": "smart wool jacket over knit top or dress, dark trousers or thick tights, clean leather flats, mild winter coastal style",
                "neutral": "smart wool jacket, knit layers, dark trousers, leather shoes, mild winter coastal style",
            },
        }
    ],
    "venice_san_marco": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "tailored wool overcoat, fitted scarf, dark trousers, leather boots, refined Italian winter elegance",
                "female": "tailored wool overcoat, fitted scarf over knit dress, dark tights, leather boots, refined Italian winter elegance",
                "neutral": "tailored wool overcoat, scarf, dark trousers, leather boots, refined Italian winter elegance",
            },
        }
    ],
    # -- Northern / temperate landmarks (swap to summer-light) ------
    "london_eye": [
        {
            "season": "summer",
            "clothing_override": {
                "male": "light tailored shirt, fitted chinos, clean leather shoes, smart British summer casual",
                "female": "light blouse or fitted summer dress, tailored trousers or skirt, clean leather flats, smart British summer casual",
                "neutral": "light tailored shirt, fitted trousers, clean leather shoes, smart British summer casual",
            },
        }
    ],
    "london_big_ben": [
        {
            "season": "summer",
            "clothing_override": {
                "male": "light cotton shirt, fitted trousers, clean leather shoes, smart British summer casual",
                "female": "light blouse or summer dress, tailored trousers or skirt, clean leather flats, smart British summer casual",
                "neutral": "light cotton shirt, fitted trousers, clean leather shoes, smart British summer casual",
            },
        }
    ],
    # -- Iconic landmarks with winter season but summer-default
    #    clothing — provide a winter alt
    "paris_eiffel": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "tailored wool coat over fitted sweater, dark trousers, leather boots, refined Parisian winter style",
                "female": "tailored wool coat over knit top or dress, dark tights, leather ankle boots, refined Parisian winter style",
                "neutral": "tailored wool coat, knit layers, dark trousers, leather boots, refined Parisian winter style",
            },
        }
    ],
    "nyc_brooklyn_bridge": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "warm wool coat over knit sweater, dark jeans, leather boots, urban NYC winter style",
                "female": "warm wool coat over knit top, dark jeans or thick tights, leather boots, urban NYC winter style",
                "neutral": "warm wool coat, knit layers, dark jeans, leather boots, urban NYC winter style",
            },
        }
    ],
    "nyc_times_square": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "warm puffer or wool coat, knit sweater, dark jeans, urban boots, NYC winter street style",
                "female": "warm puffer or wool coat, knit top or sweater dress, dark jeans or tights, urban boots, NYC winter street style",
                "neutral": "warm puffer or wool coat, knit layers, dark jeans, urban boots, NYC winter street style",
            },
        }
    ],
    "nyc_central_park": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "warm wool coat or down jacket, knit scarf, dark jeans, leather boots, NYC winter park style",
                "female": "warm wool coat or down jacket, knit scarf, dark jeans or tights, leather boots, NYC winter park style",
                "neutral": "warm wool coat, knit scarf, dark jeans, leather boots, NYC winter park style",
            },
        }
    ],
    "tokyo_tower": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "tailored wool coat over knit sweater, dark trousers, urban leather boots, Tokyo winter street style",
                "female": "tailored wool coat over knit top or dress, dark tights, urban leather boots, Tokyo winter street style",
                "neutral": "tailored wool coat, knit layers, dark trousers, urban leather boots, Tokyo winter street style",
            },
        }
    ],
    "sf_golden_gate": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "warm wool jacket over knit sweater, dark jeans, leather boots, San Francisco winter casual",
                "female": "warm wool jacket over knit top, dark jeans or tights, leather boots, San Francisco winter casual",
                "neutral": "warm wool jacket, knit layers, dark jeans, leather boots, San Francisco winter casual",
            },
        }
    ],
    "dubai_burj_khalifa": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "smart light wool jacket over fitted shirt, dark chinos, polished leather shoes, mild Dubai winter style",
                "female": "smart light wool jacket over fitted top or dress, dark trousers or skirt, polished leather flats, mild Dubai winter style",
                "neutral": "smart light wool jacket, fitted shirt, dark chinos, polished leather shoes, mild Dubai winter style",
            },
        }
    ],
    # -- Outdoor activities -----------------------------------------
    "running": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "thermal long-sleeve running top, fitted running tights, lightweight winter running jacket, running shoes",
                "female": "thermal long-sleeve running top, fitted running leggings, lightweight winter running jacket, running shoes",
                "neutral": "thermal long-sleeve running top, fitted running tights, lightweight winter running jacket, running shoes",
            },
        }
    ],
    "tennis": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "fitted long-sleeve thermal top, training pants, athletic jacket, court trainers",
                "female": "fitted long-sleeve thermal top, training leggings, athletic jacket, court trainers",
                "neutral": "fitted long-sleeve thermal top, training pants, athletic jacket, court trainers",
            },
        }
    ],
    "cycling": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "thermal cycling jersey, fitted winter bib tights, cycling jacket, cycling shoes, gloves",
                "female": "thermal cycling jersey, fitted winter bib tights, cycling jacket, cycling shoes, gloves",
                "neutral": "thermal cycling jersey, fitted winter bib tights, cycling jacket, cycling shoes, gloves",
            },
        }
    ],
    "motorcycle": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "thermal layers under leather riding jacket, riding pants, leather boots, gloves, helmet in hand",
                "female": "thermal layers under leather riding jacket, riding pants, leather boots, gloves, helmet in hand",
                "neutral": "thermal layers under leather riding jacket, riding pants, leather boots, gloves, helmet in hand",
            },
        }
    ],
    "hiking": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "winter hiking shell over fleece, insulated trousers, sturdy hiking boots, beanie",
                "female": "winter hiking shell over fleece, insulated trousers, sturdy hiking boots, beanie",
                "neutral": "winter hiking shell over fleece, insulated trousers, sturdy hiking boots, beanie",
            },
        }
    ],
    # -- Travel + miscellaneous --------------------------------------
    "travel_blogger": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "winter travel jacket over fitted sweater, dark jeans, sturdy boots, beanie or scarf, travel pack accessories",
                "female": "winter travel jacket over fitted sweater, dark jeans or thick tights, sturdy boots, beanie or scarf, travel pack accessories",
                "neutral": "winter travel jacket, knit layers, dark jeans, sturdy boots, beanie or scarf, travel pack accessories",
            },
        }
    ],
    "hotel_breakfast": [
        {
            "season": "winter",
            "clothing_override": {
                "male": "smart layered look, fitted knit sweater over collared shirt, dark trousers, leather shoes",
                "female": "smart layered look, fitted knit top or sweater dress, dark trousers or tights, leather flats",
                "neutral": "smart layered look, fitted knit over collared shirt, dark trousers, leather shoes",
            },
        }
    ],
}


def _diff_seasons(before: list[str], after: list[str]) -> str:
    removed = [s for s in before if s not in after]
    added = [s for s in after if s not in before]
    parts: list[str] = []
    if removed:
        parts.append(f"-[{', '.join(removed)}]")
    if added:
        parts.append(f"+[{', '.join(added)}]")
    return " ".join(parts)


def main() -> None:
    styles: list[dict[str, Any]] = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    by_id = {str(s.get("id") or ""): s for s in styles}

    season_modified: list[str] = []
    coherence_modified: list[str] = []

    for sid in REMOVE_WINTER_FROM:
        spec = by_id.get(sid)
        if spec is None:
            print(f"  warning: {sid} not in styles.json — skipping season cleanup")
            continue
        ambient = spec.setdefault("ambient", {})
        seasons = list(ambient.get("season") or [])
        new_seasons = [s for s in seasons if str(s).strip().lower() != "winter"]
        if new_seasons != seasons:
            ambient["season"] = new_seasons
            season_modified.append(f"{sid}: {_diff_seasons(seasons, new_seasons)}")

    for sid, rules in COHERENCE_RULES.items():
        spec = by_id.get(sid)
        if spec is None:
            print(f"  warning: {sid} not in styles.json — skipping coherence")
            continue
        existing = spec.get("coherence")
        if existing == rules:
            continue  # idempotent — already applied
        spec["coherence"] = deepcopy(rules)
        coherence_modified.append(sid)

    STYLES_PATH.write_text(
        json.dumps(styles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Season pool cleanups ({len(season_modified)}):")
    for line in season_modified:
        print(f"  {line}")
    print()
    print(f"Coherence rules added/updated ({len(coherence_modified)}):")
    for sid in coherence_modified:
        print(f"  {sid}")
    print()
    print(f"styles.json written ({STYLES_PATH})")


if __name__ == "__main__":
    main()

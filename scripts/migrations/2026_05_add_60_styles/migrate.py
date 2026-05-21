"""May 2026 — add 60 non-popsy styles to the catalogue.

20 new styles per mode (``cv`` / ``social`` / ``dating``) that fill
niches the existing catalogue does not cover:

* **CV** — blue-collar / hands-on professions (mechanic, welder,
  firefighter, agronomist, vet, pilot, fisherman, …) plus a couple
  of niche white-collar archetypes (jeweler, luthier, curator,
  barista). The existing CV cohort is white-collar office-only.
* **Social** — non-mainstream hobbies (fly fishing, archery,
  shooting range, mountaineering, kayaking, horseback riding,
  sailing, climbing, paragliding, astrophotography, vintage film
  cameras, chess, vinyl records, calligraphy, pottery, woodcarving,
  beekeeping, homebrewing, falconry, drones).
* **Dating** — Russian cities + natural locations (Red Square,
  Zaryadye, SPb, Kazan, Sochi, Vladivostok, Baikal, Altai, Karelia,
  Kamchatka, Suzdal, Kavkaz, Solovki) plus rare international
  scenery (Norwegian fjord, Iceland, Tuscany, Chefchaouen,
  Patagonia, Provence) — the existing dating catalogue is biased
  toward globalised landmarks (Eiffel / Burj / Times Square / etc).

Each generated entry is a full v3 ``StyleSpecV3``-compatible JSON
object with **all** legacy bookkeeping (``type``, ``base_scene``,
``default_clothing``, ``background``, ``context_slots``,
``weather``, ``clothing``, ``allowed_variations``, ``trigger``,
``display_label``, ``hook_text``, ``meta``, ``unlock_after_generations``,
``is_scenario_only``, ``quality_identity``) so the entry survives
the legacy ``test_styles_v3_data.py`` invariants in addition to
the new v3 lint contract.

Idempotent: any style ``id`` already present in ``data/styles.json``
is skipped (a re-run reports ``added=0``).

Usage::

    python scripts/migrations/2026_05_add_60_styles/migrate.py --dry-run
    python scripts/migrations/2026_05_add_60_styles/migrate.py
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
LOG_PATH = Path(__file__).resolve().parent / "MIGRATION_LOG.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# Curated lighting / time-of-day / weather / season pools that are
# safe across the catalogue. The slot sampler treats each list as a
# uniform draw; values must never share tokens between
# ``ambient.lighting`` and ``ambient.time_of_day`` (pinned by the
# 2026-05 ``tod_lighting_dedup`` invariant).
_OUTDOOR_LIGHTING_DAY = [
    "soft golden",
    "warm afternoon",
    "diffused overcast",
    "soft golden hour",
    "warm afternoon sunlight",
    "diffused overcast daylight",
    "soft morning light",
    "golden hour",
]
_OUTDOOR_LIGHTING_EVENING = [
    "blue hour",
    "blue hour cinematic",
    "warm sunset sidelight",
    "soft amber dusk",
    "low side key light",
]
_OUTDOOR_LIGHTING_HARSH = [
    "harsh midday sun, deep shadows",
    "bright overhead sun, sharp contrast",
]
_OUTDOOR_LIGHTING_FULL = (
    _OUTDOOR_LIGHTING_DAY
    + _OUTDOOR_LIGHTING_EVENING
    + _OUTDOOR_LIGHTING_HARSH
)

_INDOOR_LIGHTING_WORKSHOP = [
    "soft window light from the side",
    "warm tungsten work lamp",
    "diffused overhead daylight",
    "cinematic side key light",
    "warm key light from a desk lamp",
    "neutral fluorescent overhead",
]
_INDOOR_LIGHTING_KITCHEN = [
    "warm key light from overhead pendants",
    "soft window light from the side",
    "warm tungsten interior",
    "diffused overhead daylight",
    "cinematic side key light",
]
_INDOOR_LIGHTING_TECHNICAL = [
    "neutral fluorescent overhead",
    "cool LED panel light",
    "soft window light from the side",
    "cinematic side key light",
    "diffused overhead daylight",
]
_INDOOR_LIGHTING_MUSEUM = [
    "warm spot lighting on exhibits",
    "soft museum gallery lighting",
    "diffused overhead daylight from skylight",
    "cinematic side key light",
]

_TOD_OUTDOOR = ["morning", "afternoon", "early morning", "late afternoon"]
_TOD_OUTDOOR_EVE = ["evening", "twilight", "late afternoon"]
_TOD_OUTDOOR_ALL = [
    "morning", "afternoon", "evening", "early morning",
    "late afternoon", "twilight",
]
_TOD_OUTDOOR_NIGHT = ["evening", "night", "twilight"]
_TOD_INDOOR = ["morning", "afternoon", "late afternoon", "evening"]

_WEATHER_TEMPERATE = [
    "clear",
    "partly cloudy",
    "light overcast",
    "light drizzle",
    "after rain, glistening surfaces",
]
_WEATHER_COLD = [
    "clear winter air",
    "light snow",
    "overcast winter sky",
    "fresh snow on the ground",
]
_WEATHER_MOUNTAIN = [
    "clear alpine air",
    "light haze in the valley",
    "partly cloudy",
    "after rain, glistening surfaces",
]
_WEATHER_COASTAL = [
    "clear",
    "partly cloudy",
    "sea spray and light wind",
    "light overcast",
]

_SEASONS_ALL = ["spring", "summer", "autumn", "winter"]


def _build_style(
    *,
    style_id: str,
    mode: str,
    location_type: str,
    label_ru: str,
    hook_ru: str,
    meta_param: str,
    delta_range: tuple[float, float],
    unlock_after: int,
    scene: str,
    scene_overrides: list[str],
    triggers: list[str],
    clothing_default: str | None = None,
    clothing_m: str | None = None,
    clothing_f: str | None = None,
    clothing_n: str | None = None,
    clothing_allowed: list[str] | None = None,
    lighting_pool: list[str] | None = None,
    weather_pool: list[str] | None = None,
    tod_pool: list[str] | None = None,
    season_pool: list[str] | None = None,
    expression: str = "",
    winter_clothing: dict[str, str] | None = None,
    framing_pool: list[str] | None = None,
    style_type: str = "scene_locked",
) -> dict[str, Any]:
    """Build a single v3 style dict that satisfies both the v3 schema
    loader (``src.services.style_loader_v3._to_v3``) and the legacy
    ``test_styles_v3_data.py`` invariants.

    Caller may pass either a single ``clothing_default`` string (it
    will be replicated across all three gender keys) or any subset of
    gendered overrides.
    """
    if not clothing_default and not (clothing_m or clothing_f or clothing_n):
        raise ValueError(f"{style_id}: clothing is required")

    male = clothing_m or clothing_default or clothing_n or clothing_f or ""
    female = clothing_f or clothing_default or clothing_n or clothing_m or ""
    neutral = clothing_n or clothing_default or clothing_m or clothing_f or ""

    framing = list(framing_pool or ["portrait", "half_body", "full_body"])

    lighting = list(lighting_pool or _OUTDOOR_LIGHTING_FULL)
    weather = list(weather_pool or _WEATHER_TEMPERATE)
    tod = list(tod_pool or _TOD_OUTDOOR)
    season = list(season_pool or _SEASONS_ALL)

    # Indoor styles must not advertise season / weather channels
    # (``INDOOR_SEASON`` / ``INDOOR_WEATHER`` lint errors).
    is_indoor = location_type == "indoor"
    channels = ["lighting", "time_of_day", "framing", "clothing", "scene_override"]
    if not is_indoor:
        channels = [
            "lighting", "weather", "time_of_day", "season",
            "framing", "clothing", "scene_override",
        ]

    coherence: list[dict[str, Any]] = []
    if winter_clothing and not is_indoor:
        coherence.append(
            {
                "season": "winter",
                "clothing_override": {
                    "male": winter_clothing.get("male", male),
                    "female": winter_clothing.get("female", female),
                    "neutral": winter_clothing.get("neutral", neutral),
                },
            },
        )

    allowed = list(clothing_allowed or [])

    # The "context_slots" / "allowed_variations" / "weather" /
    # "background" blocks are legacy v1/v2 — the v3 loader does not
    # read them, but the legacy ``test_styles_v3_data.py`` invariant
    # iterates over every entry and demands they exist.
    background_overrides = list(scene_overrides) or [scene]

    return {
        "id": style_id,
        "mode": mode,
        "type": style_type,
        "base_scene": scene,
        "default_clothing": neutral or male or female,
        "expression": expression,
        "allowed_variations": {
            "lighting": lighting,
            "clothing": [],
            "framing": framing,
        },
        "unlock_after_generations": unlock_after,
        "is_scenario_only": False,
        "display_label": label_ru,
        "hook_text": hook_ru,
        "meta": {
            "param": meta_param,
            "delta_range": list(delta_range),
        },
        "schema_version": 3,
        "trigger": (triggers[0] if triggers else "").split(",")[0][:60],
        "background": {
            "base": scene,
            "lock": "semi",
            "overrides_allowed": background_overrides,
        },
        "clothing": {
            "default": {
                "male": male,
                "female": female,
                "neutral": neutral,
            },
            "allowed": allowed,
            "gender_neutral": (male == female == neutral),
        },
        "weather": {
            "enabled": not is_indoor,
            "allowed": weather if not is_indoor else [],
            "default_na": is_indoor,
        },
        "context_slots": {
            "lighting": lighting,
            "framing": framing,
        },
        "quality_identity": {
            "base": "",
            "per_model_tail": {},
        },
        "trigger_pool": list(triggers),
        "scene_anchor": scene,
        "scene_overrides": list(scene_overrides),
        "background_lock": "semi",
        "ambient": {
            "lighting": lighting,
            "weather": weather if not is_indoor else [],
            "time_of_day": tod,
            "season": season if not is_indoor else [],
        },
        "location_type": location_type,
        "available_channels": channels,
        "coherence": coherence,
    }


# ---------------------------------------------------------------------------
# CV — blue-collar / hands-on professions (20)
# ---------------------------------------------------------------------------

# Each entry below is a fully-fledged style. They share helper
# constants where it makes sense to keep the file scannable.

_CV_STYLES: list[dict[str, Any]] = [
    _build_style(
        style_id="construction_foreman",
        mode="cv",
        location_type="outdoor",
        label_ru="👷 Прораб на стройке",
        hook_ru="Каска и чертежи — сразу видно человека дела",
        meta_param="trust",
        delta_range=(0.20, 0.40),
        unlock_after=2,
        scene=(
            "active construction site with tower crane in the background, "
            "concrete formwork visible, safety perimeter, daylight"
        ),
        scene_overrides=[
            "construction site with steel rebar grid in the background, "
            "tower crane visible, hardhat workers around",
            "construction site office trailer in the background, "
            "rolled blueprints on a folding table in foreground",
            "rooftop construction zone with city skyline in the background, "
            "scaffolding visible, polished concrete floor in foreground",
        ],
        triggers=[
            "tower crane rising in the background",
            "construction site with rebar grid behind",
            "scaffolding and formwork in the background",
            "construction blueprints spread on a folding table",
        ],
        clothing_default=(
            "high-visibility orange safety vest over a fitted work shirt, "
            "rugged work trousers, sturdy work boots, white safety hardhat, "
            "well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted soft-shell jacket over a work shirt, cargo trousers, work boots, hardhat",
            "navy work polo over base layer, rugged trousers, work boots, hardhat",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + ["harsh midday sun, deep shadows"],
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Composed confident gaze, calm authority, steady professional smile."
        ),
        winter_clothing={
            "male": (
                "insulated high-visibility work jacket over a fleece layer, "
                "insulated work trousers, winter work boots, hardhat over a beanie"
            ),
            "female": (
                "insulated high-visibility work jacket over a fleece layer, "
                "insulated work trousers, winter work boots, hardhat over a beanie"
            ),
            "neutral": (
                "insulated high-visibility work jacket over a fleece layer, "
                "insulated work trousers, winter work boots, hardhat over a beanie"
            ),
        },
    ),
    _build_style(
        style_id="chef_pro_kitchen",
        mode="cv",
        location_type="indoor",
        label_ru="👨‍🍳 Шеф-повар",
        hook_ru="Атмосфера профессиональной кухни усиливает экспертность",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "professional restaurant kitchen with stainless steel surfaces, "
            "copper pots hanging in the background, open flame on a gas range, "
            "warm pendant glow overhead"
        ),
        scene_overrides=[
            "professional kitchen pass with plated dishes in foreground, "
            "stainless steel tickets rail in the background",
            "open kitchen line with copper pots in the background, "
            "wooden cutting board in foreground, daylight from a tall window",
            "restaurant kitchen with white tiled wall in the background, "
            "stainless steel work bench in foreground, warm overhead lighting",
        ],
        triggers=[
            "copper pots hanging in the background",
            "restaurant kitchen line behind",
            "stainless steel pass with plated dishes in foreground",
            "open flame on a gas range in the background",
        ],
        clothing_default=(
            "white professional chef jacket with neat lapel, fitted clean apron, "
            "well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "navy chef jacket with rolled sleeves, fitted clean apron",
            "fitted black chef coat, neat collar, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_KITCHEN,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Focused engaged gaze, confident professional smile, calm composed eyes."
        ),
    ),
    _build_style(
        style_id="auto_mechanic",
        mode="cv",
        location_type="indoor",
        label_ru="🔧 Автомеханик",
        hook_ru="Гараж с поднятым авто — про реальную профессию",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "professional auto repair garage with a car raised on a hydraulic lift "
            "in the background, rolling tool chest in foreground, polished concrete "
            "floor, neutral overhead glow"
        ),
        scene_overrides=[
            "auto garage with engine bay open on a lift in the background, "
            "tool board on the wall, polished concrete floor in foreground",
            "auto shop bay with workbench and pegboard in the background, "
            "rolling tool chest in foreground, daylight from a roll-up door",
            "performance garage with vintage car in the background, "
            "polished concrete floor in foreground, warm tungsten work lamp",
        ],
        triggers=[
            "car raised on a hydraulic lift behind",
            "rolling tool chest in the foreground",
            "tool board on the garage wall behind",
            "vintage car in the garage in the background",
        ],
        clothing_default=(
            "navy mechanic coveralls or fitted work shirt with rolled sleeves, "
            "dark trousers, work boots, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted denim work shirt, dark trousers, work boots",
            "navy mechanic jumpsuit, neat work boots",
        ],
        lighting_pool=_INDOOR_LIGHTING_TECHNICAL,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Steady focused gaze, calm professional smile, confident composed eyes."
        ),
    ),
    _build_style(
        style_id="firefighter_station",
        mode="cv",
        location_type="indoor",
        label_ru="🚒 Пожарный",
        hook_ru="Депо и форма — сила и ответственность в кадре",
        meta_param="trust",
        delta_range=(0.30, 0.50),
        unlock_after=2,
        scene=(
            "fire station apparatus bay with a red fire engine in the background, "
            "polished concrete floor in foreground, neat gear lockers along the wall, "
            "daylight from a tall roll-up door"
        ),
        scene_overrides=[
            "fire station bay with hose reel station in the background, "
            "polished concrete floor in foreground",
            "fire station bay with bunker gear hanging in lockers in the background, "
            "red fire engine partially in frame, daylight from a side bay door",
            "fire station hallway with the apparatus bay visible in the background, "
            "polished floor in foreground, warm overhead lighting",
        ],
        triggers=[
            "red fire engine parked in the apparatus bay behind",
            "bunker gear hanging in lockers behind",
            "fire station bay door with daylight pouring in",
            "hose reel station in the background",
        ],
        clothing_default=(
            "navy firefighter duty uniform shirt with neat patches, "
            "tucked into work trousers, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted firefighter polo with patches, dark trousers, work boots",
            "navy duty uniform with collar pins, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_TECHNICAL,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Composed steady gaze, calm grounded presence, subtle confident smile."
        ),
    ),
    _build_style(
        style_id="electrician_panel",
        mode="cv",
        location_type="indoor",
        label_ru="⚡ Электромонтёр",
        hook_ru="Щит и приборы — техническая компетентность",
        meta_param="trust",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "industrial electrical room with an opened distribution panel in the "
            "background, neat cable tray on the wall, polished concrete floor in "
            "foreground, neutral overhead glow"
        ),
        scene_overrides=[
            "electrical room with switchgear cabinets in the background, "
            "polished concrete floor in foreground",
            "electrical workshop with cable spools in the background, "
            "polished floor in foreground, neutral overhead light",
            "control room with electrical schematics on the wall in the background, "
            "polished floor in foreground",
        ],
        triggers=[
            "opened distribution panel in the background",
            "switchgear cabinets behind",
            "cable tray running along the wall behind",
            "electrical schematics on the wall behind",
        ],
        clothing_default=(
            "fitted electrician work shirt with company patches, dark work trousers, "
            "work boots, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "navy electrician polo with patches, dark trousers",
            "fitted technical jacket over a work shirt, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_TECHNICAL,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Focused confident gaze, calm professional smile, attentive technical eyes."
        ),
    ),
    _build_style(
        style_id="carpenter_workshop",
        mode="cv",
        location_type="indoor",
        label_ru="🪚 Столяр",
        hook_ru="Запах дерева в столярной мастерской — про мастера",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "professional woodworking workshop with a long workbench in foreground, "
            "neat tool wall in the background, wood shavings on the bench, daylight "
            "from a side window"
        ),
        scene_overrides=[
            "carpentry workshop with stacked timber in the background, "
            "long workbench in foreground, daylight from a tall window",
            "joinery workshop with planer and band saw in the background, "
            "polished wooden floor in foreground",
            "carpenter's bench with hand planes in foreground, "
            "tool wall in the background, warm tungsten work lamp",
        ],
        triggers=[
            "long workbench with hand planes in foreground",
            "tool wall in the workshop behind",
            "stacked timber in the workshop behind",
            "planer and band saw in the workshop behind",
        ],
        clothing_default=(
            "fitted denim work shirt with rolled sleeves, sturdy canvas apron, "
            "dark trousers, work boots, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "navy work shirt with canvas apron, dark trousers",
            "fitted flannel shirt over a tee, canvas apron, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_WORKSHOP,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Calm focused gaze, warm confident smile, steady artisan eyes."
        ),
    ),
    _build_style(
        style_id="scientist_lab",
        mode="cv",
        location_type="indoor",
        label_ru="🔬 Учёный",
        hook_ru="Лаборатория с реактивами — академическая компетентность",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "research laboratory with white fume hood in the background, "
            "stainless steel bench in foreground, microscope and glassware visible, "
            "diffused overhead daylight"
        ),
        scene_overrides=[
            "laboratory bench with microscope in foreground, glassware shelving "
            "in the background, neutral fluorescent lighting",
            "research lab with computer monitors showing data in the background, "
            "stainless steel bench in foreground",
            "biology lab with centrifuge and reagent shelves in the background, "
            "polished floor in foreground, daylight from a side window",
        ],
        triggers=[
            "fume hood in the laboratory background",
            "microscope on the lab bench in foreground",
            "glassware shelving in the lab background",
            "centrifuge and reagent shelves in the lab background",
        ],
        clothing_default=(
            "clean white lab coat over a fitted shirt, neutral trousers, "
            "well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted lab coat over a turtleneck, dark trousers",
            "lab coat over a neat blouse, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_TECHNICAL,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Curious thoughtful gaze, subtle confident smile, calm academic eyes."
        ),
    ),
    _build_style(
        style_id="factory_engineer",
        mode="cv",
        location_type="indoor",
        label_ru="🏭 Инженер на заводе",
        hook_ru="Цех в кадре — про реальное производство",
        meta_param="trust",
        delta_range=(0.20, 0.40),
        unlock_after=2,
        scene=(
            "industrial production floor with conveyor lines in the background, "
            "polished concrete floor in foreground, neutral overhead glow, "
            "engineer's clipboard in hand"
        ),
        scene_overrides=[
            "production floor with CNC machines in the background, "
            "polished concrete floor in foreground",
            "factory walkway with assembly line in the background, "
            "engineering schematics on a stand in foreground",
            "metalworking shop with steel parts on a workbench in foreground, "
            "lathes in the background, neutral overhead light",
        ],
        triggers=[
            "conveyor lines in the factory background",
            "CNC machines on the production floor behind",
            "assembly line in the factory background",
            "lathes in the metalworking shop behind",
        ],
        clothing_default=(
            "navy soft-shell engineering jacket over a fitted shirt, "
            "dark trousers, safety boots, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted engineering polo with company patches, dark trousers",
            "navy work jacket over a turtleneck, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_TECHNICAL,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Composed analytical gaze, calm confident smile, steady professional eyes."
        ),
    ),
    _build_style(
        style_id="agronomist_field",
        mode="cv",
        location_type="outdoor",
        label_ru="🌾 Агроном в поле",
        hook_ru="Бескрайнее поле — про реальное сельское хозяйство",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=2,
        scene=(
            "vast cultivated field stretching to the horizon, narrow dirt road "
            "in foreground, rugged off-road vehicle parked at the edge, "
            "wide rural sky"
        ),
        scene_overrides=[
            "wheat field at the edge of harvest in the background, "
            "dirt road and rugged vehicle in foreground, wide rural sky",
            "sunflower field stretching to the horizon, dirt path in foreground, "
            "off-road vehicle with open hood",
            "cornfield with a tractor in the background, "
            "rolled crop maps spread on a vehicle bonnet in foreground",
        ],
        triggers=[
            "wheat field stretching to the horizon",
            "sunflower field with horizon behind",
            "cornfield with a tractor in the background",
            "rolled crop maps on a vehicle bonnet in foreground",
        ],
        clothing_default=(
            "fitted technical work shirt with rolled sleeves, sturdy trousers, "
            "hiking boots, light field cap, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "soft-shell field jacket over a shirt, sturdy trousers, hiking boots",
            "navy work polo over base layer, sturdy trousers, field cap",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm thoughtful gaze, warm professional smile, steady rural eyes."
        ),
        winter_clothing={
            "male": (
                "insulated field jacket over a fleece layer, sturdy trousers, "
                "winter hiking boots, knit beanie"
            ),
            "female": (
                "insulated field jacket over a fleece layer, sturdy trousers, "
                "winter hiking boots, knit beanie"
            ),
            "neutral": (
                "insulated field jacket over a fleece layer, sturdy trousers, "
                "winter hiking boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="veterinarian_clinic",
        mode="cv",
        location_type="indoor",
        label_ru="🐕 Ветеринар",
        hook_ru="Светлая клиника — про эмпатию и заботу",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=1,
        scene=(
            "bright veterinary clinic examination room with a clean exam table in "
            "foreground, medical cabinet in the background, friendly dog in frame, "
            "soft diffused daylight"
        ),
        scene_overrides=[
            "veterinary clinic room with a friendly cat on the exam table in "
            "foreground, medical posters on the back wall",
            "vet clinic exam room with diagnostic equipment cart in the background, "
            "clean exam table in foreground, daylight from a side window",
            "small animal clinic with a wagging dog in foreground, "
            "neat cabinets in the background, warm overhead lighting",
        ],
        triggers=[
            "friendly dog on the veterinary exam table",
            "friendly cat on the veterinary exam table",
            "medical cabinet in the veterinary clinic background",
            "diagnostic equipment cart in the clinic background",
        ],
        clothing_default=(
            "fitted clean veterinary scrubs top with neat collar, dark trousers, "
            "well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "navy scrubs top with stethoscope around the neck, dark trousers",
            "fitted scrubs top under a clean white lab coat, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_TECHNICAL,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Warm caring gaze, gentle reassuring smile, calm attentive eyes."
        ),
    ),
    _build_style(
        style_id="paramedic_ambulance",
        mode="cv",
        location_type="outdoor",
        label_ru="🚑 Фельдшер скорой",
        hook_ru="У машины скорой — про готовность помогать",
        meta_param="trust",
        delta_range=(0.30, 0.50),
        unlock_after=2,
        scene=(
            "ambulance parked at a quiet city street, side door open in the "
            "background, asphalt road in foreground, daylight from the side"
        ),
        scene_overrides=[
            "ambulance bay at a hospital with the vehicle in the background, "
            "polished concrete driveway in foreground",
            "ambulance parked at a roadside layby in the background, "
            "asphalt road in foreground, soft morning light",
            "ambulance with red cross livery in the background, "
            "open side compartment visible, urban backdrop",
        ],
        triggers=[
            "ambulance with side door open behind",
            "ambulance bay at a hospital behind",
            "ambulance with red cross livery behind",
            "ambulance parked at a roadside layby behind",
        ],
        clothing_default=(
            "fitted high-visibility paramedic uniform jacket with neat patches, "
            "dark duty trousers, work boots, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "navy paramedic polo with patches, dark duty trousers",
            "fitted soft-shell duty jacket over a work shirt, dark trousers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR_ALL,
        expression=(
            "Calm focused gaze, composed reassuring smile, steady professional eyes."
        ),
        winter_clothing={
            "male": (
                "insulated paramedic duty jacket with reflective trim, "
                "dark duty trousers, winter boots"
            ),
            "female": (
                "insulated paramedic duty jacket with reflective trim, "
                "dark duty trousers, winter boots"
            ),
            "neutral": (
                "insulated paramedic duty jacket with reflective trim, "
                "dark duty trousers, winter boots"
            ),
        },
    ),
    _build_style(
        style_id="airline_pilot_cockpit",
        mode="cv",
        location_type="indoor",
        label_ru="✈️ Пилот в кабине",
        hook_ru="Кабина самолёта — про уверенность и контроль",
        meta_param="presence",
        delta_range=(0.30, 0.50),
        unlock_after=3,
        scene=(
            "modern airliner cockpit with instrument panel in the background, "
            "side window with daylight, captain's seat in foreground, calm "
            "professional atmosphere"
        ),
        scene_overrides=[
            "airliner cockpit with overhead panel in the background, "
            "instrument cluster visible, daylight from the side window",
            "flight deck with multi-function displays in the background, "
            "captain's seat in foreground, soft cabin light",
            "cockpit jump seat view with the captain's controls in foreground, "
            "windshield with sky in the background",
        ],
        triggers=[
            "modern airliner instrument panel behind",
            "airliner overhead cockpit panel behind",
            "cockpit windshield with sky visible behind",
            "flight deck multi-function displays behind",
        ],
        clothing_default=(
            "professional airline pilot uniform shirt with neat epaulettes, "
            "captain's tie, dark uniform trousers, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted pilot uniform jacket with neat epaulettes, dark trousers",
            "pilot uniform shirt with neat tie and epaulettes, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_TECHNICAL,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Composed confident gaze, calm assured smile, steady professional eyes."
        ),
    ),
    _build_style(
        style_id="train_driver_platform",
        mode="cv",
        location_type="outdoor",
        label_ru="🚆 Машинист поезда",
        hook_ru="Локомотив на платформе — настоящая профессия",
        meta_param="trust",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "railway platform with a long-distance locomotive in the background, "
            "polished platform tiles in foreground, station canopy overhead, "
            "soft morning light"
        ),
        scene_overrides=[
            "railway platform with a sleek high-speed train in the background, "
            "polished platform tiles in foreground, daylight from a side canopy",
            "railway depot with several locomotives in the background, "
            "polished concrete platform in foreground",
            "train cab access door visible behind, polished platform in foreground, "
            "morning daylight",
        ],
        triggers=[
            "long-distance locomotive at the platform behind",
            "sleek high-speed train at the platform behind",
            "railway depot with locomotives behind",
            "train cab access door behind",
        ],
        clothing_default=(
            "fitted railway driver uniform jacket with neat insignia, "
            "service cap, dark trousers, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "navy railway driver shirt with epaulettes, dark trousers, service cap",
            "fitted soft-shell railway jacket over a shirt, dark trousers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + ["soft morning light"],
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm focused gaze, professional steady smile, attentive eyes."
        ),
        winter_clothing={
            "male": (
                "insulated railway driver jacket over a uniform shirt, "
                "dark trousers, winter boots, service cap"
            ),
            "female": (
                "insulated railway driver jacket over a uniform shirt, "
                "dark trousers, winter boots, service cap"
            ),
            "neutral": (
                "insulated railway driver jacket over a uniform shirt, "
                "dark trousers, winter boots, service cap"
            ),
        },
    ),
    _build_style(
        style_id="fisherman_harbor",
        mode="cv",
        location_type="outdoor",
        label_ru="🎣 Рыбак у причала",
        hook_ru="Гавань и сети — характер и приключение",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "small fishing harbor in the early hours, wooden pier in foreground, "
            "fishing nets stacked along the railing, weathered boats in the background, "
            "soft coastal light"
        ),
        scene_overrides=[
            "harbor pier with rope coils in foreground, fishing trawler in the "
            "background, soft morning coastal light",
            "stone quay with seagulls in the background, fishing nets on a rack "
            "in foreground, low side key light",
            "old fishing village harbor at dusk, lanterns on the pier in foreground, "
            "boats moored in the background",
        ],
        triggers=[
            "fishing nets stacked along the harbor railing",
            "weathered fishing boats moored in the harbor behind",
            "fishing trawler in the harbor behind",
            "harbor lanterns on the pier in foreground",
        ],
        clothing_default=(
            "thick fisherman knit sweater, weatherproof bib trousers, sturdy boots, "
            "knit cap, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted waxed jacket over a thick sweater, rugged trousers, sturdy boots",
            "navy fisherman sweater over a base layer, weatherproof trousers, boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_COASTAL,
        tod_pool=_TOD_OUTDOOR_ALL,
        expression=(
            "Calm weathered gaze, warm steady smile, attentive seafarer eyes."
        ),
        winter_clothing={
            "male": (
                "heavy fisherman knit sweater under a waxed weatherproof jacket, "
                "insulated bib trousers, winter boots, knit cap"
            ),
            "female": (
                "heavy fisherman knit sweater under a waxed weatherproof jacket, "
                "insulated bib trousers, winter boots, knit cap"
            ),
            "neutral": (
                "heavy fisherman knit sweater under a waxed weatherproof jacket, "
                "insulated bib trousers, winter boots, knit cap"
            ),
        },
    ),
    _build_style(
        style_id="forester_taiga",
        mode="cv",
        location_type="outdoor",
        label_ru="🌲 Лесник в тайге",
        hook_ru="Сосны и тропа — про спокойную силу",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "northern taiga forest with tall pines stretching into the depth, "
            "narrow forest trail in foreground, mossy ground, soft morning light "
            "filtering through the trees"
        ),
        scene_overrides=[
            "taiga forest with a felled log on the trail in foreground, pines in "
            "the background, soft morning light",
            "forest road through tall pines in the background, rugged off-road "
            "vehicle parked at the side in foreground",
            "ranger station at the edge of the taiga in the background, wooden "
            "porch in foreground, soft daylight",
        ],
        triggers=[
            "tall pines stretching into the depth of the taiga",
            "felled log on the forest trail in foreground",
            "forest road through tall pines behind",
            "ranger station at the edge of the taiga behind",
        ],
        clothing_default=(
            "olive forester jacket over a fitted shirt, sturdy trousers, hiking boots, "
            "wide-brim field hat, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted soft-shell jacket over a flannel shirt, sturdy trousers, boots",
            "navy forester polo over base layer, sturdy trousers, hiking boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_TEMPERATE + ["light fog through the pines"],
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm grounded gaze, warm understated smile, attentive woodsman eyes."
        ),
        winter_clothing={
            "male": (
                "insulated olive forester jacket over a fleece layer, sturdy trousers, "
                "winter hiking boots, knit beanie"
            ),
            "female": (
                "insulated olive forester jacket over a fleece layer, sturdy trousers, "
                "winter hiking boots, knit beanie"
            ),
            "neutral": (
                "insulated olive forester jacket over a fleece layer, sturdy trousers, "
                "winter hiking boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="welder_industrial",
        mode="cv",
        location_type="indoor",
        label_ru="🛠 Сварщик",
        hook_ru="Искры и металл — про ремесло и силу",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "industrial welding workshop with a steel frame on a workbench in "
            "foreground, sparks fading in the background, polished concrete floor, "
            "warm tungsten work lamp from the side"
        ),
        scene_overrides=[
            "welding bay with steel construction in the background, polished "
            "concrete floor in foreground, neutral overhead light",
            "metalworking shop with welding curtains in the background, steel "
            "parts on a workbench in foreground, side key light",
            "fabrication shop with a steel frame in foreground, gas cylinders in "
            "the background, warm tungsten lamp",
        ],
        triggers=[
            "steel frame on the welding workbench in foreground",
            "welding curtains in the metalworking shop behind",
            "gas cylinders in the fabrication shop behind",
            "steel construction in the welding bay behind",
        ],
        clothing_default=(
            "heavy-duty welder jacket over a fitted work shirt, leather welding apron, "
            "dark trousers, work boots, welding mask lifted onto the head, "
            "well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted welder coveralls, leather apron, work boots",
            "heavy work shirt under a leather apron, dark trousers, work boots",
        ],
        lighting_pool=_INDOOR_LIGHTING_WORKSHOP,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Focused intense gaze, steady professional smile, calm artisan eyes."
        ),
    ),
    _build_style(
        style_id="jeweler_bench",
        mode="cv",
        location_type="indoor",
        label_ru="💍 Ювелир",
        hook_ru="Тонкие инструменты — про точность и вкус",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "jeweler's workshop bench with magnifying loupe in foreground, "
            "neat row of fine tools in the background, polished wooden surface, "
            "warm focused desk light"
        ),
        scene_overrides=[
            "jewelry workshop with a velvet display tray in foreground, tool wall "
            "in the background, warm desk lamp",
            "watchmaker's bench with tiny tools in foreground, wooden cabinets in "
            "the background, soft window light",
            "goldsmith's bench with a polishing wheel in the background, polished "
            "wooden surface in foreground, warm key light",
        ],
        triggers=[
            "magnifying loupe on the jeweler's bench in foreground",
            "velvet display tray on the jewelry workshop bench in foreground",
            "polishing wheel in the goldsmith workshop behind",
            "tiny tools on the watchmaker's bench in foreground",
        ],
        clothing_default=(
            "fitted dark vest over a crisp shirt, neat tie or cravat, fine wool "
            "trousers, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted black turtleneck under a tailored jacket, dark trousers",
            "fitted dark shirt with rolled sleeves, fine wool trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_WORKSHOP,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Calm precise gaze, subtle confident smile, attentive artisan eyes."
        ),
    ),
    _build_style(
        style_id="barista_specialty",
        mode="cv",
        location_type="indoor",
        label_ru="☕ Бариста",
        hook_ru="Кофейня и эспрессо-машина — про стиль и характер",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "specialty coffee bar interior with espresso machine in the background, "
            "wooden counter in foreground, neat row of cups, warm pendant glow"
        ),
        scene_overrides=[
            "specialty coffee bar with grinder and espresso machine in the "
            "background, wooden counter in foreground",
            "third-wave cafe interior with brew bar in the background, polished "
            "concrete floor in foreground, daylight from a tall window",
            "coffee shop with chalkboard menu in the background, wooden counter "
            "in foreground, warm overhead lighting",
        ],
        triggers=[
            "espresso machine on the coffee bar behind",
            "brew bar with V60 drippers in the cafe behind",
            "chalkboard menu in the coffee shop behind",
            "wooden coffee bar counter in foreground",
        ],
        clothing_default=(
            "fitted dark tee under a clean canvas barista apron, dark trousers, "
            "well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted denim shirt under a canvas apron, dark trousers",
            "fitted heather grey tee under a leather apron, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_KITCHEN,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Warm engaged gaze, friendly confident smile, attentive hospitality eyes."
        ),
    ),
    _build_style(
        style_id="luthier_workshop",
        mode="cv",
        location_type="indoor",
        label_ru="🎻 Мастер скрипок",
        hook_ru="Мастерская со скрипками — про утончённое ремесло",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=2,
        scene=(
            "luthier's workshop with a violin on a workbench in foreground, "
            "stringed instruments hanging on the back wall, neat hand tools on a "
            "shelf, warm side window light"
        ),
        scene_overrides=[
            "luthier workshop with cello body in foreground, violins hanging in "
            "the background, soft window light",
            "violin maker's bench with planes and chisels in foreground, "
            "instrument shells in the background, warm tungsten lamp",
            "stringed instrument workshop with rosin and varnish jars on a shelf "
            "in the background, polished wooden bench in foreground",
        ],
        triggers=[
            "violin on the luthier's workbench in foreground",
            "cello body on the workbench in foreground",
            "stringed instruments hanging on the workshop wall behind",
            "rosin and varnish jars on the workshop shelf behind",
        ],
        clothing_default=(
            "fitted denim shirt under a clean canvas apron, dark trousers, "
            "well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted flannel shirt under a canvas apron, dark trousers",
            "fitted dark shirt with rolled sleeves under a leather apron, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_WORKSHOP,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Calm patient gaze, subtle warm smile, attentive artisan eyes."
        ),
    ),
    _build_style(
        style_id="museum_curator",
        mode="cv",
        location_type="indoor",
        label_ru="🏛 Куратор музея",
        hook_ru="Музейный зал — про эрудицию и вкус",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "classical museum gallery with framed paintings on a deep wall in the "
            "background, polished parquet floor in foreground, soft museum spot "
            "light"
        ),
        scene_overrides=[
            "modern art museum gallery with a large abstract canvas in the "
            "background, polished concrete floor in foreground, warm gallery light",
            "sculpture hall with marble busts on plinths in the background, "
            "polished stone floor in foreground, diffused daylight from a skylight",
            "museum library with tall bookshelves in the background, polished "
            "parquet floor in foreground, warm reading lamps",
        ],
        triggers=[
            "framed paintings on the museum gallery wall behind",
            "large abstract canvas in the museum gallery behind",
            "marble busts on plinths in the sculpture hall behind",
            "tall bookshelves in the museum library behind",
        ],
        clothing_default=(
            "fitted dark blazer over a turtleneck, neat tailored trousers, "
            "minimal silver glasses, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted blazer over a crisp shirt, tailored trousers",
            "fitted dark turtleneck under a tailored jacket, fine wool trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_MUSEUM,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Thoughtful refined gaze, subtle knowing smile, attentive cultured eyes."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Social — niche hobbies (20)
# ---------------------------------------------------------------------------

_SOCIAL_STYLES: list[dict[str, Any]] = [
    _build_style(
        style_id="fly_fishing_river",
        mode="social",
        location_type="outdoor",
        label_ru="🎣 Нахлыст на горной реке",
        hook_ru="Горная река и нахлыст — про азарт и спокойствие",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "mountain river bend with clear water flowing over rounded stones, "
            "wooded slopes in the background, gravel bank in foreground, soft "
            "morning light"
        ),
        scene_overrides=[
            "mountain stream with mossy boulders in foreground, pine slopes in "
            "the background, soft morning light",
            "river bend with riffles in foreground, wooded ridge in the background, "
            "diffused overcast daylight",
            "alpine river with snow patches on the bank in foreground, fir trees "
            "in the background, soft side light",
        ],
        triggers=[
            "fly fishing rod arching over the river",
            "clear mountain river flowing over rounded stones",
            "wooded slopes along the river in the background",
            "fly fisherman's vest with rows of flies on the chest",
        ],
        clothing_default=(
            "fitted fly-fishing vest with rows of flies, soft technical shirt with "
            "rolled sleeves, chest-high waders, wading boots, brimmed hat, "
            "well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "soft technical shirt under a fishing vest, waders, brimmed hat",
            "fitted fleece under a fishing vest, waders, wading boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_MOUNTAIN,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Focused calm gaze, subtle satisfied smile, attentive outdoorsman eyes."
        ),
        winter_clothing={
            "male": (
                "insulated fishing vest over a thermal layer, neoprene waders, "
                "winter wading boots, knit beanie"
            ),
            "female": (
                "insulated fishing vest over a thermal layer, neoprene waders, "
                "winter wading boots, knit beanie"
            ),
            "neutral": (
                "insulated fishing vest over a thermal layer, neoprene waders, "
                "winter wading boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="archery_range",
        mode="social",
        location_type="outdoor",
        label_ru="🏹 Стрельба из лука",
        hook_ru="Натянутая тетива — про сосредоточенность",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "outdoor archery range with target butts in the background, mowed grass "
            "lane in foreground, soft afternoon light, neat shooting line markers"
        ),
        scene_overrides=[
            "field archery range with 3D animal targets along a forest edge in the "
            "background, grass lane in foreground",
            "Olympic-style archery range with paper targets in the background, "
            "mowed lane in foreground, diffused overcast daylight",
            "traditional archery field with hay-bale targets in the background, "
            "grass lane in foreground, soft golden hour",
        ],
        triggers=[
            "archery target butts at the end of the lane",
            "3D animal target along the forest edge",
            "paper archery target in the background",
            "recurve bow drawn with arrow nocked",
        ],
        clothing_default=(
            "fitted technical archery polo over base layer, arm guard on the bow "
            "arm, finger tab, cargo trousers, sport shoes, well-fitted across the "
            "shoulders"
        ),
        clothing_allowed=[
            "fitted athletic top with arm guard, cargo trousers",
            "soft technical shirt with arm guard and chest guard, cargo trousers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Focused steady gaze, subtle composed smile, attentive marksman eyes."
        ),
    ),
    _build_style(
        style_id="shooting_range_pistol",
        mode="social",
        location_type="indoor",
        label_ru="🎯 Тир (пистолет)",
        hook_ru="Защитные очки и наушники — характер в кадре",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=2,
        scene=(
            "indoor pistol shooting range with shooting bays in the background, "
            "concrete floor in foreground, neutral overhead glow, brass "
            "casings on the floor"
        ),
        scene_overrides=[
            "indoor pistol range with paper targets downrange in the background, "
            "concrete floor in foreground",
            "shooting range with row of shooting bays in the background, polished "
            "concrete floor in foreground, neutral overhead light",
            "tactical training range with sandbag walls in the background, "
            "polished concrete floor in foreground",
        ],
        triggers=[
            "indoor pistol shooting bays in the background",
            "paper targets downrange behind",
            "brass casings on the range floor in foreground",
            "tactical training range sandbag walls behind",
        ],
        clothing_default=(
            "fitted technical range shirt, neat tactical belt, dark cargo trousers, "
            "ear protection muffs around the neck, safety glasses, "
            "well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted range polo with tactical belt, dark trousers",
            "soft technical shirt with ear protection muffs and safety glasses",
        ],
        lighting_pool=_INDOOR_LIGHTING_TECHNICAL,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Composed focused gaze, calm steady smile, attentive marksman eyes."
        ),
    ),
    _build_style(
        style_id="mountaineering_summit",
        mode="social",
        location_type="outdoor",
        label_ru="⛰ Альпинизм",
        hook_ru="Вершина и снега — про силу духа",
        meta_param="appeal",
        delta_range=(0.30, 0.50),
        unlock_after=3,
        scene=(
            "alpine summit ridge with icy patches on the rocks, distant peaks "
            "stretching to the horizon in the background, packed scree path in "
            "foreground, clear cold alpine air"
        ),
        scene_overrides=[
            "alpine summit with cairn of stones in foreground, distant peaks in "
            "the background, clear alpine air",
            "high mountain ridge with snow cornice in the background, rocky path "
            "in foreground, soft side light",
            "alpine pass with glacier visible in the background, scree slope in "
            "foreground, diffused overcast daylight",
        ],
        triggers=[
            "alpine summit ridge with snow on the rocks",
            "distant mountain peaks stretching to the horizon",
            "cairn of stones at the alpine summit",
            "glacier visible from the alpine pass",
        ],
        clothing_default=(
            "technical alpine shell jacket over a fleece mid-layer, mountaineering "
            "trousers, sturdy mountaineering boots, ice axe in hand, climbing "
            "helmet, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "alpine shell jacket over a base layer, mountaineering trousers, boots",
            "insulated softshell jacket over a thermal layer, mountaineering trousers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + ["bright alpine sun, sharp shadows"],
        weather_pool=_WEATHER_MOUNTAIN + ["clear alpine air with distant peaks"],
        tod_pool=_TOD_OUTDOOR,
        season_pool=["spring", "summer", "autumn", "winter"],
        expression=(
            "Calm determined gaze, satisfied warm smile, attentive mountaineer eyes."
        ),
        winter_clothing={
            "male": (
                "heavy insulated mountaineering jacket over a fleece mid-layer, "
                "insulated alpine trousers, mountaineering boots, helmet, ice axe"
            ),
            "female": (
                "heavy insulated mountaineering jacket over a fleece mid-layer, "
                "insulated alpine trousers, mountaineering boots, helmet, ice axe"
            ),
            "neutral": (
                "heavy insulated mountaineering jacket over a fleece mid-layer, "
                "insulated alpine trousers, mountaineering boots, helmet, ice axe"
            ),
        },
    ),
    _build_style(
        style_id="kayak_white_water",
        mode="social",
        location_type="outdoor",
        label_ru="🛶 Каякинг по порогам",
        hook_ru="Брызги и весло — про драйв и характер",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "river rapid with whitewater foam in foreground, rocky banks in the "
            "background, kayak hull cutting through the wave, bright daylight"
        ),
        scene_overrides=[
            "river canyon with whitewater rapid in foreground, rocky walls in the "
            "background, bright daylight",
            "mountain river rapid with mossy boulders in foreground, forested banks "
            "in the background",
            "calm pool below a rapid in foreground, river canyon in the background, "
            "diffused overcast daylight",
        ],
        triggers=[
            "whitewater rapid with foaming water",
            "kayak hull cutting through the river wave",
            "river canyon with rocky walls behind",
            "mountain river rapid with mossy boulders",
        ],
        clothing_default=(
            "neoprene paddling jacket over a quick-dry shirt, spray skirt, "
            "kayak helmet, life vest, paddle in hand, well-fitted across the "
            "shoulders"
        ),
        clothing_allowed=[
            "fitted paddling jacket over a base layer, life vest, helmet",
            "quick-dry rash guard under a paddling jacket, life vest, helmet",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_MOUNTAIN,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Focused energised gaze, exhilarated subtle smile, attentive paddler eyes."
        ),
    ),
    _build_style(
        style_id="horseback_riding_forest",
        mode="social",
        location_type="outdoor",
        label_ru="🐎 Верховая езда",
        hook_ru="Седло и лесная тропа — про благородство",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=2,
        scene=(
            "wooded forest trail with a calm chestnut horse on the path in "
            "foreground, tall trees in the background, soft dappled daylight"
        ),
        scene_overrides=[
            "open meadow trail with a calm horse in foreground, distant trees in "
            "the background, soft morning light",
            "forest trail by a stream with a chestnut horse in foreground, mossy "
            "stones in the background",
            "riding center paddock with a saddled horse in foreground, wooden "
            "fence in the background, soft afternoon light",
        ],
        triggers=[
            "calm chestnut horse on the forest trail",
            "saddled horse in the riding center paddock",
            "forest trail by a stream with a horse",
            "open meadow with a calm horse and rider",
        ],
        clothing_default=(
            "fitted equestrian jacket over a crisp shirt, neat riding breeches, "
            "tall leather riding boots, riding helmet, well-fitted across the "
            "shoulders"
        ),
        clothing_allowed=[
            "fitted equestrian polo, riding breeches, tall boots, helmet",
            "tailored riding jacket over a turtleneck, breeches, tall boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm graceful gaze, warm composed smile, attentive horsewoman eyes."
        ),
        winter_clothing={
            "male": (
                "insulated equestrian jacket over a fleece layer, warm riding "
                "breeches, tall winter riding boots, helmet over a thin beanie"
            ),
            "female": (
                "insulated equestrian jacket over a fleece layer, warm riding "
                "breeches, tall winter riding boots, helmet over a thin beanie"
            ),
            "neutral": (
                "insulated equestrian jacket over a fleece layer, warm riding "
                "breeches, tall winter riding boots, helmet over a thin beanie"
            ),
        },
    ),
    _build_style(
        style_id="sailing_yacht_open_sea",
        mode="social",
        location_type="outdoor",
        label_ru="⛵ Парусная яхта",
        hook_ru="Штурвал и паруса — про лёгкость и свободу",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "sailing yacht deck with a tall mast and full mainsail in the "
            "background, polished teak deck in foreground, open sea horizon, "
            "warm afternoon sunlight"
        ),
        scene_overrides=[
            "sailing yacht cockpit with the helm wheel in foreground, full "
            "mainsail in the background, open sea",
            "yacht bow with a sailing jib in the background, polished teak deck "
            "in foreground, soft golden hour",
            "sailing yacht heeled in a breeze, blue water along the hull, sail in "
            "the background, bright daylight",
        ],
        triggers=[
            "tall mast with a full mainsail behind",
            "yacht helm wheel in foreground",
            "yacht bow with a sailing jib behind",
            "sailing yacht heeled in a breeze",
        ],
        clothing_default=(
            "fitted crisp white sailing polo, neat navy chinos, deck shoes, "
            "polarized sunglasses on top of the head, well-fitted across the "
            "shoulders"
        ),
        clothing_allowed=[
            "fitted breton stripe shirt, navy chinos, deck shoes",
            "lightweight sailing jacket over a polo, navy chinos, deck shoes",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + ["bright sea-reflected daylight"],
        weather_pool=_WEATHER_COASTAL,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm refined gaze, easy confident smile, attentive sailor eyes."
        ),
    ),
    _build_style(
        style_id="rock_climbing_gym",
        mode="social",
        location_type="indoor",
        label_ru="🧗 Скалодром",
        hook_ru="Зацепы и страховка — про спорт и характер",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "indoor climbing gym with a tall bouldering wall in the background, "
            "colorful holds across the wall, padded floor in foreground, neutral "
            "overhead glow"
        ),
        scene_overrides=[
            "climbing gym with a lead wall in the background, ropes hanging, "
            "padded floor in foreground",
            "climbing gym training board with crimps in the background, padded "
            "floor in foreground, neutral overhead light",
            "indoor climbing wall with overhang section in the background, "
            "chalk bag on a bench in foreground",
        ],
        triggers=[
            "tall bouldering wall in the climbing gym behind",
            "lead climbing wall with ropes hanging behind",
            "climbing training board with crimps behind",
            "indoor climbing wall overhang section behind",
        ],
        clothing_default=(
            "fitted athletic tank or short-sleeve climbing shirt, climbing pants, "
            "chalk bag on a belt, climbing shoes, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted athletic top, climbing pants, chalk bag",
            "fitted athletic shirt under a soft hoodie, climbing pants",
        ],
        lighting_pool=_INDOOR_LIGHTING_TECHNICAL,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Determined focused gaze, satisfied confident smile, attentive climber eyes."
        ),
    ),
    _build_style(
        style_id="paragliding_launch",
        mode="social",
        location_type="outdoor",
        label_ru="🪂 Парапланеризм",
        hook_ru="Купол и обрыв — про свободу полёта",
        meta_param="appeal",
        delta_range=(0.30, 0.50),
        unlock_after=3,
        scene=(
            "mountain paragliding launch with a colorful canopy spread on the grass "
            "in foreground, valley vista in the background, clear alpine air"
        ),
        scene_overrides=[
            "paragliding takeoff ramp with a canopy partially inflated in "
            "foreground, distant mountains in the background",
            "alpine meadow launch with paragliding canopy in foreground, deep "
            "valley behind, soft afternoon light",
            "mountainside launch zone with paragliding pilot harness in foreground, "
            "valley vista in the background, diffused daylight",
        ],
        triggers=[
            "paragliding canopy spread on the launch grass",
            "paragliding canopy partially inflated at takeoff",
            "alpine valley vista from the paragliding launch",
            "paragliding pilot harness in foreground",
        ],
        clothing_default=(
            "technical paragliding pilot jacket over a base layer, harness with "
            "leg loops, sturdy hiking boots, paragliding helmet, well-fitted "
            "across the shoulders"
        ),
        clothing_allowed=[
            "soft-shell jacket over a base layer, harness, helmet, hiking boots",
            "fitted technical shirt under a harness, hiking trousers, helmet",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_MOUNTAIN,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm exhilarated gaze, warm satisfied smile, attentive pilot eyes."
        ),
    ),
    _build_style(
        style_id="astrophotography_field",
        mode="social",
        location_type="outdoor",
        label_ru="🔭 Астрофотография",
        hook_ru="Млечный путь и телескоп — про эстетику ночного неба",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "remote dark-sky field with a telescope on a sturdy tripod in "
            "foreground, the Milky Way arching across the sky in the background, "
            "soft starlight"
        ),
        scene_overrides=[
            "high-altitude meadow with a tracking mount and DSLR camera on a "
            "tripod in foreground, starry sky in the background",
            "mountain plateau with a telescope in foreground, distant horizon and "
            "the Milky Way in the background, faint moonlight",
            "stargazing camp with red headlamp glow in foreground, telescope on a "
            "tripod, dark sky in the background",
        ],
        triggers=[
            "telescope on a sturdy tripod in foreground",
            "the Milky Way arching across the sky behind",
            "tracking mount and DSLR camera on a tripod",
            "stargazing camp with red headlamp glow",
        ],
        clothing_default=(
            "warm insulated jacket over a fleece layer, dark trousers, sturdy "
            "boots, knit beanie, red headlamp around the neck, well-fitted across "
            "the shoulders"
        ),
        clothing_allowed=[
            "soft-shell jacket over a thermal layer, dark trousers, beanie",
            "fitted technical jacket over a fleece, dark trousers, beanie",
        ],
        lighting_pool=[
            "soft starlight",
            "faint moonlight",
            "low ambient blue-hour glow",
            "warm headlamp side light",
        ],
        weather_pool=["clear cold night air", "thin high cirrus, stars visible"],
        tod_pool=_TOD_OUTDOOR_NIGHT,
        expression=(
            "Quiet wondering gaze, soft contemplative smile, attentive observer eyes."
        ),
    ),
    _build_style(
        style_id="vintage_film_camera",
        mode="social",
        location_type="outdoor",
        label_ru="📷 Плёночная фотография",
        hook_ru="Старый Canon и переулок — про эстетический вкус",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "narrow old-town side street with brick facades in the background, "
            "cobblestone pavement in foreground, vintage 35mm rangefinder camera "
            "with a leather strap, soft afternoon light"
        ),
        scene_overrides=[
            "cobbled lane with a mural on a wall in the background, vintage SLR "
            "camera with a leather strap in foreground",
            "old-town square with stone fountain in the background, vintage "
            "twin-lens reflex camera in foreground, soft morning light",
            "narrow shopfront street with neon sign in the background, vintage "
            "35mm camera in foreground, warm evening light",
        ],
        triggers=[
            "vintage 35mm rangefinder camera with a leather strap",
            "vintage twin-lens reflex camera in foreground",
            "old-town side street with brick facades behind",
            "cobbled lane with a mural on the wall behind",
        ],
        clothing_default=(
            "fitted soft cotton shirt under a tailored wool overcoat, fine trousers, "
            "leather loafers, soft camera strap across the shoulder, well-fitted "
            "across the shoulders"
        ),
        clothing_allowed=[
            "fitted turtleneck under a wool overcoat, fine trousers, loafers",
            "soft linen shirt under a fitted blazer, dark jeans, leather sneakers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR_ALL,
        expression=(
            "Curious refined gaze, subtle warm smile, attentive photographer eyes."
        ),
    ),
    _build_style(
        style_id="chess_park",
        mode="social",
        location_type="outdoor",
        label_ru="♟ Шахматы в парке",
        hook_ru="Шахматный столик в парке — про интеллект",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "city park chess table with a wooden chess set mid-game in foreground, "
            "park benches and tall trees in the background, soft afternoon light"
        ),
        scene_overrides=[
            "park alley with stone chess tables in the background, wooden chess "
            "set in foreground, autumn leaves on the ground",
            "garden pavilion with chess set on a small table in foreground, leafy "
            "background, soft morning light",
            "outdoor chess corner with several boards in the background, central "
            "wooden board in foreground, warm afternoon light",
        ],
        triggers=[
            "wooden chess set mid-game on the park table",
            "city park chess tables in the background",
            "garden pavilion with a chess set in foreground",
            "outdoor chess corner with several boards behind",
        ],
        clothing_default=(
            "fitted wool overcoat over a turtleneck, fine trousers, leather "
            "loafers, soft scarf, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted blazer over a turtleneck, dark trousers, leather shoes",
            "soft cardigan over a crisp shirt, dark trousers, loafers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Thoughtful focused gaze, subtle knowing smile, attentive strategist eyes."
        ),
        winter_clothing={
            "male": (
                "heavy wool overcoat over a turtleneck, fine trousers, leather "
                "winter boots, soft scarf, knit beanie"
            ),
            "female": (
                "heavy wool overcoat over a turtleneck, fine trousers, leather "
                "winter boots, soft scarf, knit beret"
            ),
            "neutral": (
                "heavy wool overcoat over a turtleneck, fine trousers, leather "
                "winter boots, soft scarf, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="vinyl_records_collector",
        mode="social",
        location_type="indoor",
        label_ru="💿 Винил и проигрыватель",
        hook_ru="Стеллаж пластинок — про музыкальный вкус",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "home listening room with a tall vinyl shelf in the background, "
            "turntable on a wooden cabinet in foreground, warm tungsten lamp"
        ),
        scene_overrides=[
            "vinyl record store with rows of crates in the background, wooden "
            "counter in foreground, warm overhead light",
            "home listening room with a hi-fi stack in the background, turntable "
            "on a sideboard in foreground, soft window light",
            "record collector's lounge with art prints on the wall in the "
            "background, vinyl on a turntable in foreground, warm side lamp",
        ],
        triggers=[
            "tall vinyl shelf in the listening room behind",
            "turntable on a wooden cabinet in foreground",
            "vinyl record store crates behind",
            "hi-fi stack in the listening room behind",
        ],
        clothing_default=(
            "fitted soft band tee under a tailored wool cardigan, dark jeans, "
            "leather sneakers, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted shirt under a soft cardigan, dark jeans",
            "fitted soft sweater, dark jeans, leather sneakers",
        ],
        lighting_pool=_INDOOR_LIGHTING_WORKSHOP,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Calm passionate gaze, subtle warm smile, attentive listener eyes."
        ),
    ),
    _build_style(
        style_id="calligraphy_atelier",
        mode="social",
        location_type="indoor",
        label_ru="🖋 Каллиграфия",
        hook_ru="Тушь и кисть — про утончённый вкус",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "calligraphy atelier with a wooden writing desk in foreground, "
            "ink stone and brush set neatly arranged, finished scrolls hanging on "
            "the back wall, soft side window light"
        ),
        scene_overrides=[
            "calligraphy studio with a long desk in foreground, scrolls and brush "
            "rack in the background, warm desk lamp",
            "Japanese-style calligraphy room with tatami mats in the background, "
            "low writing desk in foreground, soft daylight",
            "calligraphy atelier with shelves of paper and ink in the background, "
            "wooden desk in foreground, warm key light",
        ],
        triggers=[
            "ink stone and brush set on the calligraphy desk in foreground",
            "finished calligraphy scrolls hanging on the atelier wall behind",
            "Japanese calligraphy room with tatami mats behind",
            "shelves of paper and ink in the calligraphy atelier behind",
        ],
        clothing_default=(
            "fitted soft cotton shirt with rolled sleeves, neat trousers, leather "
            "loafers, soft linen apron, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted turtleneck under a linen apron, dark trousers",
            "soft cotton shirt with rolled sleeves under a linen apron, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_WORKSHOP,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Calm focused gaze, subtle refined smile, attentive artist eyes."
        ),
    ),
    _build_style(
        style_id="pottery_studio",
        mode="social",
        location_type="indoor",
        label_ru="🏺 Гончарное дело",
        hook_ru="Гончарный круг и глина — про творчество руками",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "ceramics studio with a pottery wheel in foreground, finished pieces "
            "on shelves in the background, polished concrete floor, soft window "
            "light from the side"
        ),
        scene_overrides=[
            "pottery studio with kiln in the background, wedging table in "
            "foreground, soft daylight",
            "ceramics workshop with hand-built clay pieces on shelves in the "
            "background, pottery wheel in foreground",
            "ceramics studio corner with thrown vessels drying on a wooden plank, "
            "wheel in foreground, warm tungsten lamp",
        ],
        triggers=[
            "pottery wheel on the ceramics studio floor in foreground",
            "kiln in the pottery studio background",
            "finished ceramic pieces on the studio shelves behind",
            "thrown vessels drying on a wooden plank in the studio",
        ],
        clothing_default=(
            "fitted soft tee under a clay-streaked canvas apron, rolled sleeves, "
            "dark trousers, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted denim shirt under a canvas apron, dark trousers",
            "fitted soft sweater under a linen apron, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_WORKSHOP,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Calm meditative gaze, soft warm smile, attentive artisan eyes."
        ),
    ),
    _build_style(
        style_id="woodcarving_bench",
        mode="social",
        location_type="indoor",
        label_ru="🪵 Резьба по дереву",
        hook_ru="Стамески и заготовка — про традиционное ремесло",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "woodcarving workshop with a long bench in foreground, a row of "
            "carving chisels in the background, partially carved figure on the "
            "bench, warm tungsten work lamp"
        ),
        scene_overrides=[
            "traditional woodcarving workshop with finished carvings on a shelf "
            "in the background, bench in foreground, soft window light",
            "carving studio with timber stock in the background, carved bowl on "
            "the bench in foreground, warm side light",
            "village workshop with carving tools hanging on the wall in the "
            "background, bench in foreground, warm key light",
        ],
        triggers=[
            "row of carving chisels on the workshop wall behind",
            "partially carved figure on the woodcarving bench",
            "finished wood carvings on the workshop shelf behind",
            "carving studio with timber stock behind",
        ],
        clothing_default=(
            "fitted flannel shirt under a sturdy canvas apron, dark trousers, "
            "work boots, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted denim shirt under a canvas apron, dark trousers",
            "fitted soft sweater under a leather apron, dark trousers",
        ],
        lighting_pool=_INDOOR_LIGHTING_WORKSHOP,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Calm focused gaze, soft satisfied smile, attentive artisan eyes."
        ),
    ),
    _build_style(
        style_id="beekeeping_apiary",
        mode="social",
        location_type="outdoor",
        label_ru="🐝 Пасека",
        hook_ru="Ульи и медовые рамки — про природу и заботу",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=2,
        scene=(
            "rural apiary with a row of wooden beehives in the background, "
            "wildflowers in the foreground, distant tree line, soft summer "
            "daylight"
        ),
        scene_overrides=[
            "apiary in a forest clearing with hives in the background, blooming "
            "meadow in foreground, soft morning light",
            "rural homestead apiary with painted hives along a fence in the "
            "background, gravel path in foreground",
            "highland apiary with hives in the background, distant valley in "
            "view, diffused overcast daylight",
        ],
        triggers=[
            "row of wooden beehives in the apiary behind",
            "painted apiary hives along a wooden fence behind",
            "blooming meadow in the apiary foreground",
            "highland apiary with distant valley behind",
        ],
        clothing_default=(
            "white beekeeping suit with mesh veil hood pulled back to reveal the "
            "face, gloves tucked into the belt, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "white beekeeping jacket over a base layer, mesh hood pulled back",
            "beekeeping smock over a shirt, mesh hood pulled back",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm patient gaze, warm gentle smile, attentive beekeeper eyes."
        ),
    ),
    _build_style(
        style_id="homebrewing_garage",
        mode="social",
        location_type="indoor",
        label_ru="🍺 Домашнее пивоварение",
        hook_ru="Ферментёры и краны — про увлечение и мастерство",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "garage homebrewery with stainless steel fermenters in the background, "
            "wooden counter with bottles and a hydrometer in foreground, warm "
            "pendant glow"
        ),
        scene_overrides=[
            "garage brewery with conical fermenters in the background, brewing "
            "kettle in foreground, warm overhead light",
            "home brewery corner with a tap row mounted on the back wall, "
            "wooden bar in foreground, warm side light",
            "homebrew workshop with grain sacks in the background, brewing "
            "kettle in foreground, neutral overhead light",
        ],
        triggers=[
            "stainless steel fermenters in the home brewery behind",
            "tap row mounted on the home brewery wall behind",
            "brewing kettle on the homebrew counter in foreground",
            "grain sacks in the homebrew workshop behind",
        ],
        clothing_default=(
            "fitted soft tee under a sturdy canvas apron, dark jeans, leather "
            "sneakers, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted flannel shirt under a canvas apron, dark jeans",
            "fitted soft sweater under a linen apron, dark jeans",
        ],
        lighting_pool=_INDOOR_LIGHTING_KITCHEN,
        tod_pool=_TOD_INDOOR,
        expression=(
            "Warm engaged gaze, satisfied confident smile, attentive brewer eyes."
        ),
    ),
    _build_style(
        style_id="falconry_field",
        mode="social",
        location_type="outdoor",
        label_ru="🦅 Соколиная охота",
        hook_ru="Сокол на руке — благородство и характер",
        meta_param="appeal",
        delta_range=(0.30, 0.50),
        unlock_after=3,
        scene=(
            "open steppe meadow with a falcon perched on a gloved hand in "
            "foreground, distant tree line in the background, warm afternoon light"
        ),
        scene_overrides=[
            "highland meadow with a hawk on a gloved hand in foreground, distant "
            "mountains in the background",
            "rural field with a peregrine falcon on a gloved hand in foreground, "
            "wooden falconer's perch nearby, soft morning light",
            "forest edge with a golden eagle on a gloved hand in foreground, "
            "trees in the background, diffused daylight",
        ],
        triggers=[
            "falcon perched on a gloved hand in foreground",
            "hawk on a gloved hand in the highland meadow",
            "peregrine falcon on a gloved hand in foreground",
            "golden eagle on a gloved hand at the forest edge",
        ],
        clothing_default=(
            "fitted waxed countryside jacket over a flannel shirt, sturdy trousers, "
            "hiking boots, thick leather falconry glove on the arm, well-fitted "
            "across the shoulders"
        ),
        clothing_allowed=[
            "fitted soft-shell jacket over a flannel shirt, sturdy trousers, boots",
            "tailored countryside coat over a turtleneck, sturdy trousers, boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm noble gaze, subtle composed smile, attentive falconer eyes."
        ),
        winter_clothing={
            "male": (
                "insulated waxed countryside coat over a fleece, sturdy trousers, "
                "winter boots, falconry glove, knit beanie"
            ),
            "female": (
                "insulated waxed countryside coat over a fleece, sturdy trousers, "
                "winter boots, falconry glove, knit beanie"
            ),
            "neutral": (
                "insulated waxed countryside coat over a fleece, sturdy trousers, "
                "winter boots, falconry glove, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="drone_aerial_pilot",
        mode="social",
        location_type="outdoor",
        label_ru="🛸 Дроновод",
        hook_ru="Пульт управления и поле — технологичное хобби",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "open coastal meadow with a folded camera drone on a launch mat in "
            "foreground, controller with screen in hand, distant horizon in the "
            "background, soft afternoon light"
        ),
        scene_overrides=[
            "open hillside with a camera drone on the grass in foreground, "
            "controller in hand, distant valley in the background",
            "rural field with a quadcopter on a folding pad in foreground, "
            "horizon in the background, diffused overcast daylight",
            "lakeside meadow with a drone on a landing pad in foreground, "
            "controller in hand, soft golden hour",
        ],
        triggers=[
            "folded camera drone on a launch mat in foreground",
            "drone controller with screen in hand",
            "quadcopter on a folding pad in the field in foreground",
            "camera drone on the landing pad in foreground",
        ],
        clothing_default=(
            "fitted technical jacket over a soft tee, dark trousers, sport shoes, "
            "polarized sunglasses on top of the head, well-fitted across the "
            "shoulders"
        ),
        clothing_allowed=[
            "fitted soft-shell jacket over a tee, dark trousers",
            "fitted athletic shirt under a soft-shell jacket, dark trousers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm engaged gaze, subtle confident smile, attentive pilot eyes."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Dating — Russian cities + natural scenery (20)
# ---------------------------------------------------------------------------

_DATING_STYLES: list[dict[str, Any]] = [
    _build_style(
        style_id="moscow_red_square",
        mode="dating",
        location_type="outdoor",
        label_ru="🇷🇺 Красная площадь",
        hook_ru="Красная площадь и Кремль — про столичный шарм",
        meta_param="presence",
        delta_range=(0.25, 0.45),
        unlock_after=0,
        scene=(
            "Red Square panorama with the Kremlin wall and Spasskaya Tower in the "
            "background, polished stone pavement in foreground, warm afternoon "
            "Moscow light"
        ),
        scene_overrides=[
            "Red Square with St Basil's Cathedral domes in the background, "
            "polished stone pavement in foreground, soft golden hour",
            "GUM department store facade in the background, Red Square pavement "
            "in foreground, warm evening city lights",
            "Kremlin embankment with the Kremlin towers in the background, "
            "Moskva river in foreground, blue hour cinematic light",
        ],
        triggers=[
            "Kremlin wall and Spasskaya Tower in the background",
            "St Basil's Cathedral domes in the background",
            "GUM department store facade in the background",
            "Kremlin towers reflected in the Moskva river",
        ],
        clothing_default=(
            "fitted tailored wool coat over a turtleneck, dark trousers, leather "
            "Chelsea boots, soft scarf, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted blazer over a knit, dark jeans, leather boots",
            "tailored overcoat over a fitted sweater, dark trousers, leather shoes",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR_ALL,
        expression=(
            "Warm worldly gaze, subtle confident smile, calm capital-city eyes."
        ),
        winter_clothing={
            "male": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie, soft scarf"
            ),
            "female": (
                "heavy wool overcoat over a turtleneck or knit dress, dark tights, "
                "leather winter boots, knit beret, soft scarf"
            ),
            "neutral": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie, soft scarf"
            ),
        },
    ),
    _build_style(
        style_id="moscow_zaryadye",
        mode="dating",
        location_type="outdoor",
        label_ru="🌉 Парк Зарядье",
        hook_ru="Парящий мост и виды на Кремль — современная Москва",
        meta_param="presence",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "Zaryadye floating bridge with the Kremlin and St Basil's domes in "
            "the background, polished walkway in foreground, soft evening light"
        ),
        scene_overrides=[
            "Zaryadye park glass dome in the background, polished landscaped "
            "walkway in foreground, soft daylight",
            "Zaryadye floating bridge with the Moskva river in foreground, "
            "Kremlin towers in the background, blue hour cinematic light",
            "Zaryadye landscape terraces with native plants in the background, "
            "polished walkway in foreground, soft golden hour",
        ],
        triggers=[
            "Zaryadye floating bridge with the Kremlin behind",
            "Zaryadye park glass dome behind",
            "Moskva river with Kremlin towers behind",
            "Zaryadye landscape terraces with native plants behind",
        ],
        clothing_default=(
            "fitted tailored overcoat over a knit, slim trousers, leather "
            "ankle boots, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted soft-shell coat over a turtleneck, dark trousers, leather boots",
            "tailored blazer over a fine knit, dark trousers, leather shoes",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR_ALL,
        expression=(
            "Easy modern gaze, warm relaxed smile, attentive contemporary eyes."
        ),
        winter_clothing={
            "male": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie"
            ),
            "female": (
                "heavy wool overcoat over a turtleneck, dark tights, leather "
                "winter boots, knit beret"
            ),
            "neutral": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="spb_palace_square",
        mode="dating",
        location_type="outdoor",
        label_ru="🏛 Дворцовая площадь",
        hook_ru="Эрмитаж и колонна — классический Петербург",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=0,
        scene=(
            "Saint Petersburg Palace Square with the Winter Palace facade in the "
            "background, Alexander Column visible, polished granite pavement in "
            "foreground, soft afternoon light"
        ),
        scene_overrides=[
            "Palace Square with the General Staff arch in the background, polished "
            "granite pavement in foreground, soft morning light",
            "Hermitage facade along the Neva embankment in the background, polished "
            "granite pavement in foreground, soft golden hour",
            "Alexander Column close in the background, polished granite square in "
            "foreground, warm evening light",
        ],
        triggers=[
            "Winter Palace facade in the background",
            "Alexander Column on Palace Square in the background",
            "General Staff arch in the background",
            "Hermitage facade along the Neva embankment behind",
        ],
        clothing_default=(
            "fitted tailored wool coat over a knit, dark trousers, leather "
            "Chelsea boots, soft scarf, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted blazer over a fine knit, dark trousers, leather shoes",
            "tailored overcoat over a turtleneck, dark trousers, leather boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR_ALL,
        expression=(
            "Refined warm gaze, subtle Petersburg smile, attentive cultured eyes."
        ),
        winter_clothing={
            "male": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie, soft scarf"
            ),
            "female": (
                "heavy wool overcoat over a turtleneck or knit dress, dark tights, "
                "leather winter boots, knit beret, soft scarf"
            ),
            "neutral": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie, soft scarf"
            ),
        },
    ),
    _build_style(
        style_id="spb_nevsky_avenue",
        mode="dating",
        location_type="outdoor",
        label_ru="🛣 Невский проспект",
        hook_ru="Фасады Невского — про городской вкус",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "Nevsky Avenue with classical Petersburg facades in the background, "
            "polished sidewalk in foreground, warm afternoon light"
        ),
        scene_overrides=[
            "Nevsky Avenue intersection with Kazan Cathedral colonnade in the "
            "background, polished sidewalk in foreground, soft golden hour",
            "Nevsky Avenue with Singer house dome in the background, polished "
            "sidewalk in foreground, soft daylight",
            "Anichkov bridge with Klodt sculptures in the background, polished "
            "stone pavement in foreground, warm evening light",
        ],
        triggers=[
            "classical Petersburg facades along Nevsky Avenue",
            "Kazan Cathedral colonnade in the background",
            "Singer house dome on Nevsky in the background",
            "Anichkov bridge with Klodt sculptures behind",
        ],
        clothing_default=(
            "fitted tailored overcoat over a fine knit, slim trousers, leather "
            "shoes, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted blazer over a turtleneck, dark trousers, leather shoes",
            "tailored coat over a knit, dark trousers, leather boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR_ALL,
        expression=(
            "Warm refined gaze, easy confident smile, attentive city eyes."
        ),
        winter_clothing={
            "male": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, soft scarf"
            ),
            "female": (
                "heavy wool overcoat over a turtleneck, dark tights, leather "
                "winter boots, knit beret, soft scarf"
            ),
            "neutral": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, soft scarf"
            ),
        },
    ),
    _build_style(
        style_id="kazan_kremlin",
        mode="dating",
        location_type="outdoor",
        label_ru="🕌 Казанский Кремль",
        hook_ru="Кул-Шариф и Сююмбике — про восток России",
        meta_param="presence",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "Kazan Kremlin courtyard with Kul-Sharif mosque in the background, "
            "polished stone pavement in foreground, soft afternoon light"
        ),
        scene_overrides=[
            "Kazan Kremlin with the Soyembika Tower in the background, polished "
            "stone pavement in foreground, soft golden hour",
            "Kazan Kremlin wall with the white facade in the background, polished "
            "stone pavement in foreground, warm afternoon light",
            "Kazan Kremlin overlook with the river in the background, polished "
            "stone pavement in foreground, blue hour cinematic light",
        ],
        triggers=[
            "Kul-Sharif mosque in the Kazan Kremlin courtyard behind",
            "Soyembika Tower in the Kazan Kremlin behind",
            "Kazan Kremlin wall with the white facade behind",
            "Kazan Kremlin overlook with the river behind",
        ],
        clothing_default=(
            "fitted tailored overcoat over a fine knit, dark trousers, leather "
            "ankle boots, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted blazer over a turtleneck, dark trousers, leather shoes",
            "tailored coat over a soft sweater, dark trousers, leather boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR_ALL,
        expression=(
            "Warm worldly gaze, subtle confident smile, attentive cultural eyes."
        ),
        winter_clothing={
            "male": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie"
            ),
            "female": (
                "heavy wool overcoat over a turtleneck, dark tights, leather "
                "winter boots, knit beret"
            ),
            "neutral": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="sochi_seaside",
        mode="dating",
        location_type="outdoor",
        label_ru="🌊 Сочи, набережная",
        hook_ru="Море и Кавказские горы — про южное настроение",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=1,
        scene=(
            "Sochi seaside promenade with palm trees along the railing in the "
            "background, polished pavement in foreground, distant Caucasus "
            "mountains, soft afternoon light"
        ),
        scene_overrides=[
            "Sochi promenade with marina yachts in the background, polished "
            "pavement in foreground, warm golden hour",
            "Black Sea pebble beach with mountain ridges in the background, "
            "sandy pavement in foreground, soft morning light",
            "Sochi waterfront with the open Black Sea horizon in the background, "
            "polished pavement in foreground, warm afternoon sunlight",
        ],
        triggers=[
            "Sochi seaside promenade with palm trees behind",
            "Sochi marina yachts in the background",
            "Black Sea pebble beach with Caucasus mountains behind",
            "Sochi waterfront with the open Black Sea horizon behind",
        ],
        clothing_default=(
            "fitted linen shirt with rolled sleeves, slim chinos, leather "
            "loafers, polarized sunglasses, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted breton stripe shirt, light chinos, espadrilles",
            "soft linen blazer over a tee, light chinos, loafers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + ["bright sea-reflected daylight"],
        weather_pool=_WEATHER_COASTAL,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Warm easy gaze, relaxed confident smile, attentive seaside eyes."
        ),
        winter_clothing={
            "male": (
                "fitted soft-shell jacket over a knit, dark trousers, leather "
                "boots, soft scarf"
            ),
            "female": (
                "tailored wool coat over a knit, dark trousers, leather boots, "
                "soft scarf"
            ),
            "neutral": (
                "fitted soft-shell jacket over a knit, dark trousers, leather "
                "boots, soft scarf"
            ),
        },
    ),
    _build_style(
        style_id="vladivostok_golden_bridge",
        mode="dating",
        location_type="outdoor",
        label_ru="🌉 Владивосток, Золотой мост",
        hook_ru="Дальневосточный берег — про размах России",
        meta_param="presence",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "Vladivostok waterfront with the Golden Bridge cable-stay towers in "
            "the background, polished pavement in foreground, distant hills "
            "across the bay, soft afternoon light"
        ),
        scene_overrides=[
            "Vladivostok promenade with the Russky Bridge in the background, "
            "polished pavement in foreground, warm evening light",
            "Vladivostok harbor with the Golden Horn bay in the background, "
            "polished pavement in foreground, soft golden hour",
            "Vladivostok hillside lookout with the Golden Bridge in the background, "
            "polished pavement in foreground, blue hour cinematic light",
        ],
        triggers=[
            "Golden Bridge cable-stay towers in Vladivostok behind",
            "Russky Bridge in the background",
            "Golden Horn bay panorama behind",
            "Vladivostok hillside lookout with the Golden Bridge behind",
        ],
        clothing_default=(
            "fitted tailored overcoat over a knit, dark trousers, leather "
            "Chelsea boots, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted blazer over a turtleneck, dark trousers, leather shoes",
            "tailored coat over a soft sweater, dark trousers, leather boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_COASTAL,
        tod_pool=_TOD_OUTDOOR_ALL,
        expression=(
            "Warm worldly gaze, easy modern smile, attentive Pacific-coast eyes."
        ),
        winter_clothing={
            "male": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie"
            ),
            "female": (
                "heavy wool overcoat over a turtleneck, dark tights, leather "
                "winter boots, knit beret"
            ),
            "neutral": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="baikal_winter_ice",
        mode="dating",
        location_type="outdoor",
        label_ru="🧊 Байкал зимой",
        hook_ru="Прозрачный лёд Байкала — про русскую природу",
        meta_param="appeal",
        delta_range=(0.30, 0.50),
        unlock_after=3,
        scene=(
            "Lake Baikal ice expanse with translucent blue ice in foreground, "
            "snowy distant shore in the background, clear cold air, soft "
            "afternoon light"
        ),
        scene_overrides=[
            "Baikal ice field with cracked ice patterns in foreground, distant "
            "ice hummocks in the background, clear cold air",
            "Baikal coastal cliffs with ice in foreground, snowy shore in the "
            "background, soft golden hour",
            "Olkhon island shore with frozen rocks in foreground, distant "
            "mountains in the background, diffused overcast daylight",
        ],
        triggers=[
            "Lake Baikal translucent blue ice in foreground",
            "Baikal ice field with cracked ice patterns",
            "Baikal coastal cliffs with ice in foreground",
            "Olkhon island shore with frozen rocks",
        ],
        clothing_default=(
            "heavy insulated parka over a thermal layer, dark winter trousers, "
            "winter boots, knit beanie, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "insulated parka over a fleece, dark winter trousers, winter boots",
            "insulated jacket over a turtleneck, winter trousers, winter boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_COLD,
        tod_pool=_TOD_OUTDOOR,
        season_pool=["winter"],
        expression=(
            "Calm wondering gaze, soft warm smile, attentive Siberian eyes."
        ),
    ),
    _build_style(
        style_id="altai_mountains",
        mode="dating",
        location_type="outdoor",
        label_ru="🏔 Алтайские горы",
        hook_ru="Бирюзовая Катунь и хребты — про сибирскую красоту",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "Altai mountain valley with a turquoise Katun river in foreground, "
            "snowy ridges in the background, soft alpine air, soft afternoon "
            "light"
        ),
        scene_overrides=[
            "Altai alpine meadow with wildflowers in foreground, distant peaks "
            "in the background, soft morning light",
            "Altai river gorge with rocky banks in foreground, ridges in the "
            "background, diffused overcast daylight",
            "Altai mountain pass with a stone marker in foreground, valley "
            "stretching to the horizon, soft golden hour",
        ],
        triggers=[
            "turquoise Katun river in the Altai valley",
            "Altai alpine meadow with wildflowers in foreground",
            "Altai river gorge with rocky banks",
            "Altai mountain pass with stone marker",
        ],
        clothing_default=(
            "fitted technical shell jacket over a fleece mid-layer, sturdy "
            "trousers, hiking boots, knit beanie, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "soft-shell jacket over a base layer, sturdy trousers, hiking boots",
            "fitted technical fleece over a thermal layer, sturdy trousers, boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_MOUNTAIN,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm awed gaze, warm satisfied smile, attentive mountain eyes."
        ),
        winter_clothing={
            "male": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trousers, winter mountain boots, knit beanie"
            ),
            "female": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trousers, winter mountain boots, knit beanie"
            ),
            "neutral": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trousers, winter mountain boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="karelia_lake",
        mode="dating",
        location_type="outdoor",
        label_ru="🌲 Карельское озеро",
        hook_ru="Карельские валуны и сосны — про северную тишину",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=2,
        scene=(
            "Karelian lake with smooth granite boulders in foreground, pine trees "
            "along the shore in the background, soft northern light"
        ),
        scene_overrides=[
            "Karelian forest lake with mossy boulders in foreground, distant pines "
            "in the background, diffused overcast daylight",
            "Ladoga lake shore with granite rocks in foreground, distant islands "
            "in the background, soft golden hour",
            "Karelian wooden cabin in the background, granite shore in foreground, "
            "soft afternoon light",
        ],
        triggers=[
            "Karelian lake with smooth granite boulders",
            "Karelian forest lake with mossy boulders",
            "Ladoga lake shore with granite rocks in foreground",
            "Karelian wooden cabin behind",
        ],
        clothing_default=(
            "fitted soft-shell jacket over a flannel shirt, sturdy trousers, "
            "hiking boots, knit beanie, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted fleece over a base layer, sturdy trousers, hiking boots",
            "fitted technical jacket over a flannel shirt, sturdy trousers, boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_TEMPERATE + ["light mist over the lake"],
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm contemplative gaze, warm soft smile, attentive northern eyes."
        ),
        winter_clothing={
            "male": (
                "insulated jacket over a fleece, sturdy winter trousers, winter "
                "hiking boots, knit beanie"
            ),
            "female": (
                "insulated jacket over a fleece, sturdy winter trousers, winter "
                "hiking boots, knit beanie"
            ),
            "neutral": (
                "insulated jacket over a fleece, sturdy winter trousers, winter "
                "hiking boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="kamchatka_volcano",
        mode="dating",
        location_type="outdoor",
        label_ru="🌋 Камчатские вулканы",
        hook_ru="Действующий вулкан — про дикую природу",
        meta_param="appeal",
        delta_range=(0.30, 0.50),
        unlock_after=3,
        scene=(
            "Kamchatka plateau with a steaming volcanic cone in the background, "
            "volcanic ash and grass in foreground, soft afternoon light"
        ),
        scene_overrides=[
            "Kamchatka caldera rim with steam rising from fumaroles in the "
            "background, volcanic gravel in foreground, diffused overcast daylight",
            "Kamchatka river valley with a snow-capped volcano in the background, "
            "river stones in foreground, soft golden hour",
            "Kamchatka coastal cliff with a distant volcano in the background, "
            "rocky shore in foreground, soft afternoon light",
        ],
        triggers=[
            "steaming Kamchatka volcanic cone behind",
            "Kamchatka caldera rim with fumaroles behind",
            "Kamchatka river valley with snow-capped volcano behind",
            "Kamchatka coastal cliff with distant volcano behind",
        ],
        clothing_default=(
            "fitted technical shell jacket over a fleece mid-layer, sturdy "
            "trousers, mountain boots, knit beanie, well-fitted across the "
            "shoulders"
        ),
        clothing_allowed=[
            "soft-shell jacket over a base layer, sturdy trousers, mountain boots",
            "insulated technical jacket over a thermal layer, sturdy trousers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_MOUNTAIN + ["volcanic haze on the horizon"],
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm awed gaze, subtle satisfied smile, attentive explorer eyes."
        ),
        winter_clothing={
            "male": (
                "heavy insulated mountain jacket over a fleece mid-layer, "
                "insulated trousers, winter mountain boots, knit beanie"
            ),
            "female": (
                "heavy insulated mountain jacket over a fleece mid-layer, "
                "insulated trousers, winter mountain boots, knit beanie"
            ),
            "neutral": (
                "heavy insulated mountain jacket over a fleece mid-layer, "
                "insulated trousers, winter mountain boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="suzdal_golden_ring",
        mode="dating",
        location_type="outdoor",
        label_ru="⛪ Суздаль, Золотое кольцо",
        hook_ru="Деревянные церкви и валы — про русскую глубинку",
        meta_param="appeal",
        delta_range=(0.20, 0.40),
        unlock_after=2,
        scene=(
            "Suzdal monastery walls with wooden church domes in the background, "
            "earthen rampart in foreground, soft afternoon light"
        ),
        scene_overrides=[
            "Suzdal river bend with the Saviour Monastery walls in the background, "
            "grass riverbank in foreground, soft golden hour",
            "Suzdal kremlin earthen rampart with the Nativity Cathedral in the "
            "background, grass slope in foreground, soft morning light",
            "Suzdal market square with wooden traders' rows in the background, "
            "cobblestone pavement in foreground, warm afternoon light",
        ],
        triggers=[
            "Suzdal monastery walls with wooden church domes",
            "Suzdal river bend with the Saviour Monastery walls behind",
            "Suzdal kremlin earthen rampart with the Nativity Cathedral",
            "Suzdal market square with wooden traders' rows behind",
        ],
        clothing_default=(
            "fitted tailored wool coat over a fine knit, dark trousers, leather "
            "ankle boots, soft scarf, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted blazer over a knit, dark trousers, leather shoes",
            "tailored overcoat over a turtleneck, dark trousers, leather boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR_ALL,
        expression=(
            "Warm thoughtful gaze, soft refined smile, attentive heritage eyes."
        ),
        winter_clothing={
            "male": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie, soft scarf"
            ),
            "female": (
                "heavy wool overcoat over a turtleneck or knit dress, dark tights, "
                "leather winter boots, knit beret, soft scarf"
            ),
            "neutral": (
                "heavy wool overcoat over a turtleneck, dark trousers, leather "
                "winter boots, knit beanie, soft scarf"
            ),
        },
    ),
    _build_style(
        style_id="kavkaz_alpine",
        mode="dating",
        location_type="outdoor",
        label_ru="🏔 Кавказ, Эльбрус",
        hook_ru="Альпийские луга Кавказа — про южные горы",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "Caucasus alpine meadow with wildflowers in foreground, distant snowy "
            "Elbrus peak in the background, soft afternoon light"
        ),
        scene_overrides=[
            "Caucasus mountain pass with the Elbrus massif in the background, "
            "gravel path in foreground, diffused overcast daylight",
            "Caucasus valley with a clear mountain river in foreground, snowy "
            "peaks in the background, soft golden hour",
            "Caucasus ridge with alpine grass in foreground, distant peaks in "
            "the background, soft morning light",
        ],
        triggers=[
            "snowy Elbrus peak in the Caucasus background",
            "Caucasus mountain pass with Elbrus massif behind",
            "Caucasus valley with clear mountain river",
            "Caucasus ridge with alpine grass in foreground",
        ],
        clothing_default=(
            "fitted technical shell jacket over a fleece mid-layer, sturdy "
            "trousers, hiking boots, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "soft-shell jacket over a base layer, sturdy trousers, hiking boots",
            "fitted technical fleece over a thermal layer, sturdy trousers, boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_MOUNTAIN,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm awed gaze, warm content smile, attentive mountaineer eyes."
        ),
        winter_clothing={
            "male": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trousers, winter mountain boots, knit beanie"
            ),
            "female": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trousers, winter mountain boots, knit beanie"
            ),
            "neutral": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trousers, winter mountain boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="solovki_white_sea",
        mode="dating",
        location_type="outdoor",
        label_ru="⛪ Соловки, Белое море",
        hook_ru="Соловецкий монастырь — про русский Север",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=3,
        scene=(
            "Solovetsky Monastery walls in the background, White Sea coast in "
            "foreground, polished stone pavement, soft northern light"
        ),
        scene_overrides=[
            "Solovetsky island shore with the monastery towers in the background, "
            "stone beach in foreground, soft morning light",
            "Solovetsky kremlin walls in the background, grass field in foreground, "
            "diffused overcast daylight",
            "Solovetsky island wooden chapels in the background, gravel path in "
            "foreground, soft golden hour",
        ],
        triggers=[
            "Solovetsky Monastery walls in the background",
            "Solovetsky island shore with monastery towers behind",
            "Solovetsky kremlin walls in the background",
            "Solovetsky island wooden chapels behind",
        ],
        clothing_default=(
            "fitted soft-shell jacket over a flannel shirt, sturdy trousers, "
            "hiking boots, knit beanie, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted fleece over a base layer, sturdy trousers, hiking boots",
            "fitted technical jacket over a flannel shirt, sturdy trousers, boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_COASTAL + ["light sea mist along the shore"],
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm contemplative gaze, soft warm smile, attentive pilgrim eyes."
        ),
        winter_clothing={
            "male": (
                "heavy insulated jacket over a fleece, sturdy winter trousers, "
                "winter hiking boots, knit beanie"
            ),
            "female": (
                "heavy insulated jacket over a fleece, sturdy winter trousers, "
                "winter hiking boots, knit beanie"
            ),
            "neutral": (
                "heavy insulated jacket over a fleece, sturdy winter trousers, "
                "winter hiking boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="norwegian_fjord",
        mode="dating",
        location_type="outdoor",
        label_ru="🏞 Норвежский фьорд",
        hook_ru="Обрыв над фьордом — про чувство масштаба",
        meta_param="presence",
        delta_range=(0.30, 0.50),
        unlock_after=3,
        scene=(
            "Norwegian fjord overlook with sheer cliffs and deep blue water in "
            "the background, rocky outcrop in foreground, soft afternoon light"
        ),
        scene_overrides=[
            "Norwegian fjord viewpoint with Pulpit Rock-style flat outcrop in "
            "foreground, fjord stretching to the horizon in the background",
            "Norwegian fjord village with red wooden houses in the background, "
            "stone pier in foreground, soft golden hour",
            "Norwegian fjord ridge with snow patches in foreground, distant peaks "
            "in the background, diffused overcast daylight",
        ],
        triggers=[
            "Norwegian fjord with sheer cliffs and deep blue water",
            "Pulpit Rock-style flat outcrop in foreground",
            "Norwegian fjord village with red wooden houses",
            "Norwegian fjord ridge with snow patches in foreground",
        ],
        clothing_default=(
            "fitted technical shell jacket over a fleece mid-layer, sturdy "
            "trousers, hiking boots, knit beanie, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "soft-shell jacket over a base layer, sturdy trousers, hiking boots",
            "fitted technical fleece over a thermal layer, sturdy trousers, boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_MOUNTAIN,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm awed gaze, warm satisfied smile, attentive Nordic eyes."
        ),
        winter_clothing={
            "male": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trousers, winter mountain boots, knit beanie"
            ),
            "female": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trousers, winter mountain boots, knit beanie"
            ),
            "neutral": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trousers, winter mountain boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="iceland_waterfall",
        mode="dating",
        location_type="outdoor",
        label_ru="🌊 Исландский водопад",
        hook_ru="Брызги и базальт — про драматичную природу",
        meta_param="appeal",
        delta_range=(0.30, 0.50),
        unlock_after=3,
        scene=(
            "Iceland waterfall with sheets of water falling over basalt cliffs in "
            "the background, mossy stones in foreground, soft mist in the air"
        ),
        scene_overrides=[
            "Iceland waterfall with a rainbow arc in the background, gravel path "
            "in foreground, soft afternoon light",
            "Iceland canyon waterfall with basalt columns in the background, "
            "river bank in foreground, diffused overcast daylight",
            "Iceland black sand beach with sea stacks in the background, dark "
            "sand in foreground, soft golden hour",
        ],
        triggers=[
            "Iceland waterfall over basalt cliffs",
            "Iceland waterfall with a rainbow arc",
            "Iceland canyon waterfall with basalt columns",
            "Iceland black sand beach with sea stacks",
        ],
        clothing_default=(
            "fitted technical rain shell jacket over a fleece, sturdy trousers, "
            "hiking boots, knit beanie, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "soft-shell rain jacket over a fleece, sturdy trousers, hiking boots",
            "fitted technical jacket over a thermal layer, sturdy trousers, boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_MOUNTAIN + ["light spray from the waterfall"],
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm awed gaze, warm satisfied smile, attentive explorer eyes."
        ),
        winter_clothing={
            "male": (
                "heavy insulated rain shell jacket over a fleece, insulated "
                "trousers, winter hiking boots, knit beanie"
            ),
            "female": (
                "heavy insulated rain shell jacket over a fleece, insulated "
                "trousers, winter hiking boots, knit beanie"
            ),
            "neutral": (
                "heavy insulated rain shell jacket over a fleece, insulated "
                "trousers, winter hiking boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="tuscany_vineyard",
        mode="dating",
        location_type="outdoor",
        label_ru="🍇 Тосканский виноградник",
        hook_ru="Кипарисы и холмы Тосканы — про вкус к жизни",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "Tuscan vineyard with neat rows of vines in foreground, cypress-lined "
            "hill in the background, warm afternoon sunlight"
        ),
        scene_overrides=[
            "Tuscan farmhouse with cypress trees in the background, gravel "
            "driveway in foreground, soft golden hour",
            "Tuscan olive grove with silver leaves in the background, gravel path "
            "in foreground, warm afternoon sunlight",
            "Tuscan hilltop village with stone facades in the background, "
            "vineyard rows in foreground, soft evening light",
        ],
        triggers=[
            "Tuscan vineyard with neat rows of vines",
            "cypress-lined Tuscan hill in the background",
            "Tuscan farmhouse with cypress trees behind",
            "Tuscan olive grove with silver leaves",
        ],
        clothing_default=(
            "fitted linen shirt with rolled sleeves, soft chinos, leather "
            "loafers, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "soft linen blazer over a tee, light chinos, loafers",
            "fitted linen shirt under a soft cardigan, light chinos, loafers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Warm relaxed gaze, easy refined smile, attentive Mediterranean eyes."
        ),
        winter_clothing={
            "male": (
                "fitted wool overcoat over a knit, dark trousers, leather boots, "
                "soft scarf"
            ),
            "female": (
                "fitted wool overcoat over a knit, dark trousers, leather boots, "
                "soft scarf"
            ),
            "neutral": (
                "fitted wool overcoat over a knit, dark trousers, leather boots, "
                "soft scarf"
            ),
        },
    ),
    _build_style(
        style_id="chefchaouen_blue",
        mode="dating",
        location_type="outdoor",
        label_ru="🟦 Голубой Шефшауэн",
        hook_ru="Голубые лестницы — про необычный кадр",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "Chefchaouen blue-painted alley with steep stone steps in the "
            "background, blue facade in foreground, soft afternoon light"
        ),
        scene_overrides=[
            "Chefchaouen blue archway with hanging plants in the background, "
            "blue staircase in foreground, soft morning light",
            "Chefchaouen blue square with wooden door in the background, blue "
            "pavement in foreground, soft golden hour",
            "Chefchaouen rooftop with the blue city stretching out in the "
            "background, blue parapet in foreground, soft afternoon light",
        ],
        triggers=[
            "Chefchaouen blue-painted alley with steep stone steps",
            "Chefchaouen blue archway with hanging plants",
            "Chefchaouen blue square with wooden door",
            "Chefchaouen rooftop view of the blue city",
        ],
        clothing_default=(
            "fitted soft cotton shirt under a tailored linen jacket, slim trousers, "
            "leather loafers, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "fitted linen shirt with rolled sleeves, slim chinos, loafers",
            "soft cardigan over a fine tee, slim chinos, leather sneakers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Warm curious gaze, easy refined smile, attentive traveler eyes."
        ),
    ),
    _build_style(
        style_id="patagonia_trail",
        mode="dating",
        location_type="outdoor",
        label_ru="🥾 Патагонский трек",
        hook_ru="Ледник и трекинг — про дух приключений",
        meta_param="appeal",
        delta_range=(0.30, 0.50),
        unlock_after=3,
        scene=(
            "Patagonia trekking trail with the Torres del Paine spires in the "
            "background, alpine grass in foreground, soft afternoon light"
        ),
        scene_overrides=[
            "Patagonian glacier with deep blue ice in the background, gravel path "
            "in foreground, diffused overcast daylight",
            "Patagonian valley with a mirror lake in the background, alpine grass "
            "in foreground, soft golden hour",
            "Patagonian mountain pass with windswept ridges in the background, "
            "stone path in foreground, soft afternoon light",
        ],
        triggers=[
            "Patagonia Torres del Paine spires in the background",
            "Patagonian glacier with deep blue ice in the background",
            "Patagonian valley with a mirror lake",
            "Patagonian mountain pass with windswept ridges",
        ],
        clothing_default=(
            "fitted technical shell jacket over a fleece mid-layer, sturdy "
            "trekking trousers, hiking boots, knit beanie, well-fitted across the "
            "shoulders"
        ),
        clothing_allowed=[
            "soft-shell jacket over a base layer, sturdy trousers, hiking boots",
            "fitted technical fleece over a thermal layer, sturdy trousers, boots",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY,
        weather_pool=_WEATHER_MOUNTAIN,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Calm exhilarated gaze, warm satisfied smile, attentive explorer eyes."
        ),
        winter_clothing={
            "male": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trekking trousers, winter mountain boots, knit beanie"
            ),
            "female": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trekking trousers, winter mountain boots, knit beanie"
            ),
            "neutral": (
                "heavy insulated alpine jacket over a fleece mid-layer, insulated "
                "trekking trousers, winter mountain boots, knit beanie"
            ),
        },
    ),
    _build_style(
        style_id="provence_lavender",
        mode="dating",
        location_type="outdoor",
        label_ru="💜 Лавандовые поля Прованса",
        hook_ru="Лавандовые ряды — про эстетику и нежность",
        meta_param="appeal",
        delta_range=(0.25, 0.45),
        unlock_after=2,
        scene=(
            "Provence lavender field with neat purple rows stretching to the "
            "horizon in the background, gravel path in foreground, warm afternoon "
            "sunlight"
        ),
        scene_overrides=[
            "Provence stone village in the background, lavender field in "
            "foreground, soft golden hour",
            "Provence sunflower field in the background, gravel path in "
            "foreground, soft afternoon light",
            "Provence olive grove with silver leaves in the background, gravel "
            "path in foreground, warm evening light",
        ],
        triggers=[
            "Provence lavender field with neat purple rows",
            "Provence stone village in the background",
            "Provence sunflower field behind",
            "Provence olive grove with silver leaves",
        ],
        clothing_default=(
            "fitted linen shirt with rolled sleeves, soft chinos, leather "
            "espadrilles, well-fitted across the shoulders"
        ),
        clothing_allowed=[
            "soft linen blazer over a tee, light chinos, espadrilles",
            "fitted linen dress shirt under a soft cardigan, light chinos, loafers",
        ],
        lighting_pool=_OUTDOOR_LIGHTING_DAY + _OUTDOOR_LIGHTING_EVENING,
        weather_pool=_WEATHER_TEMPERATE,
        tod_pool=_TOD_OUTDOOR,
        expression=(
            "Warm relaxed gaze, easy refined smile, attentive Mediterranean eyes."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def _all_new_styles() -> list[dict[str, Any]]:
    return list(_CV_STYLES) + list(_SOCIAL_STYLES) + list(_DATING_STYLES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    if not isinstance(styles, list):
        print("ERROR: data/styles.json is not a JSON array.", file=sys.stderr)
        return 2

    existing_ids: set[str] = {
        str(entry.get("id"))
        for entry in styles
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }

    added: list[str] = []
    skipped: list[str] = []
    for new in _all_new_styles():
        sid = new["id"]
        if sid in existing_ids:
            skipped.append(sid)
            continue
        styles.append(copy.deepcopy(new))
        existing_ids.add(sid)
        added.append(sid)

    print(
        f"add_60_styles: added={len(added)} skipped={len(skipped)} "
        f"styles_total={len(styles)}"
    )

    if not args.dry_run and added:
        payload = json.dumps(styles, ensure_ascii=False, indent=2) + "\n"
        _atomic_write(STYLES_PATH, payload)
        print(f"Wrote {STYLES_PATH}")

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# 2026-05 — Add 60 non-popsy styles",
        "",
        f"- Timestamp: `{timestamp}`",
        f"- Mode: `{'DRY-RUN' if args.dry_run else 'COMMIT'}`",
        f"- Added: {len(added)}",
        f"- Skipped (already present): {len(skipped)}",
        "",
        "## Added",
        "",
    ]
    for sid in sorted(added):
        lines.append(f"- `{sid}`")
    if skipped:
        lines.append("")
        lines.append("## Skipped")
        lines.append("")
        for sid in sorted(skipped):
            lines.append(f"- `{sid}`")
    lines.append("")
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Log written to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""End-to-end seed for one or more visa scenarios.

Idempotent. Updates four JSON files at once:

- ``data/scenarios.json`` — Scenario Engine entry (kind=visa)
- ``data/styles.json`` — `visa_<country>` style for the document-format catalog
- ``data/landing_content.json`` — landing page blocks for ``visa-<country>`` slug
- ``web/public/sitemap.xml`` — append ``/visa/<country>`` if missing

The visa source spec lives in ``data/visa_requirements.json``. Add a
new visa = one entry there + one in ``VISA_DEFINITIONS`` below + run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = REPO_ROOT / "data" / "scenarios.json"
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
LANDING_PATH = REPO_ROOT / "data" / "landing_content.json"
REQUIREMENTS_PATH = REPO_ROOT / "data" / "visa_requirements.json"
SITEMAP_PATH = REPO_ROOT / "web" / "public" / "sitemap.xml"


@dataclass(frozen=True)
class VisaDefinition:
    country: str  # e.g. "schengen"
    label_ru: str
    label_en: str
    label_short_ru: str
    icon: str
    aspect_key: str
    image_instructions: str


VISA_DEFINITIONS: list[VisaDefinition] = [
    VisaDefinition(
        country="schengen",
        label_ru="Шенгенская виза",
        label_en="Schengen visa",
        label_short_ru="Шенген",
        icon="🛂",
        aspect_key="visa_schengen",
        image_instructions=(
            "Document-grade Schengen visa portrait. Flat uniform white background "
            "(#FFFFFF, no shadows, no gradient). Neutral facial expression, mouth closed, "
            "eyes open and looking straight into the camera, head perfectly centered "
            "and frontal. Head must occupy 70-80% of frame height, framed from collarbone "
            "to slightly above the crown. No tinted glasses, no head covering (except "
            "religious). Soft, even lighting with no harsh shadows on face or background. "
            "Output color photo, ICAO 9303 compliant proportions."
        ),
    ),
    VisaDefinition(
        country="usa",
        label_ru="Виза США",
        label_en="US visa",
        label_short_ru="США",
        icon="🇺🇸",
        aspect_key="visa_us",
        image_instructions=(
            "Document-grade US visa portrait. Square 1:1 aspect ratio (51×51 mm). Plain "
            "white or off-white background, no shadows, no gradient. Neutral facial "
            "expression, mouth closed, eyes open and looking straight into the camera, "
            "head centered. Head height between 25 and 35 mm from chin to crown; eyes "
            "in the upper third of the frame. No glasses (medical only), no head covering "
            "(religious only). Soft even lighting. Color photo, ICAO 9303 compliant."
        ),
    ),
    VisaDefinition(
        country="uk",
        label_ru="Виза Великобритании",
        label_en="UK visa",
        label_short_ru="Великобритания",
        icon="🇬🇧",
        aspect_key="visa_uk",
        image_instructions=(
            "Document-grade UK visa portrait. 7:9 aspect ratio (35×45 mm). Plain "
            "light-coloured background (light grey or off-white preferred), strong "
            "contrast with the subject, no shadows. Neutral expression with mouth closed, "
            "eyes open and looking straight at the camera. Head, shoulders and upper body "
            "visible; head height 29-34 mm. No glasses (medical only) and no tinted "
            "lenses; no head covering except religious. Even lighting, color photo, "
            "ICAO 9303 compliant."
        ),
    ),
    VisaDefinition(
        country="canada",
        label_ru="Виза Канады",
        label_en="Canada visa",
        label_short_ru="Канада",
        icon="🇨🇦",
        aspect_key="visa_canada",
        image_instructions=(
            "Document-grade Canadian visa portrait. 7:9 aspect ratio (35×45 mm). "
            "Plain white or very light-coloured background, no shadows, no patterns. "
            "Neutral expression with mouth closed, full front view, head and top of "
            "shoulders visible, head square to the camera. Head height between 31 and "
            "36 mm. Non-tinted prescription glasses allowed if eyes fully visible; no "
            "sunglasses. No head covering except for religious reasons. Soft, even "
            "lighting; color photo; ICAO 9303 compliant."
        ),
    ),
    VisaDefinition(
        country="japan",
        label_ru="Виза Японии",
        label_en="Japan visa",
        label_short_ru="Япония",
        icon="🇯🇵",
        aspect_key="visa_japan",
        image_instructions=(
            "Document-grade Japan visa portrait. 1:1 aspect ratio (45×45 mm). Plain "
            "white background only — no patterns, no shadows. Neutral expression, mouth "
            "closed, eyes open, looking straight at the camera. Head centered with a "
            "small top margin (~7.5 mm). Head height 27-33 mm from chin to crown. No "
            "hat, no head covering (religious only). Sharp, evenly lit color photo at "
            "high resolution; ICAO 9303 compliant."
        ),
    ),
    VisaDefinition(
        country="china",
        label_ru="Виза Китая",
        label_en="China visa",
        label_short_ru="Китай",
        icon="🇨🇳",
        aspect_key="visa_china",
        image_instructions=(
            "Document-grade China visa portrait. Aspect ratio 33×48 mm (close to 11:16). "
            "Plain white background, no shadows, no border. Natural expression with "
            "both eyes open, mouth closed, ears visible, looking directly at the camera. "
            "Head centered, head height 28-33 mm chin-to-crown, ~3-5 mm top margin and "
            "≥7 mm below chin. Glasses only if untinted and eyes fully visible. No head "
            "covering (religious only). Color photo on matte/glossy paper; ICAO 9303 "
            "compliant."
        ),
    ),
    VisaDefinition(
        country="uae",
        label_ru="Виза ОАЭ",
        label_en="UAE visa",
        label_short_ru="ОАЭ",
        icon="🇦🇪",
        aspect_key="visa_uae",
        image_instructions=(
            "Document-grade UAE visa portrait. 43×55 mm format (~7:9). Plain white "
            "background, fully even, no shadows, no patterns or borders. Neutral "
            "expression, mouth closed, both eyes open, head centered and looking "
            "straight at the camera. Face occupies 70-80% of frame; head height "
            "32-36 mm chin-to-crown. No tinted glasses, no sunglasses. No head "
            "covering (religious only, full face visible). Even, uniform lighting. "
            "Color photo, 24-bit, ICAO 9303 compliant."
        ),
    ),
    VisaDefinition(
        country="australia",
        label_ru="Виза Австралии",
        label_en="Australia visa",
        label_short_ru="Австралия",
        icon="🇦🇺",
        aspect_key="visa_australia",
        image_instructions=(
            "Document-grade Australia visa portrait. 35-40 mm × 45-50 mm. Neutral or "
            "light-grey background, even lighting, no shadows or reflections. Hair off "
            "the face so edges are visible. Neutral expression with mouth closed and "
            "eyes open, looking straight at the camera. Head centered, head height "
            "32-36 mm chin-to-crown. No glasses (medical only, no tint, no glare). No "
            "head covering except religious; if worn, full face visible from chin to "
            "forehead. Natural skin tone, color photo, ICAO 9303 compliant."
        ),
    ),
    VisaDefinition(
        country="korea",
        label_ru="Виза Южной Кореи",
        label_en="South Korea visa",
        label_short_ru="Южная Корея",
        icon="🇰🇷",
        aspect_key="visa_korea",
        image_instructions=(
            "Document-grade South Korea visa portrait. 35×45 mm format (7:9). Plain "
            "white background, no shadows, no border, no colored elements. Neutral "
            "expression, mouth closed, both ears fully visible, hair away from face. "
            "Head centered and frontal, looking directly at the camera. Head height "
            "32-36 mm chin-to-crown. Glasses discouraged; if worn, no glare and frames "
            "must not obstruct eyes. No head covering except religious or medical. "
            "Sharp color photo at 600 DPI; ICAO 9303 compliant."
        ),
    ),
    VisaDefinition(
        country="india",
        label_ru="Виза Индии",
        label_en="India visa",
        label_short_ru="Индия",
        icon="🇮🇳",
        aspect_key="visa_india",
        image_instructions=(
            "Document-grade India visa portrait. Square 51×51 mm (1:1). Plain white "
            "or very light coloured background, no shadows. Color photograph, full "
            "front view with both eyes open, mouth closed, natural expression. Head "
            "centered and fully visible: top of hair to bottom of chin, ears, forehead "
            "and chin all visible. Head height 25-35 mm chin-to-crown. No head covering "
            "except religious or medical. No edits or marks. ICAO 9303 compliant."
        ),
    ),
]


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _update_scenarios(visas: list[VisaDefinition], reqs: dict) -> list[str]:
    data = _load_json(SCENARIOS_PATH)
    assert isinstance(data, dict)
    bucket = data.setdefault("scenarios", {})
    added: list[str] = []
    for v in visas:
        slug = f"visa-{v.country}"
        spec = reqs["visas"].get(v.country)
        if spec is None:
            print(f"[skip] missing requirements for {v.country}")
            continue
        if slug in bucket:
            continue
        scenario = {
            "kind": "visa",
            "api_mode": "cv",
            "pipeline_profile": "simple",
            "step3_mode": "document_formats",
            "output_spec": {
                "size_mm": spec.get("size_mm"),
                "dpi": spec.get("dpi", 300),
                "background_color": spec.get("background_color", "#FFFFFF"),
                "head_height_mm": spec.get("head_height_mm"),
                "aspect_key": v.aspect_key,
            },
            "requirements": {
                "expression": spec.get("expression", "neutral"),
                "glasses": spec.get("glasses", "forbidden"),
                "head_covering": spec.get(
                    "head_covering", "forbidden_except_religious"
                ),
                "background": spec.get("background_options", ["plain_white"])[0],
                "shadows": spec.get("shadows", "forbidden"),
                "compliance_source": spec.get("compliance_source", ""),
            },
            "prompt_overrides": {
                "analysis_checklist": _build_checklist(v, spec),
                "image_instructions": v.image_instructions,
            },
            "paywall": {"pack_qty": 5, "show_paywall": True},
            "landing_slug": slug,
            "enabled": True,
            "extra": {
                "simplified_analysis": True,
                "primary_cta_main_app": True,
                "hide_category_tabs": True,
                "scores_category": "cv",
                "country_slug": v.country,
                "country_label_ru": v.label_short_ru,
                "country_label_en": spec.get("country_label_en", ""),
            },
        }
        bucket[slug] = scenario
        added.append(slug)
    _save_json(SCENARIOS_PATH, data)
    return added


def _build_checklist(v: VisaDefinition, spec: dict) -> list[str]:
    size = spec.get("size_mm") or [0, 0]
    head = spec.get("head_height_mm") or [0, 0]
    bg = ", ".join(spec.get("background_options", ["plain_white"]))
    glasses = {
        "forbidden": "не разрешены",
        "forbidden_except_medical": "только по медицинским показаниям",
        "no_tinted": "без тонировки и бликов",
        "allowed": "разрешены, без бликов",
    }.get(spec.get("glasses", "forbidden"), "не разрешены")
    return [
        f"Размер {size[0]}×{size[1]} мм; цветная фотография.",
        f"Голова {head[0]}-{head[1]} мм по высоте (от подбородка до макушки).",
        f"Фон: {bg.replace('_', ' ')}; без теней и узоров.",
        "Нейтральное выражение, рот закрыт, глаза открыты, прямой взгляд в камеру.",
        f"Очки: {glasses}. Головной убор — только по религиозным причинам.",
        f"Фотография сделана не более {spec.get('recency_months', 6)} месяцев назад.",
    ]


def _update_styles(visas: list[VisaDefinition]) -> list[str]:
    raw = _load_json(STYLES_PATH)
    arr = raw if isinstance(raw, list) else raw.get("styles", [])
    existing = {s.get("id") for s in arr if isinstance(s, dict)}
    added: list[str] = []
    for v in visas:
        sid = f"visa_{v.country}"
        if sid in existing:
            continue
        style = {
            "id": sid,
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
            "display_label": f"{v.icon} {v.label_short_ru}",
            "hook_text": v.label_ru,
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
            "scenario": f"visa-{v.country}",
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
        arr.append(style)
        added.append(sid)
    payload = arr if isinstance(raw, list) else {**raw, "styles": arr}
    _save_json(STYLES_PATH, payload)
    return added


def _update_landings(visas: list[VisaDefinition]) -> list[str]:
    data = _load_json(LANDING_PATH)
    assert isinstance(data, dict)
    pages = data.setdefault("pages", {})
    added: list[str] = []
    for v in visas:
        slug = f"visa-{v.country}"
        if slug in pages:
            continue
        pages[slug] = {
            "blocks": [
                {
                    "id": "hero",
                    "type": "hero",
                    "enabled": True,
                    "data": {
                        "icon": v.icon,
                        "title": f"Фото на {v.label_ru.lower()}",
                        "gradient_phrase": "по официальным требованиям",
                        "lead": (
                            f"Идеальное фото на {v.label_ru.lower()} за 2 минуты — "
                            "ровный фон, правильный размер и нейтральное выражение, "
                            "по стандарту ICAO 9303."
                        ),
                        "cta_label": "Создать фото — 199 ₽",
                        "cta_microcopy": "5 фото в пакете",
                    },
                },
                {
                    "id": "proof-counter",
                    "type": "proof_counter",
                    "enabled": True,
                    "data": {
                        "heading": "Тысячи готовых фото на визы",
                        "subheading": (
                            "Пользователи делают визовые фото из дома, "
                            "без поездки в студию."
                        ),
                    },
                },
                {
                    "id": "how-it-works",
                    "type": "how_it_works",
                    "enabled": True,
                    "data": {
                        "title": "Как это работает",
                        "steps": [
                            {
                                "num": "1",
                                "title": "Загрузите фото",
                                "desc": (
                                    "Любое фото с чётким лицом, без фильтров и "
                                    "крупным планом — мы проверим автоматически."
                                ),
                            },
                            {
                                "num": "2",
                                "title": "Проверка по требованиям",
                                "desc": (
                                    f"Сверим фото с официальными требованиями "
                                    f"{v.label_ru.lower()}: размер, фон, мимика."
                                ),
                            },
                            {
                                "num": "3",
                                "title": "Создаём визовое фото",
                                "desc": (
                                    "Автоматически выровняем фон, размер и "
                                    "пропорции под стандарт ICAO 9303."
                                ),
                            },
                            {
                                "num": "4",
                                "title": "Скачайте JPG",
                                "desc": (
                                    "Получите готовое фото в нужном формате, "
                                    "экономя поход в фотосалон."
                                ),
                            },
                        ],
                    },
                },
                {
                    "id": "final-cta",
                    "type": "final_cta",
                    "enabled": True,
                    "data": {
                        "brand_heading": f"{v.icon} {v.label_ru}",
                        "h2": "Готовы создать фото?",
                        "lead": (
                            "Загрузите любое фото — получим результат, "
                            "соответствующий требованиям визы."
                        ),
                        "cta_signed_in_label": "Открыть приложение",
                        "cta_anonymous_label": "Получить доступ",
                    },
                },
                {
                    "id": "scenario-pricing",
                    "type": "scenario_pricing",
                    "enabled": True,
                    "data": {
                        "tagline": "Один пакет — фото на визу и любой документ"
                    },
                },
            ]
        }
        added.append(slug)
    _save_json(LANDING_PATH, data)
    return added


def _update_sitemap(visas: list[VisaDefinition]) -> list[str]:
    text = SITEMAP_PATH.read_text(encoding="utf-8")
    added: list[str] = []
    for v in visas:
        url = f"https://ailookstudio.ru/visa/{v.country}"
        if url in text:
            continue
        block = (
            f"  <url>\n"
            f"    <loc>{url}</loc>\n"
            f"    <changefreq>weekly</changefreq>\n"
            f"    <priority>0.9</priority>\n"
            f"  </url>\n"
        )
        text = re.sub(r"</urlset>\s*$", block + "</urlset>\n", text, count=1)
        added.append(url)
    if added:
        SITEMAP_PATH.write_text(text, encoding="utf-8")
    return added


def main() -> None:
    reqs = _load_json(REQUIREMENTS_PATH)
    assert isinstance(reqs, dict)
    print("scenarios:", _update_scenarios(VISA_DEFINITIONS, reqs))
    print("styles:", _update_styles(VISA_DEFINITIONS))
    print("landings:", _update_landings(VISA_DEFINITIONS))
    print("sitemap:", _update_sitemap(VISA_DEFINITIONS))


if __name__ == "__main__":
    main()

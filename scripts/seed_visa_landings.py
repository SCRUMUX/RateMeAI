"""Seed Visa landing pages into ``data/landing_content.json``.

Idempotent: re-running keeps existing page contents untouched (admin
edits via /admin/landing/pages take precedence).

Usage:
    python scripts/seed_visa_landings.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LANDING_PATH = REPO_ROOT / "data" / "landing_content.json"


VISAS: list[dict[str, object]] = [
    {
        "slug": "visa-schengen",
        "icon": "🛂",
        "country_label": "Шенгенская виза",
        "country_label_en": "Schengen visa",
        "size": "35×45 мм",
        "lead": (
            "Идеальное фото на шенгенскую визу за 2 минуты. Размер 35×45 мм, "
            "ровный белый фон, нейтральное выражение, голова 32–36 мм по высоте."
        ),
        "lead_en": (
            "Schengen visa photo in 2 minutes. 35×45 mm size, plain white "
            "background, neutral expression, 32–36 mm head height."
        ),
    }
]


def _build_page(visa: dict[str, object]) -> dict[str, object]:
    icon = visa["icon"]
    label = visa["country_label"]
    size = visa["size"]
    lead = visa["lead"]
    return {
        "blocks": [
            {
                "id": "hero",
                "type": "hero",
                "enabled": True,
                "data": {
                    "icon": icon,
                    "title": f"Фото на {label.lower()}",
                    "gradient_phrase": f"{size}, по стандартам ICAO",
                    "lead": lead,
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
                                "Сверим фото с официальными требованиями "
                                f"{label.lower()}: размер, фон, мимика."
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
                    "brand_heading": f"{icon} {label}",
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
                    "tagline": "Один пакет — фото на визу и любой документ",
                },
            },
        ]
    }


def main() -> None:
    data = json.loads(LANDING_PATH.read_text(encoding="utf-8"))
    pages = data.setdefault("pages", {})
    added: list[str] = []
    for visa in VISAS:
        slug = str(visa["slug"])
        if slug in pages:
            continue
        pages[slug] = _build_page(visa)
        added.append(slug)
    if not added:
        print("nothing to seed — visa landings already exist")
        return
    LANDING_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"seeded {len(added)} visa landing(s): {', '.join(added)}")


if __name__ == "__main__":
    main()

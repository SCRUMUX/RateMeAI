"""Enhancement Advisor — generates improvement suggestions with predictive metrics.

Accepts hidden analysis results and produces:
- 3 concrete enhancement suggestions with fractional predicted metrics
- 2 best-fit style options for binary choice
- Engagement-depth-aware progression
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnhancementSuggestion:
    action: str
    effect: str
    predicted_delta: float

    @property
    def line(self) -> str:
        return f"{self.action} \u2192 {self.effect} (+{self.predicted_delta:.2f})"


@dataclass(frozen=True)
class StyleOption:
    key: str
    label: str
    callback_data: str


@dataclass
class EnhancementPreview:
    suggestions: list[EnhancementSuggestion] = field(default_factory=list)
    option_a: StyleOption | None = None
    option_b: StyleOption | None = None
    mode: str = ""
    depth: int = 1

    @property
    def suggestions_text(self) -> str:
        lines = []
        for s in self.suggestions[:3]:
            lines.append(f"\u2022 {s.line}")
        return "\n".join(lines)


_ENHANCEMENT_ACTIONS: dict[str, list[dict]] = {
    "dating": [
        {"action": "Мягкий направленный свет", "effect": "подчеркнёт черты лица", "base": 0.58},
        {"action": "Коррекция тона кожи", "effect": "добавит свежести и здорового вида", "base": 0.41},
        {"action": "Тёплая цветовая гамма", "effect": "создаст располагающее впечатление", "base": 0.36},
        {"action": "Стильный фон", "effect": "усилит атмосферу уверенности", "base": 0.62},
        {"action": "Чистые линии одежды", "effect": "добавит ухоженности", "base": 0.47},
        {"action": "Мягкое боке на фоне", "effect": "сфокусирует внимание на тебе", "base": 0.33},
    ],
    "cv": [
        {"action": "Профессиональное освещение", "effect": "усилит восприятие компетентности", "base": 0.73},
        {"action": "Нейтральный деловой фон", "effect": "добавит серьёзности", "base": 0.52},
        {"action": "Структурированный стиль одежды", "effect": "повысит доверие", "base": 0.64},
        {"action": "Ровный тон кожи", "effect": "добавит уверенности в образе", "base": 0.38},
        {"action": "Чёткий контур причёски", "effect": "усилит профессиональный вид", "base": 0.44},
        {"action": "Спокойное выражение", "effect": "создаст впечатление надёжности", "base": 0.56},
    ],
    "social": [
        {"action": "Яркая цветовая палитра", "effect": "привлечёт внимание в ленте", "base": 0.67},
        {"action": "Трендовое освещение", "effect": "добавит современности", "base": 0.54},
        {"action": "Стильный фон", "effect": "создаст запоминающийся кадр", "base": 0.48},
        {"action": "Чистая кожа и свежий вид", "effect": "усилит визуальный эффект", "base": 0.42},
        {"action": "Модная обработка", "effect": "повысит вовлечённость аудитории", "base": 0.59},
        {"action": "Контрастные акценты", "effect": "выделит из массы контента", "base": 0.37},
    ],
}

_STYLE_OPTIONS: dict[str, list[dict]] = {
    "dating": [
        {"key": "warm_outdoor", "label": "Тёплый уличный"},
        {"key": "studio_elegant", "label": "Студийный элегант"},
        {"key": "cafe", "label": "Уютное кафе"},
    ],
    "cv": [
        {"key": "corporate", "label": "Строгий корпоративный"},
        {"key": "creative", "label": "Креативный"},
        {"key": "neutral", "label": "Нейтральный фон"},
    ],
    "social": [
        {"key": "influencer", "label": "Инфлюенсер"},
        {"key": "luxury", "label": "Luxury"},
        {"key": "casual", "label": "Casual lifestyle"},
        {"key": "artistic", "label": "Арт-стиль"},
    ],
}

_DEPTH_LABELS: dict[str, dict[int, list[dict]]] = {
    "dating": {
        2: [
            {"key": "confident", "label": "Уверенный взгляд"},
            {"key": "charismatic", "label": "Магнетичный образ"},
        ],
        3: [
            {"key": "studio_elegant", "label": "Контрастный студийный свет"},
            {"key": "cafe", "label": "Мягкий дневной свет"},
        ],
    },
    "cv": {
        2: [
            {"key": "corporate", "label": "Максимум доверия"},
            {"key": "creative", "label": "Креативная подача"},
        ],
        3: [
            {"key": "neutral", "label": "Нейтральный академический"},
            {"key": "corporate", "label": "Корпоративный строгий"},
        ],
    },
    "social": {
        2: [
            {"key": "luxury", "label": "Premium эстетика"},
            {"key": "influencer", "label": "Яркий инфлюенсер"},
        ],
        3: [
            {"key": "artistic", "label": "Арт-направление"},
            {"key": "casual", "label": "Естественный лайфстайл"},
        ],
    },
}


def _vary_delta(base: float, seed: str) -> float:
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    offset = ((h % 20) - 10) / 100.0
    val = round(base + offset, 2)
    return max(0.11, min(0.89, val))


def build_enhancement_preview(
    mode: str,
    analysis_result: dict,
    user_id: int,
    depth: int = 1,
    current_style: str = "",
) -> EnhancementPreview:
    from src.orchestrator.enhancement_matrix import level_for_depth

    actions = _ENHANCEMENT_ACTIONS.get(mode, _ENHANCEMENT_ACTIONS["dating"])
    seed_base = f"{user_id}:{mode}:{depth}"
    lvl = level_for_depth(depth)

    start_idx = ((depth - 1) * 3) % len(actions)
    selected = []
    for i in range(3):
        a = actions[(start_idx + i) % len(actions)]
        base_val = a["base"] * (1.0 + (lvl.level - 1) * 0.1)
        delta = _vary_delta(min(base_val, 0.95), f"{seed_base}:{i}")
        selected.append(EnhancementSuggestion(
            action=a["action"],
            effect=a["effect"],
            predicted_delta=delta,
        ))
    selected.sort(key=lambda s: s.predicted_delta, reverse=True)

    if depth >= 2:
        depth_options = _DEPTH_LABELS.get(mode, {}).get(
            min(depth, max(_DEPTH_LABELS.get(mode, {}).keys(), default=2)),
            _DEPTH_LABELS.get(mode, {}).get(2, []),
        )
    else:
        depth_options = []

    if depth_options and len(depth_options) >= 2:
        pair = depth_options[:2]
    else:
        all_opts = _STYLE_OPTIONS.get(mode, _STYLE_OPTIONS["dating"])
        filtered = [o for o in all_opts if o["key"] != current_style]
        if len(filtered) < 2:
            filtered = all_opts
        pair = filtered[:2]

    option_a = StyleOption(
        key=pair[0]["key"],
        label=pair[0]["label"],
        callback_data=f"style:{mode}:{pair[0]['key']}",
    )
    option_b = StyleOption(
        key=pair[1]["key"],
        label=pair[1]["label"],
        callback_data=f"style:{mode}:{pair[1]['key']}",
    )

    return EnhancementPreview(
        suggestions=selected,
        option_a=option_a,
        option_b=option_b,
        mode=mode,
        depth=depth,
    )

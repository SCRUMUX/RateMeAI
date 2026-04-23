"""Enhancement Advisor — generates style suggestions linked to actual catalog styles.

Picks styles from STYLE_CATALOG and uses their hook_text for suggestion copy,
ensuring text and buttons always reference the same styles.
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
    style_key: str
    predicted_param: str = ""
    predicted_delta: float = 0.0

    @property
    def line(self) -> str:
        base = f"{self.action} \u2014 {self.effect}"
        if self.predicted_param and self.predicted_delta > 0:
            display = _PARAM_DISPLAY.get(self.predicted_param, self.predicted_param)
            base += f"  {display} +{self.predicted_delta:.2f}"
        return base


_PARAM_DISPLAY: dict[str, str] = {
    "warmth": "\u2600\ufe0f к теплоте",
    "presence": "\u26a1 к уверенности",
    "appeal": "\u2728 к привлекательности",
}


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


def _pick_random_styles(
    mode: str,
    current_style: str,
    seed: str,
    count: int = 2,
    exclude: set[str] | None = None,
) -> list[dict]:
    """Pick `count` deterministic-random styles from STYLE_CATALOG.

    Excludes `current_style` and any keys in `exclude` (already used styles).
    Returns dicts with keys: key, label, hook.
    """
    from src.bot.keyboards import STYLE_CATALOG

    catalog = STYLE_CATALOG.get(mode, [])
    skip = {current_style} if current_style else set()
    if exclude:
        skip |= exclude

    filtered = [(k, lbl, hook, meta) for k, lbl, hook, meta in catalog if k not in skip]
    if len(filtered) < count:
        filtered = [
            (k, lbl, hook, meta) for k, lbl, hook, meta in catalog if k != current_style
        ]
    if len(filtered) < count:
        filtered = list(catalog)

    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    start = h % len(filtered)
    picked: list[dict] = []
    for i in range(count):
        idx = (start + i) % len(filtered)
        key, label, hook, meta = filtered[idx]
        picked.append({"key": key, "label": label, "hook": hook, "meta": meta})
    return picked


def predict_style_delta(meta: dict, user_id: int, mode: str) -> tuple[str, float]:
    """Return (perception_param_name, predicted_delta) for a style."""
    param = meta.get("param", "appeal")
    lo, hi = meta.get("delta_range", (0.15, 0.30))
    h = int(hashlib.md5(f"{user_id}:{mode}:{param}".encode()).hexdigest()[:6], 16)
    frac = (h % 100) / 100.0
    delta = round(lo + (hi - lo) * frac, 2)
    return param, delta


def build_enhancement_preview(
    mode: str,
    user_id: int,
    depth: int = 1,
    current_style: str = "",
    exclude: set[str] | None = None,
    count: int = 2,
) -> EnhancementPreview:
    """Build a unified preview where suggestions and buttons reference the same styles."""
    seed_base = f"{user_id}:{mode}:{depth}"
    pair = _pick_random_styles(
        mode, current_style, seed_base, count=count, exclude=exclude
    )

    suggestions = []
    for p in pair:
        param, delta = predict_style_delta(p.get("meta", {}), user_id, mode)
        suggestions.append(
            EnhancementSuggestion(
                action=p["label"],
                effect=p["hook"],
                style_key=p["key"],
                predicted_param=param,
                predicted_delta=delta,
            )
        )

    option_a = None
    option_b = None
    if len(pair) >= 1:
        option_a = StyleOption(
            key=pair[0]["key"],
            label=pair[0]["label"],
            callback_data=f"style:{mode}:{pair[0]['key']}",
        )
    if len(pair) >= 2:
        option_b = StyleOption(
            key=pair[1]["key"],
            label=pair[1]["label"],
            callback_data=f"style:{mode}:{pair[1]['key']}",
        )

    return EnhancementPreview(
        suggestions=suggestions,
        option_a=option_a,
        option_b=option_b,
        mode=mode,
        depth=depth,
    )

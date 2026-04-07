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

    @property
    def line(self) -> str:
        return f"{self.action} \u2014 {self.effect}"


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

    filtered = [(k, lbl, hook) for k, lbl, hook in catalog if k not in skip]
    if len(filtered) < count:
        filtered = [(k, lbl, hook) for k, lbl, hook in catalog if k != current_style]
    if len(filtered) < count:
        filtered = list(catalog)

    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    start = h % len(filtered)
    picked: list[dict] = []
    for i in range(count):
        idx = (start + i) % len(filtered)
        key, label, hook = filtered[idx]
        picked.append({"key": key, "label": label, "hook": hook})
    return picked


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
    pair = _pick_random_styles(mode, current_style, seed_base, count=count, exclude=exclude)

    suggestions = [
        EnhancementSuggestion(
            action=p["label"],
            effect=p["hook"],
            style_key=p["key"],
        )
        for p in pair
    ]

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

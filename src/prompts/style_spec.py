"""Style specification types, validation, and registry for image generation prompts.

Every generation style is represented as a StyleSpec — a typed, validated dataclass
that enforces consistent prompt structure across all modes and styles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


DepthOfField = Literal["deep", "shallow"]


@dataclass
class StyleSpec:
    """Typed specification for a single image-generation style."""

    key: str
    mode: str  # dating | cv | social

    background: str
    clothing_male: str
    clothing_female: str
    lighting: str
    expression: str

    props: str = ""
    camera_note: str = ""
    complexity: str = "simple"  # simple | medium | complex
    edit_compatible: bool = True
    depth_of_field: DepthOfField = "deep"

    def clothing_for(self, gender: str = "male") -> str:
        return self.clothing_female if gender == "female" else self.clothing_male

    def depth_of_field_prompt(self) -> str:
        if self.depth_of_field == "shallow":
            return "natural shallow depth of field, pleasant gentle background bokeh"
        return (
            "entire frame in sharp focus from foreground to background, "
            "background details fully resolved, no bokeh, no defocus blur"
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_BANNED_PHRASES = [
    "abstract", "eclectic mix", "unconventional style",
    "bold patterns", "unique layering", "flowing fabrics",
]

# Whitelist of allowed "no X" fragments used in specific document/studio styles
# where a short negative constraint is genuinely clearer than a positive
# rewrite (e.g. "no patterns", "no headwear"). Everything else matched by
# `_NEGATIVE_RE` counts as a quality warning.
_ALLOWED_NEGATIVES = frozenset({
    "no shadows",
    "no gradient",
    "no patterns",
    "no logos",
    "no headwear",
    "no uniform",
    "no makeup",
    "no accessories",
    "no texture",
    "no clutter",
    "no smile",
    "no expression",
    "no strong",
    "no heavy",
    "no artistic",
    "no background",  # e.g. "no background blur"
    "no cinematic",
    "no defocus",
    "no bokeh",
    "no branches",
})

_NEGATIVE_RE = re.compile(r"\bno\s+[a-z-]+", re.IGNORECASE)


def _has_disallowed_negative(text: str) -> bool:
    for match in _NEGATIVE_RE.findall(text):
        if match.lower() not in _ALLOWED_NEGATIVES:
            return True
    return False


def validate_style(spec: StyleSpec) -> list[str]:
    """Return a list of quality warnings for a style spec."""
    warnings: list[str] = []

    for fname in ("background", "clothing_male", "clothing_female", "expression"):
        if not getattr(spec, fname, "").strip():
            warnings.append(f"{spec.key}: empty {fname}")

    for fname in ("background", "clothing_male", "clothing_female", "lighting"):
        text = getattr(spec, fname, "").lower()
        for phrase in _BANNED_PHRASES:
            if phrase in text:
                warnings.append(f"{spec.key}.{fname}: banned phrase '{phrase}'")
        if _has_disallowed_negative(text):
            warnings.append(f"{spec.key}.{fname}: negative framing detected")

    return warnings


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class StyleRegistry:
    """Central store of all StyleSpec instances with lookup and backward-compat helpers."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], StyleSpec] = {}

    def register(self, spec: StyleSpec) -> None:
        self._by_key[(spec.mode, spec.key)] = spec

    def get(self, mode: str, key: str) -> StyleSpec | None:
        return self._by_key.get((mode, key))

    def get_or_default(self, mode: str, key: str) -> StyleSpec:
        spec = self.get(mode, key)
        if spec is not None:
            return spec
        defaults = {"dating": "warm_outdoor", "cv": "corporate", "social": "influencer"}
        default_key = defaults.get(mode, "warm_outdoor")
        fallback = self._by_key.get((mode, default_key))
        if fallback is not None:
            return fallback
        return next(iter(self._by_key.values()))

    def keys_for_mode(self, mode: str) -> list[str]:
        return [k for (m, k) in self._by_key if m == mode]

    def all_for_mode(self, mode: str) -> list[StyleSpec]:
        return [s for (m, _), s in self._by_key.items() if m == mode]

    def style_dict(self, mode: str) -> dict[str, str]:
        """Backward-compat: {key: 'Background: ... Clothing: ...'} dict."""
        return {
            s.key: f"Background: {s.background}. Clothing: {s.clothing_male}."
            for s in self.all_for_mode(mode)
        }

    def personality_dict(self, mode: str) -> dict[str, str]:
        """Backward-compat: {key: expression_text} dict."""
        return {s.key: s.expression for s in self.all_for_mode(mode)}

    def validate_all(self) -> list[str]:
        warnings: list[str] = []
        for spec in self._by_key.values():
            warnings.extend(validate_style(spec))
        return warnings

    def __len__(self) -> int:
        return len(self._by_key)


# ---------------------------------------------------------------------------
# Legacy migration helpers
# ---------------------------------------------------------------------------

def parse_legacy_style(text: str) -> tuple[str, str]:
    """Split legacy 'Background: ... Clothing: ...' string into (background, clothing)."""
    if "Background:" in text and "Clothing:" in text:
        parts = text.split("Clothing:", 1)
        bg = parts[0].replace("Background:", "", 1).strip().rstrip(". ")
        cl = parts[1].strip().rstrip(". ")
        return bg, cl
    return text.strip(), ""


def extract_lighting(background: str) -> str:
    """Extract lighting-related phrases from a background description."""
    keywords = [
        "golden-hour", "golden hour", "backlight", "rim light", "soft light",
        "warm light", "natural light", "daylight", "tungsten", "ambient light",
        "directional light", "overhead lighting", "even lighting", "soft diffused",
        "window light", "morning light", "candlelight", "neon", "ring light",
        "blue hour", "warm ambient", "spotlight", "track lighting", "lamp light",
    ]
    found = [kw for kw in keywords if kw.lower() in background.lower()]
    return ", ".join(found[:3]) if found else "warm natural light"


def adapt_female_clothing(male: str) -> str:
    """Generate a reasonable female clothing variant from a male description."""
    r = male

    _full = [
        ("fitted swim trunks, athletic build, optional sunglasses in hand",
         "elegant one-piece swimsuit, optional sunglasses, light sarong"),
        ("swim trunks", "elegant swimsuit"),
        ("compression shirt", "fitted athletic top"),
        ("athletic tank top", "fitted athletic top"),
        ("crew-neck t-shirt", "fitted crew-neck top"),
        ("crew-neck tee", "fitted crew-neck top"),
        ("band tee or flannel shirt", "vintage blouse or fitted flannel"),
        ("white crew-neck t-shirt", "white fitted top"),
        # Handle tie-or-scarf collocations before the word-level swaps
        # below, so we don't end up with redundant fragments like
        # "statement necklace or silk scarf".
        ("subtle tie or silk scarf", "delicate necklace or silk scarf"),
        ("conservative tie or silk scarf", "elegant silk scarf"),
        ("power tie or silk scarf", "statement necklace or silk scarf"),
    ]
    for old, new in _full:
        r = r.replace(old, new)

    _word = [
        ("casual shirt", "casual blouse"),
        ("dark shirt", "dark blouse"),
        ("fitted dark shirt", "fitted dark blouse"),
        ("clean fitted shirt", "clean fitted blouse"),
        ("fitted shirt", "fitted blouse"),
        ("quality shirt", "quality blouse"),
        ("dress shirt", "silk blouse"),
        ("plain tee", "fitted top"),
        ("plain tee,", "fitted top,"),
        ("black tee", "black fitted top"),
        ("over tee,", "over top,"),
        ("over tee.", "over top."),
        ("button-down", "button-down blouse"),
        ("henley", "fitted henley or silk top"),
        ("polo shirt", "fitted polo or silk top"),
        ("subtle tie", "delicate necklace"),
        ("power tie", "statement necklace"),
        ("conservative tie", "elegant silk scarf"),
        ("tie,", "silk scarf,"),
        ("pocket square", "elegant brooch"),
        ("cufflinks", "delicate bracelet"),
        ("apron over casual shirt", "apron over casual top"),
        ("linen shirt", "linen blouse or dress"),
        ("flannel shirt", "flannel or knit top"),
    ]
    for old, new in _word:
        r = r.replace(old, new)

    return r


_SHALLOW_DOF_KEYWORDS = (
    "bokeh", "blurred background", "blurred city lights", "softly blurred",
    "soft bokeh", "out of focus", "soft out-of-focus", "defocused",
)


def detect_depth_of_field(background: str) -> DepthOfField:
    """Guess depth_of_field from a legacy background description.

    Returns 'shallow' when any bokeh-ish keyword is present, 'deep' otherwise.
    """
    low = (background or "").lower()
    for kw in _SHALLOW_DOF_KEYWORDS:
        if kw in low:
            return "shallow"
    return "deep"


def build_spec_from_legacy(
    key: str,
    mode: str,
    style_text: str,
    personality_text: str,
    *,
    clothing_female_override: str = "",
    lighting_override: str = "",
    edit_compatible: bool = True,
    complexity: str = "simple",
    props: str = "",
    depth_of_field: DepthOfField | None = None,
) -> StyleSpec:
    """Create a StyleSpec from a legacy dict entry plus optional overrides."""
    bg, clothing_male = parse_legacy_style(style_text)
    lighting = lighting_override or extract_lighting(bg)
    clothing_female = clothing_female_override or adapt_female_clothing(clothing_male)
    dof: DepthOfField = depth_of_field or detect_depth_of_field(bg)

    return StyleSpec(
        key=key,
        mode=mode,
        background=bg,
        clothing_male=clothing_male,
        clothing_female=clothing_female,
        lighting=lighting,
        expression=personality_text,
        props=props,
        edit_compatible=edit_compatible,
        complexity=complexity,
        depth_of_field=dof,
    )

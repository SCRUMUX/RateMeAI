"""Style specification types, validation, and registry for image generation prompts.

Every generation style is represented as a StyleSpec — a typed, validated dataclass
that enforces consistent prompt structure across all modes and styles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


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

    def clothing_for(self, gender: str = "male") -> str:
        return self.clothing_female if gender == "female" else self.clothing_male


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_BANNED_PHRASES = [
    "abstract", "eclectic mix", "unconventional style",
    "bold patterns", "unique layering", "flowing fabrics",
]

_NEGATIVE_RE = re.compile(r"\bno\s+\w+", re.IGNORECASE)


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
        if _NEGATIVE_RE.search(text):
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
        ("fitted swim trunks, clean bare torso, optional sunglasses in hand",
         "elegant one-piece swimsuit, optional sunglasses, light sarong"),
        ("fitted swim trunks, clean bare torso",
         "elegant one-piece swimsuit, light cover-up"),
        ("swim trunks", "elegant swimsuit"),
        ("clean bare torso", "fitted top"),
        ("compression shirt", "fitted athletic top"),
        ("athletic tank top", "fitted athletic top"),
        ("crew-neck t-shirt", "fitted crew-neck top"),
        ("crew-neck tee", "fitted crew-neck top"),
        ("band tee or flannel shirt", "vintage blouse or fitted flannel"),
        ("white crew-neck t-shirt", "white fitted top"),
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
        ("subtle tie", "statement necklace"),
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
) -> StyleSpec:
    """Create a StyleSpec from a legacy dict entry plus optional overrides."""
    bg, clothing_male = parse_legacy_style(style_text)
    lighting = lighting_override or extract_lighting(bg)
    clothing_female = clothing_female_override or adapt_female_clothing(clothing_male)

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
    )

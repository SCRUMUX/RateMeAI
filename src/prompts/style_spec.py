"""Style specification types, validation, and registry for image generation prompts.

Every generation style is represented as a StyleSpec — a typed, validated dataclass
that enforces consistent prompt structure across all modes and styles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


DepthOfField = Literal["deep", "shallow"]

# v1.18 generation mode — controls which provider the StyleRouter
# forwards the request to. See ``src/providers/image_gen/style_router.py``.
# - ``identity_scene``: PuLID-style face-reference text-to-image. The
#   scene is generated from scratch by the prompt; only the face is
#   preserved from the input. Dramatically cheaper and sharper on
#   face detail, but the original background is NOT kept.
# - ``scene_preserve``: edit-based generation (Seedream v4 Edit). The
#   original background, pose, and composition are kept; the model
#   only adjusts wardrobe, lighting, or other requested deltas.
#   Used for document / CV / strict social styles.
GenerationMode = Literal["identity_scene", "scene_preserve"]

# Output aspect presets used by the FLUX.2 Pro Edit provider.
# ``square_hd`` is the only 1 MP preset we use (documents — fixed
# composition, detail secondary). Everything else is a 2 MP portrait
# or landscape, set via a custom ``{width, height}`` in the provider
# so the model actually renders at the higher resolution instead of
# falling back to a preset.
OutputAspect = Literal[
    "portrait_4_3",
    "portrait_16_9",
    "square_hd",
    "landscape_4_3",
    "landscape_16_9",
]


@dataclass(frozen=True)
class StyleVariant:
    """One content-variant of a StyleSpec used to diversify generations.

    Variants are applied on top of the base StyleSpec in ``_build_mode_prompt``:
    the variant's ``scene`` overrides ``spec.background``; ``lighting`` appends
    a dedicated Lighting line; ``props`` / ``camera`` add their own lines;
    ``clothing_*_accent`` is concatenated with the gender-specific clothing
    from the base spec. Identity anchors (PRESERVE_PHOTO / QUALITY_PHOTO) are
    never varied — they stay stable to keep face reproducibility.
    """

    id: str
    scene: str
    lighting: str
    props: str = ""
    camera: str = ""
    clothing_male_accent: str = ""
    clothing_female_accent: str = ""
    weight: float = 1.0
    # v1.18 — short machine-readable token describing the *concept*
    # this variant rotates (e.g. "sunset_coast", "blue_hour_city",
    # "rainy_neon", "minimal_studio"). Used by tests + metrics to
    # verify that a style's variants are truly diverse (no duplicates)
    # and by the bot's "Другой вариант" button to avoid showing the
    # same concept twice in a row.
    concept_signature: str = ""

    def clothing_accent_for(self, gender: str = "male") -> str:
        return (
            self.clothing_female_accent if gender == "female"
            else self.clothing_male_accent
        )


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
    # Styles whose scene semantically requires a visible torso/legs (yoga
    # mat, running track, beach, swim pool, hiking trail, cycling, etc.).
    # When the user's reference is a tight head-crop selfie, FLUX Kontext
    # Pro must hallucinate the whole body — which is exactly where it
    # drifts and destroys identity. Bot uses this flag to surface a
    # pre-generation warning and give the user a choice to reupload.
    needs_full_body: bool = False
    # Output aspect preset for the image-gen provider. FLUX.2 Pro Edit
    # honours ``image_size`` with both a preset enum and a custom
    # ``{width, height}`` dict — the provider resolves the preset into
    # the correct pixel size (1 MP for documents, 2 MP for everything
    # else). See ``src/prompts/image_gen.resolve_output_size``.
    output_aspect: OutputAspect = "portrait_4_3"
    # v1.18 hybrid pipeline: chooses PuLID (identity_scene — generate
    # scene from scratch, face-locked) vs Seedream v4 Edit
    # (scene_preserve — keep original composition). Default is
    # ``identity_scene`` for creative styles; documents/CV headshots
    # override to ``scene_preserve`` via ``detect_generation_mode``.
    generation_mode: GenerationMode = "identity_scene"
    # Optional content variants that rotate via the "Другой вариант"
    # button in the bot. Document styles keep this empty — see
    # ``image_gen._DOCUMENT_STYLE_KEYS``.
    variants: tuple[StyleVariant, ...] = field(default_factory=tuple)

    def variant_by_id(self, variant_id: str) -> StyleVariant | None:
        if not variant_id or not self.variants:
            return None
        for v in self.variants:
            if v.id == variant_id:
                return v
        return None

    def clothing_for(self, gender: str = "male") -> str:
        return self.clothing_female if gender == "female" else self.clothing_male

    def depth_of_field_prompt(self) -> str:
        if self.depth_of_field == "shallow":
            return (
                "natural mid-aperture look with the subject and near scene fully sharp; "
                "only very distant light points may soften from atmospheric perspective"
            )
        return (
            "entire frame rendered in deep natural focus from the subject all the way "
            "to the background; textures, surfaces and distant objects remain crisp, "
            "legible and fully resolved"
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_BANNED_PHRASES = [
    "abstract", "eclectic mix", "unconventional style",
    "bold patterns", "unique layering", "flowing fabrics",
]

# After the 1.14.3 positive-framing refresh, no "no X" / "without X" /
# "avoid X" / "don't X" fragments are allowed anywhere in style fields —
# FLUX.1 Kontext Pro ignores negations (often rendering the opposite), so
# we force every style to be expressed in positive terms. The detector
# below hard-fails on any such token; the previous whitelist is kept as
# an empty set purely as a future-proofing hook.
_ALLOWED_NEGATIVES: frozenset[str] = frozenset()

_NEGATIVE_RE = re.compile(r"\b(?:no|without|avoid|don't)\s+[a-z-]+", re.IGNORECASE)


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

    # Walk content variants with the same positive-framing discipline.
    seen_ids: set[str] = set()
    for idx, variant in enumerate(spec.variants or ()):
        if not variant.id:
            warnings.append(f"{spec.key}.variants[{idx}]: empty id")
        elif variant.id in seen_ids:
            warnings.append(f"{spec.key}.variants[{idx}]: duplicate id '{variant.id}'")
        seen_ids.add(variant.id)

        if not variant.scene.strip():
            warnings.append(f"{spec.key}.variants[{variant.id or idx}]: empty scene")
        if not variant.lighting.strip():
            warnings.append(f"{spec.key}.variants[{variant.id or idx}]: empty lighting")

        for vf in (
            "scene", "lighting", "props", "camera",
            "clothing_male_accent", "clothing_female_accent",
        ):
            text = getattr(variant, vf, "").lower()
            if not text:
                continue
            for phrase in _BANNED_PHRASES:
                if phrase in text:
                    warnings.append(
                        f"{spec.key}.variants[{variant.id or idx}].{vf}: "
                        f"banned phrase '{phrase}'"
                    )
            if _has_disallowed_negative(text):
                warnings.append(
                    f"{spec.key}.variants[{variant.id or idx}].{vf}: "
                    f"negative framing detected"
                )

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


# Style keys whose scene composition inherently requires a visible torso
# and legs (sport / beach / pool / yoga / cycling / yacht, etc.). The set
# is hand-curated rather than inferred from the prompt text: some scenes
# read "sport" in the keywords but work fine with half-body crops
# (studio_gym, locker_room), and we'd rather miss a warning than emit
# a false-positive that confuses the user.
_NEEDS_FULL_BODY_KEYS: frozenset[str] = frozenset({
    # dating — sport / outdoor / water
    "gym_fitness",
    "running",
    "tennis",
    "swimming_pool",
    "hiking",
    "yoga_outdoor",
    "cycling",
    "beach_sunset",
    "yacht",
    "motorcycle",
    # social — mirrors of the above
    "yoga_social",
    "cycling_social",
    "in_motion",
})


def detect_needs_full_body(key: str, mode: str) -> bool:
    """Return True when the style's scene requires visible torso/legs."""
    return key in _NEEDS_FULL_BODY_KEYS


# Document styles have strict composition requirements (passport / visa /
# license). Fixed to 1 MP square so we spend less on stylistic detail
# the spec won't use anyway.
_DOCUMENT_STYLE_KEYS: frozenset[str] = frozenset({
    "photo_3x4",
    "passport_rf",
    "visa_eu",
    "visa_schengen",
    "visa_us",
    "photo_4x6",
    "driver_license",
    "doc_passport_neutral",
    "doc_visa_compliant",
    "doc_resume_headshot",
})


# Styles that MUST preserve the original photo's scene/background/
# composition. Everything else defaults to ``identity_scene`` (PuLID).
#
# Members:
#   - All document/CV styles (passport, visa, driver license, resume
#     headshot) — the user uploads a specific pose/background and the
#     crop must come from that exact photo, not a generated one.
#   - ``social_clean`` family — the user wants their own feed look,
#     not a re-imagined scene.
#   - Emoji / cutout styles — the output is placed over the user's
#     original context, so the composition must match.
#
# Any style not in this set is eligible for PuLID when the face crop
# succeeds; the router still falls back to Seedream on a ``no_face``
# crop failure (see ``src/providers/image_gen/style_router.py``).
_SCENE_PRESERVE_STYLE_KEYS: frozenset[str] = frozenset({
    # --- cv: all document styles ---
    "photo_3x4",
    "passport_rf",
    "visa_eu",
    "visa_schengen",
    "visa_us",
    "photo_4x6",
    "driver_license",
    "doc_passport_neutral",
    "doc_visa_compliant",
    "doc_resume_headshot",
    # --- social: "keep my own photo" styles ---
    "social_clean",
    "feed_clean",
    # --- emoji / cutout / sticker styles ---
    "emoji_cutout",
    "sticker_cutout",
})


def detect_generation_mode(key: str, mode: str) -> GenerationMode:
    """Return the default ``generation_mode`` for a style.

    Document styles and "keep my own photo" styles force
    ``scene_preserve``; everything else (creative dating/social scenes,
    lifestyle shots, sport, travel) defaults to ``identity_scene`` and
    goes through PuLID for a cheaper, sharper face-locked generation.
    """
    if key in _SCENE_PRESERVE_STYLE_KEYS:
        return "scene_preserve"
    # Document styles on cv mode are also caught by _DOCUMENT_STYLE_KEYS
    # (used elsewhere for sizing); keep the two sets in sync.
    if mode == "cv" and key in _DOCUMENT_STYLE_KEYS:
        return "scene_preserve"
    return "identity_scene"


def detect_output_aspect(key: str, mode: str) -> OutputAspect:
    """Pick the output aspect for a style.

    Three buckets map to our 2 MP-portrait-by-default strategy:

    - document styles → ``square_hd`` (1 MP, fixed composition)
    - full-body scenes (yoga / beach / running / ...) → ``portrait_4_3``
      (2 MP at 1280x1600, gives the face 400–500 px on its long side)
    - everything else (headshot, dating, social, cv non-doc) →
      ``portrait_4_3`` as well

    The rare landscape-composed scene (``near_car``, ``yacht``) can
    override this at the spec level; the default keeps all styles on a
    single portrait rail so thumbnails line up in the Telegram UI.
    """
    if mode == "cv" and key in _DOCUMENT_STYLE_KEYS:
        return "square_hd"
    return "portrait_4_3"


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
    variants: tuple[StyleVariant, ...] = (),
    output_aspect: OutputAspect | None = None,
    generation_mode: GenerationMode | None = None,
) -> StyleSpec:
    """Create a StyleSpec from a legacy dict entry plus optional overrides."""
    bg, clothing_male = parse_legacy_style(style_text)
    lighting = lighting_override or extract_lighting(bg)
    clothing_female = clothing_female_override or adapt_female_clothing(clothing_male)
    dof: DepthOfField = depth_of_field or detect_depth_of_field(bg)
    aspect: OutputAspect = output_aspect or detect_output_aspect(key, mode)
    gen_mode: GenerationMode = (
        generation_mode or detect_generation_mode(key, mode)
    )

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
        needs_full_body=detect_needs_full_body(key, mode),
        output_aspect=aspect,
        variants=variants,
        generation_mode=gen_mode,
    )

"""Structured 8-block prompt adapter for the v1.21 A/B path.

When the web UI selects one of the additive A/B models (Nano Banana 2
Edit or GPT Image 2 Edit) the executor bypasses
:func:`src.prompts.image_gen._build_mode_prompt` and routes through
:func:`build_structured_prompt` here.

The adapter **auto-assembles** the 8-block layout requested by the
product spec from data that already exists on :class:`StyleSpec` and
:class:`StyleVariant`. We do not touch the ~130 existing style
definitions; instead we read their fields (``scene``, ``lighting``,
``props``, ``camera``, ``clothing_*_accent``, ``expression``, ...) and
compose the structured prompt on the fly. This keeps the hybrid
pipeline bit-for-bit untouched while letting the A/B path speak in the
format both Nano Banana and GPT Image 2 prefer.

8-block layout (verbatim):

  Subject: <who/what, concise>
  Scene: <environment, context>
  Style: <aesthetic direction>
  Lighting: <natural/studio, mood, realism>
  Camera: photorealistic, DSLR, natural depth of field, realistic proportions
  Identity & Realism: <identity lock>
  Enhancement: <subtle attractiveness>
  Output: <high detail, clean composition>

On top of the shared body we emit one of two **model-specific
wrappers**:

- GPT Image 2 → ``Change: / Preserve: / Constraints:`` triptych
  (recommended by the fal.ai GPT Image 2 prompting guide, section
  "Edit one image").
- Nano Banana 2 → structured natural paragraph with an explicit
  ``Keep facial features exactly the same as the reference image.``
  identity anchor (Google / fal reference-edit best practice).
"""
from __future__ import annotations

from typing import Literal

from src.config import settings
from src.prompts.style_spec import StyleSpec, StyleVariant

ModelKey = Literal["nano_banana_2", "gpt_image_2"]


# ----------------------------------------------------------------------
# Fixed blocks — dictated by the product spec (must stay verbatim so
# tests can assert substring equality).
# ----------------------------------------------------------------------

CAMERA_BLOCK = (
    "photorealistic, DSLR, natural depth of field, realistic proportions"
)

IDENTITY_BLOCK = (
    "Maintain identity consistency with natural facial structure and "
    "realistic skin texture. Ensure the person remains clearly "
    "recognizable with a natural, lifelike appearance."
)

ENHANCEMENT_BLOCK = (
    "Subtle, realistic attractiveness improvement through lighting, "
    "skin clarity, and balanced features, without altering identity."
)

OUTPUT_BLOCK = (
    "high detail, clean composition, realistic background, coherent scene"
)

# Prepended to the Identity block for Nano Banana so the reference-edit
# sampler holds the face geometry at full fidelity.
NANO_BANANA_IDENTITY_ANCHOR = (
    "Keep facial features exactly the same as the reference image."
)

# Boilerplate for the GPT Image 2 triptych.
GPT_PRESERVE_BASE = "face, facial features, skin tone, body shape, pose"
GPT_CONSTRAINTS = (
    "no watermark, no logo drift, no extra objects, no redesign, "
    "no identity change"
)


# ----------------------------------------------------------------------
# Aesthetic hints — derived from style/mode because the legacy
# StyleSpec doesn't carry an explicit "Style" field. Keeping the table
# short and in one place means content editors can tweak aesthetics
# without re-reading the ~130 variants.
# ----------------------------------------------------------------------

_MODE_STYLE_TONE: dict[tuple[str, str], str] = {
    # dating
    ("dating", "warm_outdoor"): "warm editorial lifestyle",
    ("dating", "cozy_cafe"): "candid lifestyle, editorial warmth",
    ("dating", "urban_night"): "cinematic night lifestyle",
    ("dating", "beach_sunset"): "warm golden-hour editorial",
    ("dating", "active_lifestyle"): "editorial sports lifestyle",
    # cv
    ("cv", "corporate"): "clean corporate editorial",
    ("cv", "business_casual"): "relaxed corporate editorial",
    ("cv", "creative_studio"): "editorial creative portrait",
    # social
    ("social", "influencer"): "editorial social-media portrait",
    ("social", "feed_clean"): "clean lifestyle feed aesthetic",
    ("social", "social_clean"): "clean lifestyle feed aesthetic",
}

_DEFAULT_MODE_TONE: dict[str, str] = {
    "dating": "warm editorial lifestyle",
    "cv": "clean corporate editorial",
    "social": "editorial social-media portrait",
}


def _style_tone(mode: str, style: str) -> str:
    m = (mode or "").strip().lower()
    s = (style or "").strip().lower()
    return (
        _MODE_STYLE_TONE.get((m, s))
        or _DEFAULT_MODE_TONE.get(m)
        or "editorial portrait"
    )


# ----------------------------------------------------------------------
# Block assembly
# ----------------------------------------------------------------------


def _gender_phrase(gender: str | None) -> str:
    g = (gender or "").strip().lower()
    if g == "female":
        return "the woman in the reference photo"
    if g == "male":
        return "the man in the reference photo"
    return "the person in the reference photo"


def _subject_block(
    spec: StyleSpec,
    gender: str | None,
) -> str:
    who = _gender_phrase(gender)
    expression = (spec.expression or "").strip().rstrip(".")
    clothing = spec.clothing_for(gender or "male").strip().rstrip(".")
    pieces = [who]
    if expression:
        pieces.append(expression)
    if clothing:
        pieces.append(f"wearing {clothing}")
    return ", ".join(p for p in pieces if p)


def _scene_block(spec: StyleSpec, variant: StyleVariant | None) -> str:
    scene = ""
    if variant is not None and variant.scene:
        scene = variant.scene
    if not scene:
        scene = spec.background or ""
    extras: list[str] = []
    if variant is not None and variant.props:
        extras.append(variant.props)
    if spec.props:
        extras.append(spec.props)
    text = scene.strip().rstrip(".")
    if extras:
        text = f"{text}, {', '.join(e.strip().rstrip('.') for e in extras)}"
    return text


def _lighting_block(spec: StyleSpec, variant: StyleVariant | None) -> str:
    if variant is not None and variant.lighting:
        return variant.lighting.strip().rstrip(".")
    return (spec.lighting or "natural daylight").strip().rstrip(".")


def _camera_block(spec: StyleSpec, variant: StyleVariant | None) -> str:
    extras: list[str] = [CAMERA_BLOCK]
    dof = spec.depth_of_field_prompt().strip().rstrip(".")
    if dof:
        extras.append(dof)
    if variant is not None and variant.camera:
        extras.append(variant.camera.strip().rstrip("."))
    elif spec.camera_note:
        extras.append(spec.camera_note.strip().rstrip("."))
    return ", ".join(extras)


def _style_block(spec: StyleSpec, gender: str | None) -> str:
    tone = _style_tone(spec.mode, spec.key)
    if getattr(spec, "needs_full_body", False):
        return f"{tone}, full-body composition"
    return tone


def _compose_body(
    spec: StyleSpec,
    gender: str | None,
    variant: StyleVariant | None,
) -> dict[str, str]:
    """Return the shared 8 blocks as a dict keyed by block name."""
    return {
        "Subject": _subject_block(spec, gender),
        "Scene": _scene_block(spec, variant),
        "Style": _style_block(spec, gender),
        "Lighting": _lighting_block(spec, variant),
        "Camera": _camera_block(spec, variant),
        "Identity & Realism": IDENTITY_BLOCK,
        "Enhancement": ENHANCEMENT_BLOCK,
        "Output": OUTPUT_BLOCK,
    }


def _render_blocks(blocks: dict[str, str]) -> str:
    lines: list[str] = []
    for key, value in blocks.items():
        if not value:
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Model-specific wrappers
# ----------------------------------------------------------------------


def _wrap_nano_banana(blocks: dict[str, str]) -> str:
    """Structured natural paragraph with explicit identity anchor."""
    id_block = blocks["Identity & Realism"]
    if NANO_BANANA_IDENTITY_ANCHOR not in id_block:
        blocks = dict(blocks)
        blocks["Identity & Realism"] = (
            f"{NANO_BANANA_IDENTITY_ANCHOR} {id_block}"
        )
    return _render_blocks(blocks)


def _wrap_gpt_image_2(blocks: dict[str, str]) -> str:
    """Wrap the body in the Change / Preserve / Constraints triptych."""
    body = _render_blocks(blocks)
    change_line = ", ".join(
        p for p in (
            blocks.get("Scene", ""),
            blocks.get("Style", ""),
            blocks.get("Lighting", ""),
        ) if p
    )
    preserve_line = (
        f"{blocks.get('Identity & Realism', IDENTITY_BLOCK)} "
        f"Preserve {GPT_PRESERVE_BASE}."
    )
    suffix = (
        f"\n\nChange: {change_line}"
        f"\nPreserve: {preserve_line}"
        f"\nConstraints: {GPT_CONSTRAINTS}"
    )
    return body + suffix


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


def build_structured_prompt(
    mode: str,
    style: str,
    gender: str | None,
    variant: StyleVariant | None,
    model: ModelKey | str,
) -> str:
    """Return a structured 8-block prompt for the A/B path.

    The function is read-only with respect to the style registry — it
    receives a ``mode`` / ``style`` pair, looks the spec up on the
    global :data:`STYLE_REGISTRY`, and composes the blocks from the
    existing fields.

    ``model`` selects the outer wrapper (Nano Banana vs GPT Image 2);
    everything else is identical across models so A/B comparison stays
    apples-to-apples.
    """
    # Lazy import — STYLE_REGISTRY lives in image_gen which pulls in
    # heavy helpers. Importing at call time keeps the hybrid pipeline
    # startup path unchanged when the A/B test is off.
    from src.prompts.image_gen import STYLE_REGISTRY

    spec = STYLE_REGISTRY.get_or_default(mode, style)
    blocks = _compose_body(spec, gender, variant)

    key = (model or "").strip().lower()
    if key == "gpt_image_2":
        prompt = _wrap_gpt_image_2(blocks)
    else:
        prompt = _wrap_nano_banana(blocks)

    limit = max(200, int(getattr(settings, "ab_prompt_max_len", 1500)))
    if len(prompt) > limit:
        prompt = prompt[: limit - 1].rstrip() + "…"
    return prompt


__all__ = [
    "build_structured_prompt",
    "CAMERA_BLOCK",
    "IDENTITY_BLOCK",
    "ENHANCEMENT_BLOCK",
    "OUTPUT_BLOCK",
    "NANO_BANANA_IDENTITY_ANCHOR",
]

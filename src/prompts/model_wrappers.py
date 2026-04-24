"""Per-model prompt wrappers for StyleSpecV2.

PR1 of the style-schema-v2 migration. Converts a :class:`CompositionIR`
into the final string that goes on the wire to either GPT Image 2 Edit
or Nano Banana 2 Edit.

Design
------
The default v1 tail (PRESERVE_PHOTO_FACE_ONLY + QUALITY_PHOTO +
LIGHT_INTEGRATION_PHOTO + CAMERA_PHOTO + ANATOMY_PHOTO) is shared
between both models. Per the PR1 plan we keep it as the byte-for-byte
equivalent for styles whose v2 ``QualityBlock`` does not override it,
and introduce split constants (``QUALITY_PHOTO_GPT`` / ``QUALITY_PHOTO_NANO``)
that model-aware styles can opt into via
``QualityBlock.per_model_tail``.

Resolution order for the tail:

1. ``ir.per_model_tail_map[model]`` — explicit per-model override on
   the style. Highest priority.
2. ``ir.quality_identity_base`` — style-level common tail (falls back
   to the v1 constant block when empty).
3. Default v1 constants — kept as a single authoritative source of
   truth so a style that doesn't fill ``QualityBlock`` at all stays
   bit-for-bit identical to its v1 sibling.

Document styles bypass the whole tail and use the legacy DOC_PRESERVE /
DOC_QUALITY + composition hint block — identity fidelity requirements
there are vendor-policy, not style-policy, and have nothing to gain
from a model-specific split.
"""

from __future__ import annotations

from src.prompts import image_gen as ig
from src.prompts.composition_builder import CompositionIR


# v2 quality / identity tails. For now they are identical to the v1
# common block so the "flag on, no v2 styles" parity test passes
# byte-for-byte. A v2 style can override either one via
# ``QualityBlock.per_model_tail``; a future PR will tune them
# independently once we have the shadow-diff evidence.
QUALITY_PHOTO_GPT = " ".join(
    [
        ig.PRESERVE_PHOTO_FACE_ONLY,
        ig.QUALITY_PHOTO,
        ig.LIGHT_INTEGRATION_PHOTO,
        ig.CAMERA_PHOTO,
        ig.ANATOMY_PHOTO,
    ]
)

QUALITY_PHOTO_NANO = " ".join(
    [
        ig.PRESERVE_PHOTO_FACE_ONLY,
        ig.QUALITY_PHOTO,
        ig.LIGHT_INTEGRATION_PHOTO,
        ig.CAMERA_PHOTO,
        ig.ANATOMY_PHOTO,
    ]
)

_MODEL_DEFAULT_TAIL = {
    "gpt_image_2": QUALITY_PHOTO_GPT,
    "nano_banana_2": QUALITY_PHOTO_NANO,
}


def _resolve_tail(ir: CompositionIR, model: str) -> str:
    """Pick the right quality/identity tail for ``model``."""
    override = ir.per_model_tail_map.get(model)
    if override:
        return override
    if ir.quality_identity_base:
        return ir.quality_identity_base
    return _MODEL_DEFAULT_TAIL.get(model, QUALITY_PHOTO_GPT)


def _assemble(ir: CompositionIR, *, tail: str) -> str:
    parts: list[str] = []

    if ir.change_instruction:
        parts.append(ir.change_instruction)

    scene_line = ir.scene_line()
    if scene_line:
        parts.append(f"{scene_line}.")

    if ir.clothing:
        parts.append(f"Subject is wearing {ir.clothing}.")

    if ir.expression:
        parts.append(ir.expression)

    if ir.is_document:
        hint = ig._DOC_COMPOSITION_HINT.get(
            ir.style_key, "Centered head-and-shoulders framing."
        )
        parts.append(f"Composition: {hint}")
        parts.append(ig.DOC_PRESERVE)
        parts.append(ig.DOC_QUALITY)
    else:
        if ir.framing_line:
            parts.append(ir.framing_line)
        if tail:
            parts.append(tail)

    prompt = " ".join(p.strip() for p in parts if p and p.strip())

    try:
        from src.prompts.compression import compress_prompt

        prompt = compress_prompt(prompt)
    except ImportError:
        pass

    return ig._truncate(prompt)


def wrap_for_gpt_image_2(ir: CompositionIR) -> str:
    """Final prompt for GPT Image 2 Edit."""
    return _assemble(ir, tail=_resolve_tail(ir, "gpt_image_2"))


def wrap_for_nano_banana_2(ir: CompositionIR) -> str:
    """Final prompt for Nano Banana 2 Edit."""
    return _assemble(ir, tail=_resolve_tail(ir, "nano_banana_2"))


def wrap_for_model(ir: CompositionIR, model: str) -> str:
    """Dispatch helper used by the executor: pick the wrapper by model name."""
    if model == "nano_banana_2":
        return wrap_for_nano_banana_2(ir)
    return wrap_for_gpt_image_2(ir)

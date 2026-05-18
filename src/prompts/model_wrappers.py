"""Per-model prompt wrappers for StyleSpecV3.

v4.1 / v1.64 — single-path prompt pipeline
-------------------------------------------
Stages of the prompt:

1. ``change_instruction``                 — Google-formula opener
                                             ("Using the reference photo,
                                             render the same person in a
                                             new scene…")
2. ``_COMPOSITION_NUMERICAL_HINT``        — numerical layout target
                                             ("face fills upper X% of
                                             frame"). v1.64: mirrors the
                                             document-path hint so
                                             edit-models stop copying
                                             tight-selfie head/torso
                                             ratios verbatim. Goes
                                             BEFORE identity so layout
                                             wins attention.
3. ``IDENTITY_PRESERVE_BLOCK``            — explicit identity anchors
                                             (face shape, eye shape and
                                             colour, hairline, skin
                                             undertone). v1.64 trimmed
                                             the "head and shoulders
                                             read as real human
                                             proportions" tail because
                                             it conflicted with the
                                             numerical hint above.
4. narrative scene line                   — "<scene> lit by X during a Y
                                             morning in Z." (composed in
                                             :meth:`CompositionIR.scene_line`)
5. wardrobe                               — "Wardrobe: <clothing>."
6. ``expression``                         — natural-from-reference by
                                             default (see
                                             composition_builder.py)
7. ``framing_line``                       — short framing reminder
8. ``PHOTOREAL_BLOCK``                    — single camera/DoF block,
                                             single materiality clause,
                                             single lighting-integration
                                             clause.

Document styles use a separate vendor-policy path with DOC_PRESERVE /
DOC_QUALITY and a fixed composition hint — identity fidelity
requirements there are not negotiable. The non-document numerical
hint mirrors that approach.

Tail resolution order:

1. ``ir.per_model_tail_map[model]`` — explicit per-model override on
   the style. Highest priority. The v4 migration zeroed these out
   across ``data/styles.json``; until they are re-curated we honour
   any non-empty override.
2. ``ir.quality_identity_base`` — style-level common tail.
3. Default constants (``QUALITY_PHOTO_GPT`` / ``QUALITY_PHOTO_NANO`` /
   ``QUALITY_PHOTO_FLUX``) — ``PHOTOREAL_BLOCK`` for every model.
"""

from __future__ import annotations

from src.prompts import image_gen as ig
from src.prompts.composition_builder import CompositionIR


# v4.1 short tails. ``PHOTOREAL_BLOCK`` is the entire fixed tail;
# identity-preserve has been hoisted to the top of the prompt by
# ``_assemble``. Per-model variants kept as separate names so a future
# PR can tune wording for a single model without rebalancing others.
QUALITY_PHOTO_GPT = ig.PHOTOREAL_BLOCK
QUALITY_PHOTO_NANO = ig.PHOTOREAL_BLOCK
QUALITY_PHOTO_FLUX = ig.PHOTOREAL_BLOCK


_MODEL_DEFAULT_TAIL = {
    "gpt_image_2": QUALITY_PHOTO_GPT,
    "nano_banana_2": QUALITY_PHOTO_NANO,
    "flux_kontext": QUALITY_PHOTO_FLUX,
}


def _resolve_tail(ir: CompositionIR, model: str) -> str:
    """Pick the right quality/identity tail for ``model``."""
    override = ir.per_model_tail_map.get(model)
    if override:
        return override
    if ir.quality_identity_base:
        return ir.quality_identity_base
    return _MODEL_DEFAULT_TAIL.get(model, _MODEL_DEFAULT_TAIL["gpt_image_2"])


def _assemble(ir: CompositionIR, *, tail: str) -> str:
    """Assemble the wire-prompt from a :class:`CompositionIR`.

    v4.1: single layout — preserve-first ordering. Identity sits in the
    first third of the prompt where edit-models pay most attention;
    scene/wardrobe/expression follow; ``PHOTOREAL_BLOCK`` closes.
    Document styles use a separate vendor-policy layout because
    DOC_PRESERVE / DOC_QUALITY are not negotiable.
    """
    parts: list[str] = []

    if ir.is_document:
        if ir.change_instruction:
            parts.append(ir.change_instruction)
        scene_line = ir.scene_line()
        if scene_line:
            parts.append(f"{scene_line}.")
        if ir.clothing:
            parts.append(f"Wardrobe: {ir.clothing}.")
        if ir.expression:
            parts.append(ir.expression)
        hint = ig._DOC_COMPOSITION_HINT.get(
            ir.style_key, "Centered head-and-shoulders framing."
        )
        parts.append(f"Composition: {hint}")
        parts.append(ig.DOC_PRESERVE)
        parts.append(ig.DOC_QUALITY)
    else:
        if ir.change_instruction:
            parts.append(ir.change_instruction)

        # v1.64 — numerical composition anchor BEFORE identity. Mirrors
        # the document-path ``_DOC_COMPOSITION_HINT`` so edit-models
        # receive an explicit "face fills upper X% of frame" target and
        # stop replicating the tight-selfie head/torso ratio. Placed in
        # the first third of the prompt where edit-models pay most
        # attention.
        if ir.framing and ir.framing in ig._COMPOSITION_NUMERICAL_HINT:
            parts.append(
                f"Composition: {ig._COMPOSITION_NUMERICAL_HINT[ir.framing]}"
            )

        # Identity-preserve sits right after the layout target so the
        # face stays anchored to the reference while the body fits the
        # numerical composition.
        parts.append(ig.IDENTITY_PRESERVE_BLOCK)

        scene_line = ir.scene_line()
        if scene_line:
            parts.append(f"{scene_line}.")

        if ir.clothing:
            parts.append(f"Wardrobe: {ir.clothing}.")

        if ir.expression:
            parts.append(ir.expression)

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


def wrap_for_flux_kontext(ir: CompositionIR) -> str:
    """Final prompt for FLUX Kontext (BFL)."""
    return _assemble(ir, tail=_resolve_tail(ir, "flux_kontext"))


def wrap_for_model(ir: CompositionIR, model: str) -> str:
    """Dispatch helper used by the executor: pick the wrapper by model name."""
    if model == "nano_banana_2":
        return wrap_for_nano_banana_2(ir)
    if model == "flux_kontext":
        return wrap_for_flux_kontext(ir)
    return wrap_for_gpt_image_2(ir)

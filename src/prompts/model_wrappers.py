"""Per-model prompt wrappers for StyleSpecV3.

v4.1 / v1.65 — single-path prompt pipeline
-------------------------------------------
Stages of the prompt:

1. ``change_instruction``                 — Google-formula opener
                                             ("Using the reference photo,
                                             render the same person in a
                                             new scene…"). v1.65 appends
                                             a positive-framed proportions
                                             clause so the very first
                                             sentence carries an anatomy
                                             goal.
2. ``_COMPOSITION_NUMERICAL_HINT``        — cinematic layout directive
                                             ("Reframe the reference into
                                             a head-and-shoulders bust
                                             shot taken with an 85mm
                                             portrait lens …"). v1.65
                                             swapped percentage targets
                                             for cinematic shot
                                             vocabulary + explicit
                                             physical lens — the
                                             canonical fix for the
                                             "huge head, tiny shoulders"
                                             pathology. Goes BEFORE
                                             identity so layout wins
                                             attention.
3. ``IDENTITY_PRESERVE_BLOCK``            — 4 explicit identity anchors
                                             (face shape, eye shape and
                                             colour, hairline, skin
                                             undertone). v1.65 trimmed
                                             from 9 anchors so attention
                                             budget stays available for
                                             composition.
4. narrative scene line                   — "<scene> lit by X during a Y
                                             morning in Z." (composed in
                                             :meth:`CompositionIR.scene_line`)
5. wardrobe                               — "Wardrobe: <clothing>."
6. ``expression``                         — natural-from-reference by
                                             default (see
                                             composition_builder.py)
7. ``PHOTOREAL_BLOCK``                    — single camera/DoF block
                                             (``85mm portrait lens at
                                             chest height``), single
                                             materiality clause, single
                                             lighting-integration
                                             clause.

v1.65 removed the standalone ``framing_line`` stage from the wire
prompt: it duplicated the framing signal already delivered by
``_COMPOSITION_NUMERICAL_HINT`` and the camera setup in
``PHOTOREAL_BLOCK``. ``framing_line`` is still computed on
:class:`CompositionIR` for IR inspection / test tooling, just not
emitted into the final prompt.

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

        # v1.65 — cinematic composition anchor BEFORE identity. Mirrors
        # the document-path ``_DOC_COMPOSITION_HINT`` so edit-models
        # receive an explicit ``Reframe the reference into …`` directive
        # with cinematic shot vocabulary (``bust shot`` / ``waist-up
        # shot`` / ``full-length standing shot``) and a physical lens
        # spec (``85mm portrait lens`` / ``35mm``). This stops them
        # replicating the tight-selfie head/torso ratio. Placed in the
        # first third of the prompt where edit-models pay most
        # attention.
        if ir.framing and ir.framing in ig._COMPOSITION_NUMERICAL_HINT:
            parts.append(
                f"Composition: {ig._COMPOSITION_NUMERICAL_HINT[ir.framing]}"
            )

        # Identity-preserve sits right after the layout target so the
        # face stays anchored to the reference while the body fits the
        # cinematic composition.
        parts.append(ig.IDENTITY_PRESERVE_BLOCK)

        scene_line = ir.scene_line()
        if scene_line:
            parts.append(f"{scene_line}.")

        if ir.clothing:
            parts.append(f"Wardrobe: {ir.clothing}.")

        if ir.expression:
            parts.append(ir.expression)

        # v1.65: ``framing_line`` is no longer emitted into the wire
        # prompt. The cinematic composition hint above + the camera
        # spec in ``PHOTOREAL_BLOCK`` already carry the framing signal;
        # repeating it here gave edit-models duplicate (and sometimes
        # mildly contradictory) framing tokens. Field stays on
        # :class:`CompositionIR` for IR inspection / test tooling.

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

"""Per-model prompt wrappers for StyleSpecV3.

v1.67 — composition-first / identity-tail pipeline
---------------------------------------------------
Stages of the wire prompt (non-document styles):

1. ``change_instruction``                 — Google-formula opener
                                             ("Using the reference photo,
                                             render the same person in a
                                             new scene…").
2. ``_COMPOSITION_NUMERICAL_HINT``        — cinematic layout directive
                                             ("Reframe the reference into
                                             a head-and-shoulders bust
                                             shot taken with an 85mm
                                             short-telephoto lens …").
                                             Owns the early-attention
                                             budget that edit-models
                                             weigh heavily.
3. narrative scene line                   — "<scene> lit by X during a Y
                                             morning in Z." (composed in
                                             :meth:`CompositionIR.scene_line`)
4. wardrobe                               — "Wardrobe: <clothing>."
                                             Body-geometry cue.
5. ``expression``                         — natural-from-reference by
                                             default (see
                                             composition_builder.py).
6. ``PHOTOREAL_BLOCK``                    — single camera/DoF block
                                             (``85mm short-telephoto lens
                                             at chest height``), single
                                             materiality clause, single
                                             lighting-integration
                                             clause.
7. ``IDENTITY_PRESERVE_BLOCK``            — identity anchors at the
                                             very tail. v1.67 demoted
                                             identity from "between
                                             composition anchor and
                                             scene" to the end. Recency
                                             bias now reinforces
                                             composition, and the
                                             softened wording ("preserve
                                             the same person's facial
                                             features") stops edit-
                                             models reading "identical
                                             face shape" as a geometric
                                             instruction to copy the
                                             reference head/torso ratio.

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
    """Pick the right quality/identity tail for ``model``.

    v1.68 — P2.8: when ``settings.photoreal_by_framing_enabled`` is
    True AND the style has not supplied an explicit per-model tail
    override AND has not supplied a style-level
    ``quality_identity.base`` override, the resolver swaps the legacy
    static ``PHOTOREAL_BLOCK`` for the framing-specific entry in
    :data:`_PHOTOREAL_BY_FRAMING`. Off → legacy single-block
    behaviour, byte-for-byte unchanged.
    """
    override = ir.per_model_tail_map.get(model)
    if override:
        return override
    if ir.quality_identity_base:
        return ir.quality_identity_base
    try:
        from src.config import settings as _settings
        _photoreal_by_framing_on = bool(
            getattr(_settings, "photoreal_by_framing_enabled", False)
        )
    except Exception:
        _photoreal_by_framing_on = False
    if (
        _photoreal_by_framing_on
        and ir.framing
        and ir.framing in ig._PHOTOREAL_BY_FRAMING
    ):
        return ig._PHOTOREAL_BY_FRAMING[ir.framing]
    return _MODEL_DEFAULT_TAIL.get(model, _MODEL_DEFAULT_TAIL["gpt_image_2"])


def _assemble(ir: CompositionIR, *, tail: str) -> str:
    """Assemble the wire-prompt from a :class:`CompositionIR`.

    v1.67 — composition-first / identity-tail ordering.

    Order of stages for non-document styles:

    1. ``change_instruction`` opener (Google-formula "Using the
       reference photo, render the same person in a new scene…").
    2. ``_COMPOSITION_NUMERICAL_HINT`` — cinematic anchor (bust shot /
       waist-up / full-length) with explicit lens spec. Owns the
       early-attention budget that edit-models weigh heavily.
    3. Scene line — narrative environment.
    4. Wardrobe — explicit body geometry cue.
    5. Expression — facial expression / gaze.
    6. ``PHOTOREAL_BLOCK`` — camera, DoF, materiality, lighting.
    7. ``IDENTITY_PRESERVE_BLOCK`` — identity anchors at the very
       tail. v1.67 demoted identity from "between composition anchor
       and scene" to the end so the recency-bias channel reinforces
       composition, and so the geometric reading of "identical face
       shape" no longer overrides the composition directive.

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
            ir.style_key, "Centered framing."
        )
        parts.append(f"Composition: {hint}")
        parts.append(ig.DOC_PRESERVE)
        parts.append(ig.DOC_QUALITY)
    else:
        # v1.68 — P1.4: quantitative face-area anchor at the VERY
        # head of the prompt. Behind ``numerical_percent_anchor_enabled``
        # so Phase 2 rollout can enable it on top of the Phase 1
        # geometry fix. Document styles get their own
        # ``_DOC_COMPOSITION_HINT`` so they bypass this branch.
        if ir.framing and ir.framing in ig._FACE_AREA_ANCHOR_BY_FRAMING:
            try:
                from src.config import settings as _settings
                _anchor_on = bool(
                    getattr(_settings, "numerical_percent_anchor_enabled", False)
                )
            except Exception:
                _anchor_on = False
            if _anchor_on:
                parts.append(ig._FACE_AREA_ANCHOR_BY_FRAMING[ir.framing])

        if ir.change_instruction:
            parts.append(ir.change_instruction)

        # v1.65 — cinematic composition anchor BEFORE identity. Mirrors
        # the document-path ``_DOC_COMPOSITION_HINT`` so edit-models
        # receive an explicit ``Reframe the reference into …`` directive
        # with cinematic shot vocabulary (``bust shot`` / ``waist-up
        # shot`` / ``full-length standing shot``). v1.68 dropped the
        # in-anchor lens spec (PHOTOREAL_BLOCK owns it now). This stops
        # them replicating the tight-selfie head/torso ratio.
        #
        # v1.67 — composition anchor stays first AND is no longer
        # immediately followed by identity. The previous layout sandwiched
        # identity ("identical face shape …") between the cinematic
        # anchor and the scene/wardrobe block, which empirically pulled
        # edit-models toward copying the reference head size verbatim
        # (the "identical" token reads geometrically). Identity is now
        # demoted to the very tail of the prompt, after PHOTOREAL_BLOCK,
        # so recency bias works for composition rather than against it.
        if ir.framing and ir.framing in ig._COMPOSITION_NUMERICAL_HINT:
            parts.append(
                f"Composition: {ig._COMPOSITION_NUMERICAL_HINT[ir.framing]}"
            )

        scene_line = ir.scene_line()
        if scene_line:
            parts.append(f"{scene_line}.")

        if ir.clothing:
            parts.append(f"Wardrobe: {ir.clothing}.")

        # v1.68 — P2.10 per-framing pose hint, emitted right after
        # wardrobe (the natural slot for body-geometry directives).
        # Gated on ``settings.pose_hint_enabled``. The hint is short
        # enough to leave room for the expression line below; without
        # the flag, the wire prompt is byte-for-byte unchanged.
        if ir.framing and ir.framing in ig._POSE_BY_FRAMING:
            try:
                from src.config import settings as _settings
                _pose_hint_on = bool(
                    getattr(_settings, "pose_hint_enabled", False)
                )
            except Exception:
                _pose_hint_on = False
            if _pose_hint_on:
                parts.append(ig._POSE_BY_FRAMING[ir.framing])

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

        # v1.68 — P2.9 LIGHT_MATCH_CLAUSE. Inserted right before
        # IDENTITY_PRESERVE_BLOCK so the clause sits at the tail of
        # the prompt (recency bias) but identity still gets the very
        # last word — keeps identity preservation strictly above
        # lighting realism when the two conflict. Gated on
        # ``settings.light_match_clause_enabled``.
        try:
            from src.config import settings as _settings
            _light_match_on = bool(
                getattr(_settings, "light_match_clause_enabled", False)
            )
        except Exception:
            _light_match_on = False
        if _light_match_on:
            parts.append(ig.LIGHT_MATCH_CLAUSE)

        # v1.67 — identity-preserve at the tail. Empirical audit of
        # v1.66 generations showed that placing identity right after
        # the composition anchor leaked "identical face" into the
        # geometric channel: edit-models interpreted "identical face
        # shape" as "match the head/torso ratio of the reference",
        # which over-rode the cinematic composition directive.
        # Anchoring identity LAST keeps the strongest face-feature
        # signal close to the model's decoding step (recency bias),
        # while letting the composition directive own the early-
        # attention budget. Wording is also softened from
        # "identical face shape" to "the same person's facial
        # features" so the cue is identity-only, not geometric.
        parts.append(ig.IDENTITY_PRESERVE_BLOCK)

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

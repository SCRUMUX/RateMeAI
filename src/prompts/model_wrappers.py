"""Per-model prompt wrappers for StyleSpecV3.

v1.67 — composition-first / identity-tail pipeline
---------------------------------------------------
v1.70 — cinematic head-anchor cluster removed.
v1.71 — dead-code cleanup: ``LIGHT_MATCH_CLAUSE`` + flag retired,
        regression-marker dicts dropped, single-path assembler.

Stages of the wire prompt (non-document styles), as they ship today:

1. ``change_instruction``       — Google-formula opener
                                  ("Using the reference photo, render
                                  the same person in a new scene…").
2. narrative scene line         — "<scene> lit by X during a Y morning
                                  in Z." (composed in
                                  :meth:`CompositionIR.scene_line`).
3. wardrobe                     — "Wardrobe: <clothing>." Body-geometry
                                  cue (carries the v1.71 strong
                                  shoulder paint). v1.71.2 filters
                                  out lower-body garments / footwear
                                  when framing ≠ full_body.
4. ``_FRAMING_PROMPT_DIRECTIVES`` — explicit crop directive (v1.71.2,
                                  "Crop the frame above the chest;
                                  do not render the lower body."),
                                  emitted right after wardrobe.
5. ``_POSE_BY_FRAMING``         — relaxed-pose directive. Gated on
                                  ``settings.pose_hint_enabled``
                                  (default True since v1.69).
6. ``expression``               — natural-from-reference by default
                                  (see composition_builder.py).
7. ``DEEP_FOCUS_BLOCK``         — v1.72 anti-bokeh directive. Appended
                                  between expression and tail unless
                                  the scene line carries a shallow-DoF
                                  keyword (``_SHALLOW_DOF_KEYWORDS``).
8. ``PHOTOREAL_BLOCK``          — skin-texture + light-match anchors
                                  (lens / DoF tokens removed in v1.70).
9. ``IDENTITY_PRESERVE_BLOCK``  — identity anchors at the very tail.
                                  v1.67 demoted identity from "between
                                  composition anchor and scene" to
                                  the end so recency bias reinforces
                                  composition, and the softened wording
                                  ("preserve the same person's facial
                                  features") stops edit-models reading
                                  "identical face shape" as a geometric
                                  instruction to copy the reference
                                  head/torso ratio.

Historical anchors retired
--------------------------

* ``_COMPOSITION_NUMERICAL_HINT`` ("Reframe the reference into a
  head-and-shoulders bust shot …") — emptied in v1.70, dict dropped
  in v1.71. The geometric half ships via ``reference_preprocess``;
  the textual half over-anchored headshot perspective.
* ``_FACE_AREA_ANCHOR_BY_FRAMING`` ("face occupies ~6% of the frame
  area") — same story, duplicated the cinematic anchor in the numeric
  channel.
* ``LIGHT_MATCH_CLAUSE`` ("Match the subject's lighting …") — gated
  on ``light_match_clause_enabled`` (default False); the instruction
  is already dissolved into ``PHOTOREAL_BLOCK``. v1.71 retired both
  the clause and the flag.
* Per-framing ``_PHOTOREAL_BY_FRAMING`` (three lens specs) — collapsed
  to ``PHOTOREAL_BLOCK`` in v1.70 (lens tokens over-anchored portrait
  perspective); the marker dict was dropped in v1.71.

``framing_line`` is still computed on :class:`CompositionIR` for IR
inspection / test tooling, but never emitted into the wire prompt
(retired in v1.65).

Document styles use a separate vendor-policy path with DOC_PRESERVE /
DOC_QUALITY and a fixed composition hint — identity fidelity
requirements there are not negotiable.

Tail resolution order:

1. ``ir.per_model_tail_map[model]`` — explicit per-model override on
   the style. Highest priority.
2. ``ir.quality_identity_base`` — style-level common tail.
3. Default constants (``QUALITY_PHOTO_GPT`` / ``QUALITY_PHOTO_NANO``)
   — ``PHOTOREAL_BLOCK`` for every model.

The historical ``flux_kontext`` wrapper was retired in v1.70.8 once
``AB_MODELS_ALLOWED`` in ``src/services/analysis_request.py`` was
narrowed to ``{nano_banana_2, gpt_image_2}``.
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


_MODEL_DEFAULT_TAIL = {
    "gpt_image_2": QUALITY_PHOTO_GPT,
    "nano_banana_2": QUALITY_PHOTO_NANO,
}


def _resolve_tail(ir: CompositionIR, model: str) -> str:
    """Pick the right quality/identity tail for ``model``.

    Resolution order:

    1. ``ir.per_model_tail_map[model]`` — explicit per-model override
       on the style.
    2. ``ir.quality_identity_base``    — style-level common tail.
    3. ``_MODEL_DEFAULT_TAIL[model]``  — global default
       (``PHOTOREAL_BLOCK`` for every model in v1.70+).
    """
    override = ir.per_model_tail_map.get(model)
    if override:
        return override
    if ir.quality_identity_base:
        return ir.quality_identity_base
    return _MODEL_DEFAULT_TAIL.get(model, _MODEL_DEFAULT_TAIL["gpt_image_2"])


def _assemble(ir: CompositionIR, *, tail: str) -> str:
    """Assemble the wire-prompt from a :class:`CompositionIR`.

    v1.67 — composition-first / identity-tail ordering.
    v1.70 — cinematic head-anchors removed.
    v1.71 — single-path assembler (no more conditional anchor branches).
    v1.71.2 — explicit crop directive + framing-aware wardrobe filter.
    v1.72 — deep-focus directive against the default bokeh prior.

    Order of stages for non-document styles:

    1. ``change_instruction`` opener (Google-formula "Using the
       reference photo, render the same person in a new scene…").
    2. Scene line — narrative environment.
    3. Wardrobe — explicit body geometry cue. Filtered by framing
       (lower-body garments / footwear stripped on portrait /
       half_body) so the catalogue's full-outfit string does not
       cue the edit model into rendering a fabricated lower body.
    4. Crop directive — ``_FRAMING_PROMPT_DIRECTIVES`` ("Crop the
       frame above the chest; do not render the lower body."),
       emitted right after wardrobe and BEFORE the pose hint.
    5. ``_POSE_BY_FRAMING`` — relaxed-pose body-geometry directive,
       gated on ``settings.pose_hint_enabled`` (default True).
    6. Expression — facial expression / gaze.
    7. ``DEEP_FOCUS_BLOCK`` — v1.72 anti-bokeh directive. Appended
       between expression and tail unless the scene line itself
       carries a shallow-DoF keyword (red-carpet, gala, distant
       landmark "softly out of focus" — see
       ``_SHALLOW_DOF_KEYWORDS`` in ``style_spec.py``).
    8. ``PHOTOREAL_BLOCK`` — skin texture + light-match anchors
       (lens / DoF removed in v1.70).
    9. ``IDENTITY_PRESERVE_BLOCK`` — identity anchors at the very
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
        if ir.change_instruction:
            parts.append(ir.change_instruction)

        scene_line = ir.scene_line()
        if scene_line:
            parts.append(f"{scene_line}.")

        if ir.clothing:
            # v1.71.2 — strip lower-body / footwear garments on
            # portrait / half_body so the catalogue's full-outfit
            # string can't sneak ``trousers`` / ``shoes`` cues into a
            # crop that won't show them. Full-body framing is the
            # passthrough case.
            clothing_for_prompt = ig.filter_wardrobe_by_framing(
                ir.clothing, ir.framing
            )
            if clothing_for_prompt:
                parts.append(f"Wardrobe: {clothing_for_prompt}.")

        # v1.71.2 — explicit crop directive, emitted between wardrobe
        # and the pose hint. Closes the May 2026 ``singapore_marina_bay``
        # regression where a portrait-framing wire prompt carried zero
        # crop signal and the model fabricated a full body. The wording
        # is v1.70-anatomy-lint compliant (no ``head-and-shoulders`` /
        # ``bust shot`` / ``upper third`` head-anchor tokens).
        if ir.framing and ir.framing in ig._FRAMING_PROMPT_DIRECTIVES:
            parts.append(ig._FRAMING_PROMPT_DIRECTIVES[ir.framing])

        # v1.68 — P2.10 per-framing pose hint, emitted right after
        # the crop directive (the natural slot for body-geometry
        # directives). Gated on ``settings.pose_hint_enabled``.
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

        # v1.72 — explicit deep-focus directive (anti-bokeh). Edit-
        # models default to a portrait bokeh prior, and our
        # ``reference_preprocess`` edge-blur padding (radius 80) on
        # ~60% of the canvas reads as a styling cue to keep the
        # background blurred. We append ``DEEP_FOCUS_BLOCK`` between
        # expression and tail UNLESS the scene line itself carries a
        # shallow-DoF token (red-carpet, evening gala, distant
        # landmark "softly out of focus" — see
        # ``_SHALLOW_DOF_KEYWORDS`` in ``style_spec.py``). Document
        # styles are excluded — they use DOC_PRESERVE / DOC_QUALITY.
        _df_inputs: list[str] = []
        if scene_line:
            _df_inputs.append(scene_line)
        if ir.clothing:
            _df_inputs.append(ir.clothing)
        if ir.expression:
            _df_inputs.append(ir.expression)
        if ig.should_apply_deep_focus(*_df_inputs):
            parts.append(ig.DEEP_FOCUS_BLOCK)

        if tail:
            parts.append(tail)

        # v1.67 — identity-preserve at the tail. Empirical audit of
        # v1.66 generations showed that placing identity right after
        # the composition anchor leaked "identical face" into the
        # geometric channel: edit-models interpreted "identical face
        # shape" as "match the head/torso ratio of the reference".
        # Anchoring identity LAST keeps the strongest face-feature
        # signal close to the model's decoding step (recency bias)
        # while letting the composition directive own the early-
        # attention budget.
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


def wrap_for_model(ir: CompositionIR, model: str) -> str:
    """Dispatch helper used by the executor: pick the wrapper by model name.

    ``AB_MODELS_ALLOWED`` ships only ``gpt_image_2`` and ``nano_banana_2``,
    so any unknown ``model`` falls back to the GPT Image 2 wrapper.
    """
    if model == "nano_banana_2":
        return wrap_for_nano_banana_2(ir)
    return wrap_for_gpt_image_2(ir)

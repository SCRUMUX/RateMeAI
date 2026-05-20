"""Per-model prompt wrappers for StyleSpecV3.

v1.67 — composition-first / identity-tail pipeline
---------------------------------------------------
v1.70 — cinematic head-anchor cluster removed (see
``image_gen._COMPOSITION_NUMERICAL_HINT``).
v1.71 — unreachable assembler branches dropped (the underlying dicts
were emptied in v1.70).

Stages of the wire prompt (non-document styles), as they ship today:

1. ``change_instruction``                 — Google-formula opener
                                             ("Using the reference photo,
                                             render the same person in a
                                             new scene…").
2. narrative scene line                   — "<scene> lit by X during a Y
                                             morning in Z." (composed in
                                             :meth:`CompositionIR.scene_line`)
3. wardrobe                               — "Wardrobe: <clothing>."
                                             Body-geometry cue.
4. ``_POSE_BY_FRAMING``                   — relaxed-pose body geometry
                                             directive. Gated on
                                             ``settings.pose_hint_enabled``
                                             (default True in v1.69+).
5. ``expression``                         — natural-from-reference by
                                             default (see
                                             composition_builder.py).
6. ``PHOTOREAL_BLOCK``                    — skin-texture + light-match
                                             anchors. v1.70 dropped the
                                             lens / DoF tokens that
                                             over-anchored portrait
                                             perspective.
7. ``LIGHT_MATCH_CLAUSE``                 — separate clause, gated on
                                             ``light_match_clause_enabled``
                                             (default False in v1.70 —
                                             the instruction is dissolved
                                             into ``PHOTOREAL_BLOCK``).
8. ``IDENTITY_PRESERVE_BLOCK``            — identity anchors at the
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

Historical: stage 2 used to be ``_COMPOSITION_NUMERICAL_HINT`` (a
"Reframe the reference into a head-and-shoulders bust shot …" line)
and there was a v1.68 numeric face-area anchor at the prompt head.
Both were emptied in v1.70 (audit:
``docs/ANATOMY_INVESTIGATION.md``) — the geometric half of those
doctrines still ships via ``reference_preprocess``, the textual half
was found to dominate the prompt with head-cues.

v1.65 removed the standalone ``framing_line`` stage from the wire
prompt; ``framing_line`` is still computed on :class:`CompositionIR`
for IR inspection / test tooling, just not emitted into the final
prompt.

Document styles use a separate vendor-policy path with DOC_PRESERVE /
DOC_QUALITY and a fixed composition hint — identity fidelity
requirements there are not negotiable.

Tail resolution order:

1. ``ir.per_model_tail_map[model]`` — explicit per-model override on
   the style. Highest priority. The v4 migration zeroed these out
   across ``data/styles.json``; until they are re-curated we honour
   any non-empty override.
2. ``ir.quality_identity_base`` — style-level common tail.
3. Default constants (``QUALITY_PHOTO_GPT`` / ``QUALITY_PHOTO_NANO``)
   — ``PHOTOREAL_BLOCK`` for every model.

The historical ``flux_kontext`` wrapper was retired in v1.70.8 once
``AB_MODELS_ALLOWED`` in ``src/services/analysis_request.py`` was
narrowed to ``{nano_banana_2, gpt_image_2}`` and the corresponding
entry was removed from ``data/styles.json``.
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

    v1.68 P2.8 introduced a fourth tier that swapped ``PHOTOREAL_BLOCK``
    for the per-framing :data:`_PHOTOREAL_BY_FRAMING` entry, gated on
    ``settings.photoreal_by_framing_enabled``. v1.70 collapsed every
    entry of that dict to ``PHOTOREAL_BLOCK`` (the per-framing lens
    spec was the dominant head-cue), making the flag a no-op. The
    v1.71 cleanup drops the flag and the dead branch — the
    ``_PHOTOREAL_BY_FRAMING`` dict survives in ``image_gen`` purely
    as a regression marker that ``test_photoreal_by_framing`` asserts
    equals ``PHOTOREAL_BLOCK`` for every framing.
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
    v1.70 — cinematic head-anchors removed (see ``_COMPOSITION_NUMERICAL_HINT``
    docstring); v1.71 also dropped the unreachable assembler branches.

    Order of stages for non-document styles:

    1. ``change_instruction`` opener (Google-formula "Using the
       reference photo, render the same person in a new scene…").
    2. Scene line — narrative environment.
    3. Wardrobe — explicit body geometry cue.
    4. ``_POSE_BY_FRAMING`` — relaxed-pose body-geometry directive,
       gated on ``settings.pose_hint_enabled``.
    5. Expression — facial expression / gaze.
    6. ``PHOTOREAL_BLOCK`` — skin texture + light-match anchors
       (lens / DoF removed in v1.70).
    7. ``LIGHT_MATCH_CLAUSE`` — gated on
       ``settings.light_match_clause_enabled`` (default False in v1.70
       because the clause is dissolved into ``PHOTOREAL_BLOCK``).
    8. ``IDENTITY_PRESERVE_BLOCK`` — identity anchors at the very
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
        # v1.70 anchor cleanup:
        # * ``_FACE_AREA_ANCHOR_BY_FRAMING`` (gated on
        #   ``numerical_percent_anchor_enabled``) was emptied to ``{}``;
        #   the v1.71 cleanup drops the now-unreachable
        #   ``if ir.framing in ig._FACE_AREA_ANCHOR_BY_FRAMING`` branch
        #   from this assembler.
        # * ``_COMPOSITION_NUMERICAL_HINT`` ("Reframe the reference
        #   into a bust shot …") was emptied to ``{}`` because the
        #   geometric half of the anchor still ships via
        #   ``reference_preprocess`` and the textual half was found
        #   in the audit to dominate the prompt with head-cues. The
        #   v1.71 cleanup drops the now-unreachable
        #   ``if ir.framing in ig._COMPOSITION_NUMERICAL_HINT`` branch.
        # The two ``_*_BY_FRAMING`` dicts and their feature flags are
        # kept in ``image_gen``/``config`` as regression markers — tests
        # in ``tests/test_prompts/`` assert they stay empty so a
        # re-introduction is caught instantly.

        if ir.change_instruction:
            parts.append(ir.change_instruction)

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


def wrap_for_model(ir: CompositionIR, model: str) -> str:
    """Dispatch helper used by the executor: pick the wrapper by model name.

    ``AB_MODELS_ALLOWED`` ships only ``gpt_image_2`` and ``nano_banana_2``,
    so any unknown ``model`` falls back to the GPT Image 2 wrapper.
    """
    if model == "nano_banana_2":
        return wrap_for_nano_banana_2(ir)
    return wrap_for_gpt_image_2(ir)

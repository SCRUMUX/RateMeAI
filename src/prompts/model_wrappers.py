"""Per-model prompt wrappers for StyleSpecV2 / V3.

PR1 of the style-schema-v2 migration converted a :class:`CompositionIR`
into the final string sent to GPT Image 2 Edit, Nano Banana 2 Edit or
FLUX Kontext.

v4 (May 2026) — prompt-pipeline-overhaul
----------------------------------------
The v1 tail layout (PRESERVE_PHOTO_FACE_ONLY + QUALITY_PHOTO +
LIGHT_INTEGRATION_PHOTO + SCENE_BLEND_PHOTO + CAMERA_PHOTO +
ANATOMY_PHOTO + per-model "1:7 head-to-body" addendum) was ~1100
characters of fixed boilerplate appended at the very end of every
prompt. Three problems with that:

* Identity instructions arrived in the last third of the prompt, where
  edit-models give them less attention than they deserve. The result
  was the "вклеенное лицо" / pasted-on failure mode.
* PRESERVE asked to keep skin tone while LIGHT_INTEGRATION /
  SCENE_BLEND asked to match it to scene tone — internal contradiction
  that the model resolved by re-grading the face.
* The single fixed tail dominated the attention budget, leaving little
  room for style variation across users.

v4 reorders the prompt to "preserve-first" and trims the tail to two
short blocks (PHOTOREAL_BLOCK + PASTED_ON_GUARD), following the OpenAI
gpt-image-2 cookbook (section 5.2 "Virtual Try-On") and Google's
Nano Banana 2 prompting guide. The v4 layout, in order:

1. ``change_instruction``           — "Place the person …" opener
2. ``IDENTITY_PRESERVE_BLOCK``      — facial features / bone / skin /
                                       hair / pose-fits-scene
3. ``scene`` + ``lighting`` + ``weather``
4. ``clothing``
5. ``expression``                   — natural-from-reference by default
                                       (see composition_builder.py)
6. ``framing_line`` + camera anchor
7. ``PHOTOREAL_BLOCK``              — photoreal cues + 50mm/eye-level
8. ``PASTED_ON_GUARD``              — "without looking pasted on"

Behaviour is gated on ``settings.prompt_pipeline_v4_enabled`` so an
operator can roll back to the v1 layout instantly if needed. Resolution
order for the trailing tail is the same as before:

1. ``ir.per_model_tail_map[model]`` — explicit per-model override on
   the style. Highest priority. Stage 4 of the v4 rollout zeroes these
   out across ``data/styles.json`` so every style picks up the new
   short defaults; until then we still honour any non-empty override.
2. ``ir.quality_identity_base`` — style-level common tail.
3. Default constants (``QUALITY_PHOTO_GPT`` / ``QUALITY_PHOTO_NANO`` /
   ``QUALITY_PHOTO_FLUX``) — short v4 photoreal+pasted-on stack.

Document styles bypass the whole tail and use the legacy DOC_PRESERVE /
DOC_QUALITY + composition hint block — identity fidelity requirements
there are vendor-policy, not style-policy, and have nothing to gain
from a model-specific split.
"""

from __future__ import annotations

from src.prompts import image_gen as ig
from src.prompts.composition_builder import CompositionIR


# v4 short tails. PHOTOREAL_BLOCK + PASTED_ON_GUARD is the entire fixed
# tail; identity-preserve has been hoisted to the top of the prompt by
# the v4 ``_assemble`` reorder. Per-model variants kept as separate
# names so a future PR can tune wording for a single model without
# rebalancing the others.
QUALITY_PHOTO_GPT = " ".join([ig.PHOTOREAL_BLOCK, ig.PASTED_ON_GUARD])
QUALITY_PHOTO_NANO = " ".join([ig.PHOTOREAL_BLOCK, ig.PASTED_ON_GUARD])
QUALITY_PHOTO_FLUX = " ".join([ig.PHOTOREAL_BLOCK, ig.PASTED_ON_GUARD])


# v1.32 long tails — kept addressable for the rollback code-path below
# (``prompt_pipeline_v4_enabled = False``). When v4 is on these are
# ignored entirely.
_QUALITY_PHOTO_GPT_V1 = " ".join(
    [
        ig.PRESERVE_PHOTO_FACE_ONLY,
        ig.QUALITY_PHOTO,
        ig.LIGHT_INTEGRATION_PHOTO,
        ig.SCENE_BLEND_PHOTO_LEGACY,
        ig.CAMERA_PHOTO,
        ig.ANATOMY_PHOTO,
        "Ensure correct 1:7 head-to-body ratio, natural shoulders, and realistic body proportions. The face must not be oversized relative to the body.",
    ]
)

_QUALITY_PHOTO_NANO_V1 = " ".join(
    [
        ig.PRESERVE_PHOTO_FACE_ONLY,
        ig.QUALITY_PHOTO,
        ig.LIGHT_INTEGRATION_PHOTO,
        ig.SCENE_BLEND_PHOTO_LEGACY,
        ig.CAMERA_PHOTO,
        ig.ANATOMY_PHOTO,
    ]
)

_QUALITY_PHOTO_FLUX_V1 = " ".join(
    [
        ig.PRESERVE_PHOTO_FACE_ONLY,
        ig.QUALITY_PHOTO,
        ig.LIGHT_INTEGRATION_PHOTO,
        ig.SCENE_BLEND_PHOTO_LEGACY,
        ig.CAMERA_PHOTO,
        ig.ANATOMY_PHOTO,
    ]
)


_MODEL_DEFAULT_TAIL_V4 = {
    "gpt_image_2": QUALITY_PHOTO_GPT,
    "nano_banana_2": QUALITY_PHOTO_NANO,
    "flux_kontext": QUALITY_PHOTO_FLUX,
}

_MODEL_DEFAULT_TAIL_V1 = {
    "gpt_image_2": _QUALITY_PHOTO_GPT_V1,
    "nano_banana_2": _QUALITY_PHOTO_NANO_V1,
    "flux_kontext": _QUALITY_PHOTO_FLUX_V1,
}

# Public alias retained so external callers / golden tests that import
# ``_MODEL_DEFAULT_TAIL`` keep working. Always points at v4 — v1
# rollback uses ``_MODEL_DEFAULT_TAIL_V1`` directly inside ``_resolve_tail``.
_MODEL_DEFAULT_TAIL = _MODEL_DEFAULT_TAIL_V4


def _v4_enabled() -> bool:
    """Check whether the v4 prompt pipeline is active."""
    try:
        from src.config import settings

        return bool(getattr(settings, "prompt_pipeline_v4_enabled", True))
    except Exception:
        # Defensive: in test contexts where settings aren't fully loaded
        # we default to v4 so the new behaviour is what we exercise.
        return True


def _resolve_tail(ir: CompositionIR, model: str) -> str:
    """Pick the right quality/identity tail for ``model``."""
    override = ir.per_model_tail_map.get(model)
    if override:
        return override
    if ir.quality_identity_base:
        return ir.quality_identity_base
    table = _MODEL_DEFAULT_TAIL_V4 if _v4_enabled() else _MODEL_DEFAULT_TAIL_V1
    return table.get(model, table["gpt_image_2"])


def _assemble(ir: CompositionIR, *, tail: str) -> str:
    """Assemble the wire-prompt from a :class:`CompositionIR`.

    v4 uses a preserve-first ordering; v1 uses the legacy
    ``[change → scene → clothing → expression → framing → tail]``
    layout (selected when ``prompt_pipeline_v4_enabled`` is False).
    Document styles share one path across both versions because
    DOC_PRESERVE / DOC_QUALITY are vendor-policy and haven't changed.
    """
    parts: list[str] = []
    v4 = _v4_enabled()

    if ir.is_document:
        if ir.change_instruction:
            parts.append(ir.change_instruction)
        scene_line = ir.scene_line()
        if scene_line:
            parts.append(f"{scene_line}.")
        if ir.clothing:
            parts.append(f"Subject is wearing {ir.clothing}.")
        if ir.expression:
            parts.append(ir.expression)
        hint = ig._DOC_COMPOSITION_HINT.get(
            ir.style_key, "Centered head-and-shoulders framing."
        )
        parts.append(f"Composition: {hint}")
        parts.append(ig.DOC_PRESERVE)
        parts.append(ig.DOC_QUALITY)
        parts.append(ig.CAMERA_PHOTO)
        parts.append(ig.ANATOMY_PHOTO)
    elif v4:
        if ir.change_instruction:
            parts.append(ir.change_instruction)
        # Identity-preserve hoisted to the top so it sits in the first
        # third of the prompt where edit-models pay most attention.
        parts.append(ig.IDENTITY_PRESERVE_BLOCK)

        scene_line = ir.scene_line()
        if scene_line:
            parts.append(f"{scene_line}.")

        if ir.clothing:
            parts.append(f"Subject is wearing {ir.clothing}.")

        if ir.expression:
            parts.append(ir.expression)

        if ir.framing_line:
            parts.append(ir.framing_line)

        if tail:
            parts.append(tail)
    else:
        # v1 fallback layout (rollback path).
        if ir.change_instruction:
            parts.append(ir.change_instruction)

        scene_line = ir.scene_line()
        if scene_line:
            parts.append(f"{scene_line}.")

        if ir.clothing:
            parts.append(f"Subject is wearing {ir.clothing}.")

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

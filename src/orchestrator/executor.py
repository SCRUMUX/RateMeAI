"""ImageGenerationExecutor and DeltaScorer — extracted from AnalysisPipeline.

Handles single-pass image generation and post-generation delta scoring
as standalone collaborators. v1.71 retired the dormant
``src.orchestrator.advanced`` multi-pass subpackage; the runtime
always runs through :meth:`ImageGenerationExecutor.single_pass`.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from typing import Any, Callable, Awaitable

from src.config import settings
from src.metrics import (
    FAL_CALLS,
    GENERATION_ATTEMPTS,
    GENERATION_COST_USD,
    IDENTITY_RETRY_TRIGGERED,
    IDENTITY_SCORE,
    IMAGE_GEN_BACKEND,
    IMAGE_GEN_CALLS,
    IMAGE_GEN_COST_USD_TOTAL,
    PREMIUM_REFINE_DURATION,
    PREMIUM_REFINE_INVOCATIONS,
    PROMPT_V1_FALLBACK,
    estimate_image_gen_cost_usd,
)
from src.models.enums import AnalysisMode
from src.orchestrator.errors import format_image_gen_error
from src.orchestrator.trace import trace_step as _trace_step
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import STYLE_REGISTRY, resolve_output_size
from src.providers.base import ImageGenProvider, StorageProvider
from src.services.composition_safety import resolve_effective_framing
from src.services.postprocess import (
    crop_to_aspect,
    inject_exif_only,
    upscale_lanczos,
)

# Target aspect ratio for CV document styles. Applied *locally* after
# generation via PIL (see src.services.postprocess.crop_to_aspect) —
# none of the currently wired FAL edit models (GPT Image 2 Edit,
# Nano Banana 2 Edit) accept an arbitrary aspect_ratio knob, so we
# enforce it ourselves after the generation step.
_CV_DOCUMENT_ASPECT: dict[str, str] = {
    "photo_3x4": "3:4",  # 30×40 мм
    "passport_rf": "3:4",  # 35×45 мм ≈ 3:4
    "visa_eu": "3:4",  # 35×45 мм ≈ 3:4
    "visa_schengen": "3:4",  # 35×45 мм
    "visa_us": "1:1",  # 50×50 мм
    "visa_usa": "1:1",  # 51×51 мм
    "visa_uk": "3:4",  # 35×45 мм
    "visa_canada": "3:4",  # 35×45 мм
    "visa_japan": "1:1",  # 45×45 мм
    "visa_china": "3:4",  # 33×48 мм (≈11:16, ближайший «3:4» для постпроцесса)
    "visa_uae": "3:4",  # 43×55 мм (≈7:9, ближайший «3:4»)
    "visa_australia": "3:4",  # 35-40×45-50 мм
    "visa_korea": "3:4",  # 35×45 мм
    "visa_india": "1:1",  # 51×51 мм
    "photo_4x6": "2:3",  # 40×60 мм
    "driver_license": "3:4",
}


def _document_target_aspect(style: str) -> str | None:
    """Return the local-crop target AR for a CV document style, else None."""
    return _CV_DOCUMENT_ASPECT.get((style or "").strip())


# v1.27.3 — RU labels for soft-substitution channels. Used when we
# convert a CompositionIR.substitutions entry into a user-facing notice
# on the result screen.
_SUBSTITUTION_CHANNEL_RU: dict[str, str] = {
    "lighting": "Освещение",
    "weather": "Погода",
    "scene": "Сцена",
    "clothing": "Одежда",
    "time_of_day": "Время суток",
    "season": "Сезон",
}


def _format_substitution_notice_ru(sub: dict[str, str]) -> str:
    """Compose the RU notice text for a single substitution record."""
    label = _SUBSTITUTION_CHANNEL_RU.get(
        str(sub.get("channel") or ""), str(sub.get("channel") or "")
    )
    requested = str(sub.get("requested") or "")
    applied = str(sub.get("applied") or "")
    return (
        f"Параметр «{label}: {requested}» не распознан, "
        f"использован близкий вариант: «{applied}»."
    )


# Face-area threshold above which we locally LANCZOS-upscale the
# generated image x2 (bigger faces benefit from extra detail; smaller
# faces just amplify upscaling artefacts).
_UPSCALE_FACE_THRESHOLD = 0.15


# ---------------------------------------------------------------------------
# Output-size single source of truth (post Nano-Banana cleanup).
# ---------------------------------------------------------------------------
#
# Historical note: this table used to be keyed by ``(model, framing)``
# because Nano Banana 2 needed an ``aspect_ratio`` enum + ``resolution``
# tier instead of a raw ``{width, height}``. With Nano Banana retired
# the table collapses to ``framing → image_size``: GPT Image 2 Edit
# accepts a raw ``{width, height}`` and snaps each portrait framing
# to its native 1024×1536 (2:3) canvas. CV mode (document styles)
# intentionally bypasses this table — vendor policy framing is
# non-negotiable.
_OUTPUT_SIZE_BY_FRAMING: dict[str, dict[str, Any]] = {
    "portrait": {
        "image_size": {"width": 1024, "height": 1536},
        "effective_aspect_ratio": "2:3",
    },
    "half_body": {
        "image_size": {"width": 1024, "height": 1536},
        "effective_aspect_ratio": "2:3",
    },
    "full_body": {
        "image_size": {"width": 1024, "height": 1536},
        "effective_aspect_ratio": "2:3",
    },
}


def _resolve_output_size_ssot(
    *,
    model: str | None = None,
    framing: str | None,
) -> dict[str, Any] | None:
    """Look up the framing → provider-side request shape.

    Returns ``None`` when the SSOT does not cover the requested
    framing — callers must then fall back to the legacy
    ``resolve_output_size`` path. The returned dict carries
    ``image_size`` (GPT-2 native size) and ``effective_aspect_ratio``
    (the canvas the model actually emits).

    The ``model`` kwarg survives for backwards-compatibility with
    older call sites — there is now only one image model, so the
    argument is ignored.
    """
    _ = model  # historical key, kept for backward-compatible signature.
    if not framing:
        return None
    entry = _OUTPUT_SIZE_BY_FRAMING.get(str(framing))
    if entry is None:
        return None
    return dict(entry)


def _apply_local_postprocess(
    raw: bytes,
    mode: AnalysisMode,
    style: str,
    face_area_ratio: float,
) -> bytes:
    """Apply local PIL post-processing (AR crop for documents, LANCZOS x2 for large faces).

    v1.20: historical note — this function replaced the ``postprocessing=
    [{upscale}]`` / ``aspect_ratio`` fields that the pre-v1.14 pipeline
    used to ship to Reve. The Reve and Replicate providers were retired
    together with the v1.20 refactor; local PIL post-processing has been
    the single source of truth ever since. Silent-safe: any PIL failure
    returns the original bytes.

    When ``settings.real_esrgan_enabled`` is True the LANCZOS upscale
    step is skipped — a proper diffusion-aware upscale runs later in
    :func:`_maybe_real_esrgan_upscale` (with LANCZOS as a fallback).
    """
    if not raw or len(raw) <= 100:
        return raw

    if mode == AnalysisMode.CV:
        target_ar = _document_target_aspect(style)
        if target_ar:
            try:
                raw = crop_to_aspect(raw, target_ar)
            except Exception:
                logger.debug("crop_to_aspect failed, using original", exc_info=True)

    esrgan_enabled = bool(getattr(settings, "real_esrgan_enabled", False))
    if (
        face_area_ratio
        and face_area_ratio >= _UPSCALE_FACE_THRESHOLD
        and not esrgan_enabled
    ):
        try:
            raw = upscale_lanczos(raw, factor=2)
        except Exception:
            logger.debug("upscale_lanczos failed, using original", exc_info=True)

    return raw


def _estimate_backend_cost(
    provider_name: str,
    *,
    image_size: dict | None = None,
    routed_backend: str | None = None,
) -> tuple[str, float]:
    """Estimate per-call cost *and* label the effective backend.

    Post Nano-Banana cleanup: the only FAL edit-model backend is
    ``gpt_image_2``. ``routed_backend`` (when set) wins as a label,
    but every numeric estimate now resolves through the GPT Image 2
    cost ladder in :func:`estimate_image_gen_cost_usd`.
    """
    cls = (provider_name or "").lower()
    routed = (routed_backend or "").strip().lower()
    if routed == "gpt_image_2":
        backend = routed
    elif "gpt" in cls:
        backend = "gpt_image_2"
    else:
        backend = cls or "fallback"
    cost = float(estimate_image_gen_cost_usd(provider_name, image_size=image_size))
    return backend, cost


async def _apply_codeformer_post(
    raw: bytes,
    *,
    face_area_ratio: float | None = None,
    is_retry: bool = False,
) -> tuple[bytes, bool]:
    """Run CodeFormer face polish after the main generator.

    v1.64 gating:

    - Skips tiny faces (``face_area_ratio < codeformer_min_face_ratio``)
      — polish is imperceptible at that scale.
    - Skips retry calls by default (``codeformer_on_retry``) — the
      retry is about identity recovery, not sharpness.

    Returns ``(bytes, applied)`` where ``applied`` indicates whether
    CodeFormer actually ran (False = feature disabled, no API key, or
    provider error — in which case the original bytes are returned).
    """
    if not raw or len(raw) <= 100:
        return raw, False
    if not bool(getattr(settings, "codeformer_enabled", False)):
        return raw, False

    if is_retry and not bool(
        getattr(settings, "codeformer_on_retry", False),
    ):
        logger.debug("CodeFormer skipped: retry attempt")
        return raw, False

    min_face_ratio = float(
        getattr(settings, "codeformer_min_face_ratio", 0.0) or 0.0,
    )
    if (
        min_face_ratio > 0.0
        and face_area_ratio is not None
        and face_area_ratio > 0.0
        and face_area_ratio < min_face_ratio
    ):
        logger.debug(
            "CodeFormer skipped: tiny face (%.3f < %.3f)",
            face_area_ratio,
            min_face_ratio,
        )
        return raw, False

    try:
        from src.providers.factory import get_codeformer
    except Exception:
        logger.debug("codeformer import failed", exc_info=True)
        return raw, False

    restorer = get_codeformer()
    if restorer is None:
        return raw, False
    try:
        out = await restorer.restore(raw)
    except Exception:
        logger.warning(
            "CodeFormer post-process failed, keeping generator output",
            exc_info=True,
        )
        return raw, False
    if out and len(out) > 100:
        try:
            FAL_CALLS.labels(
                mode="post",
                step="codeformer",
                model=getattr(
                    settings,
                    "codeformer_model",
                    "fal-ai/codeformer",
                ),
            ).inc()
        except Exception:
            pass
        return out, True
    logger.warning(
        "CodeFormer returned empty payload, keeping generator output",
    )
    return raw, False


async def _apply_clarity_refine(raw: bytes) -> tuple[bytes, bool]:
    """Run the Clarity Upscaler premium refiner on ``raw``.

    v1.72 premium-tier post-process step. Triggered ONLY when the
    task context carries ``image_refine == "clarity"`` (set by
    ``apply_ab_test_context_fields(tier="premium")`` in
    ``src/services/analysis_request.py``).

    Gating:

    - ``settings.clarity_refiner_enabled`` is the Railway kill-switch
      (default True). When off, returns the input unchanged and
      ``applied=False`` — the orchestrator uses that signal to refund
      1 of the 2 reserved credits so the user is not charged for a
      premium upgrade that didn't actually run.
    - Same non-fatal contract as CodeFormer / Real-ESRGAN: any
      provider error returns the input unchanged with
      ``applied=False``.

    Returns ``(processed_bytes, applied)`` where ``applied`` is True
    iff Clarity actually ran and returned a non-empty payload.
    """
    if not raw or len(raw) <= 100:
        return raw, False
    if not bool(getattr(settings, "clarity_refiner_enabled", False)):
        return raw, False

    api_key = getattr(settings, "fal_api_key", None) or ""
    if not api_key:
        logger.debug("Clarity refiner skipped: FAL_API_KEY is empty")
        return raw, False

    try:
        from src.providers.image_gen.fal_clarity_upscaler import (
            FalClarityUpscaler,
        )
    except Exception:
        logger.warning(
            "Clarity refiner import failed, keeping main render",
            exc_info=True,
        )
        return raw, False

    try:
        refiner = FalClarityUpscaler(
            api_key=api_key,
            model=getattr(
                settings,
                "clarity_refiner_model",
                "fal-ai/clarity-upscaler",
            ),
        )
        out = await refiner.refine(
            raw,
            creativity=float(
                getattr(settings, "clarity_refiner_creativity", 0.2),
            ),
            resemblance=float(
                getattr(settings, "clarity_refiner_resemblance", 0.8),
            ),
            dynamic=float(
                getattr(settings, "clarity_refiner_dynamic", 5.0),
            ),
            upscale_factor=float(
                getattr(settings, "clarity_refiner_upscale_factor", 2.0),
            ),
        )
    except Exception:
        logger.warning(
            "Clarity refiner failed, keeping main render",
            exc_info=True,
        )
        return raw, False

    if out and len(out) > 100:
        try:
            FAL_CALLS.labels(
                mode="post",
                step="clarity_refine",
                model=getattr(
                    settings,
                    "clarity_refiner_model",
                    "fal-ai/clarity-upscaler",
                ),
            ).inc()
        except Exception:
            pass
        return out, True

    logger.warning(
        "Clarity refiner returned empty payload, keeping main render",
    )
    return raw, False


async def _maybe_real_esrgan_upscale(
    raw: bytes,
    face_area_ratio: float,
) -> bytes:
    """Final upscale via fal-ai/real-esrgan, with LANCZOS fallback.

    v1.17 replacement for the sync LANCZOS path in
    :func:`_apply_local_postprocess`. Runs only when:

      * ``settings.real_esrgan_enabled`` is True (feature flag — default
        off on a fresh deploy);
      * ``face_area_ratio`` exceeds :data:`_UPSCALE_FACE_THRESHOLD` —
        tiny faces do not benefit from upscaling and we skip the spend.

    Any failure (transport, API error, empty result) folds back to a
    local PIL LANCZOS x2 — upscaling is always optional, never
    load-bearing.
    """
    if not raw or len(raw) <= 100:
        return raw
    if not bool(getattr(settings, "real_esrgan_enabled", False)):
        return raw
    if not face_area_ratio or face_area_ratio < _UPSCALE_FACE_THRESHOLD:
        return raw

    api_key = getattr(settings, "fal_api_key", None) or ""
    if not api_key:
        logger.debug("Real-ESRGAN skipped: FAL_API_KEY is empty")
        try:
            return upscale_lanczos(raw, factor=2)
        except Exception:
            return raw

    try:
        from src.providers.image_gen.fal_esrgan import FalRealEsrganUpscaler
    except Exception:
        logger.warning(
            "Real-ESRGAN import failed, falling back to LANCZOS",
            exc_info=True,
        )
        try:
            return upscale_lanczos(raw, factor=2)
        except Exception:
            return raw

    try:
        upscaler = FalRealEsrganUpscaler(
            api_key=api_key,
            model=getattr(
                settings,
                "real_esrgan_model",
                "fal-ai/real-esrgan",
            ),
        )
        out = await upscaler.upscale(raw, factor=2)
        if out and len(out) > 100:
            try:
                FAL_CALLS.labels(
                    mode="post",
                    step="real_esrgan",
                    model=getattr(
                        settings,
                        "real_esrgan_model",
                        "fal-ai/real-esrgan",
                    ),
                ).inc()
            except Exception:
                pass
            return out
        logger.warning(
            "Real-ESRGAN returned empty payload, falling back to LANCZOS",
        )
    except Exception:
        logger.warning(
            "Real-ESRGAN failed, falling back to LANCZOS",
            exc_info=True,
        )

    try:
        return upscale_lanczos(raw, factor=2)
    except Exception:
        logger.debug("LANCZOS fallback also failed, keeping original", exc_info=True)
        return raw


logger = logging.getLogger(__name__)


ProgressCallback = Callable[[str, int, int], Awaitable[None]]


# Backwards-compat alias: still referenced by a few callers inside this
# module. ``format_image_gen_error`` is the canonical name in errors.py.
_format_image_gen_error = format_image_gen_error


class ImageGenerationExecutor:
    """Runs single-pass image generation against the active provider.

    v1.71 retired the dormant ``src.orchestrator.advanced`` multi-pass
    subpackage; ``single_pass`` is the only runtime entrypoint.
    """

    def __init__(
        self,
        image_gen: ImageGenProvider | None,
        prompt_engine: PromptEngine,
        storage: StorageProvider,
        identity_svc_getter: Callable,
        gate_runner_getter: Callable,
    ):
        self._image_gen = image_gen
        self._prompt_engine = prompt_engine
        self._storage = storage
        self._get_identity_service = identity_svc_getter
        self._get_gate_runner = gate_runner_getter

    def _build_prompt(
        self,
        *,
        mode: AnalysisMode,
        style: str,
        gender: str,
        variant_id: str,
        ab_image_model: str,
        framing_norm: str,
        seed: int | None,
        scenario_slug: str | None,
        input_quality: Any | None,
        user_input_hints: dict | None,
        result_dict: dict,
    ) -> tuple[str, str]:
        """Build the wire prompt for the requested style via PromptEngine v2.

        Pure-ish extract from ``single_pass`` (v1.71 refactor). Side
        effects: appends substitution notices into
        ``result_dict["generation_warnings"]`` and writes
        ``result_dict["resolved_slots"]`` / ``result_dict["variant_id"]``
        — all behaviours the existing pipeline contract already
        produces.

        Returns:
            Tuple of ``(prompt, prompt_pipeline_path)``. Raises
            ``RuntimeError`` when no StyleSpec is registered for
            ``(mode, style)``.
        """
        desc = str(result_dict.get("base_description", ""))
        # v1.26: base hints берём из input_quality (lighting/blur/etc.
        # из гейта качества), а пользовательские hints мерджим сверху
        # — пользовательский выбор перекрывает эвристики, но если
        # пользователь не трогал поле, оно остаётся из анализа. До
        # этого user_input_hints молча терялись: executor просто
        # перезаписывал их ``input_quality.to_prompt_hints()``.
        base_hints = (
            input_quality.to_prompt_hints() if input_quality is not None else {}
        ) or {}
        merged_hints = {**base_hints, **(user_input_hints or {})}
        input_hints = merged_hints or None

        # v4.1 (May 2026): single-path prompt pipeline. The v2 path
        # is the only path — see [docs decision in v4.1 plan]. v1
        # fallback is kept for emoji-only callers that use a
        # different signature; for photo styles a missing spec is
        # an error (caught by the caller).
        v2_substitutions: list[dict[str, str]] = []
        # ``resolved_slots`` is populated by the v3 path in
        # PromptEngine.build_image_prompt_v2 — the executor passes
        # in a fresh dict so it can persist what the slot sampler
        # actually rolled into ``result_dict["resolved_slots"]``
        # (and forward it to the frontend for badge rendering).
        resolved_slots: dict[str, object] = {}
        prompt = self._prompt_engine.build_image_prompt_v2(
            mode,
            style=style,
            base_description=desc,
            gender=gender,
            input_hints=input_hints,
            variant_id=variant_id,
            target_model=ab_image_model,
            framing=framing_norm,
            out_substitutions=v2_substitutions,
            seed=seed,
            out_resolved_slots=resolved_slots,
            scenario_slug=scenario_slug,
        )

        if prompt is None:
            # Style is not registered for the slot-based path
            # (no v3 spec, no v2 spec) — should be impossible after
            # the v4.1 auto-promoter ran, so we fail loud.
            logger.error(
                "prompt_build_failed_no_spec",
                extra={
                    "mode": getattr(mode, "value", str(mode)),
                    "style": style,
                    "variant_id": variant_id,
                    "ab_image_model": ab_image_model,
                },
            )
            PROMPT_V1_FALLBACK.labels(
                mode=getattr(mode, "value", str(mode)),
                style=style or "unknown",
            ).inc()
            raise RuntimeError(
                f"No StyleSpec registered for mode={mode.value!r} "
                f"style={style!r}. Run the v3 loader before "
                "executor.single_pass()."
            )

        # v4.1: derive path tag for INFO logging in FAL providers.
        # ``resolved_slots`` is non-empty only on the v3 path, so
        # its presence/absence is the most reliable in-process
        # signal for which schema actually drove the prompt.
        # v1.70.17 cleanup: ``v3_promoted`` distinguisher was retired
        # alongside ``_auto_promote_v2_specs`` — every style on disk
        # is now natively v3, no synthetic-from-v2 specs exist.
        prompt_pipeline_path = "v3" if resolved_slots else "v2"

        # v1.27.3 — surface soft-substitutions as a post-generation
        # notice. When the user typed a value the style didn't
        # recognise (e.g. "Эверест" in scene_override on Times Square),
        # composition_builder picks a random whitelist value AND
        # records it here; we translate the record into RU and
        # append to result_dict.generation_warnings so the web
        # client can show a small notice on the result screen.
        if v2_substitutions:
            bucket = result_dict.setdefault("generation_warnings", [])
            for sub in v2_substitutions:
                bucket.append(_format_substitution_notice_ru(sub))

        # Persist the v3 slot roll for the frontend badges and for
        # the "Другой вариант" anti-repeat logic. We always write
        # the dict (even when empty) so consumers can branch on
        # presence without a key check.
        if resolved_slots:
            result_dict["resolved_slots"] = dict(resolved_slots)

        if variant_id:
            result_dict["variant_id"] = variant_id

        return prompt, prompt_pipeline_path

    def _resolve_framing(
        self,
        *,
        mode: AnalysisMode,
        style: str,
        framing: str | None,
        user_input_hints: dict | None,
        input_quality: Any | None,
        result_dict: dict,
    ) -> tuple[str, bool, bool, str]:
        """Pick the final framing through the CSL resolver.

        Pure-ish extract from ``single_pass`` (v1.71 refactor). The
        only side effects are writing ``resolved_framing`` /
        ``user_picked_framing`` into ``result_dict`` and emitting the
        ``framing_resolved`` INFO log — both observable behaviours
        that the existing pipeline contract depends on.

        Returns:
            Tuple of
            ``(framing_norm, is_document, is_studio_portrait_style,
            user_picked_framing)``.
        """
        # v1.27.3: «Другой вариант» — framing из модалки перебивает
        # framing шага «Выберите стиль». Если модалка явно прислала
        # framing в input_hints, он побеждает; пустое поле модалки
        # = унаследовать значение основного шага.
        modal_framing = ""
        if user_input_hints:
            modal_framing = str(user_input_hints.get("framing") or "").strip().lower()

        # v1.65 — pick the final framing through the CSL resolver.
        # Replaces the hardcoded ``half_body`` fallback that v1.63
        # used when the request came in without a valid framing. The
        # resolver respects an explicit user pick when the policy
        # allows it, falls back to the style's ``needs_full_body``
        # when relevant, and finally to the safest framing for the
        # detected composition class. Document styles short-circuit
        # to ``portrait`` regardless.
        try:
            from src.prompts.image_gen import is_document_style as _is_doc
            _is_document = bool(_is_doc(style or ""))
        except Exception:
            _is_document = False

        try:
            from src.prompts.image_gen import (
                is_studio_portrait_style as _is_studio_portrait,
            )
            _is_studio_portrait_style = bool(_is_studio_portrait(style or ""))
        except Exception:
            _is_studio_portrait_style = False

        user_picked_framing = (
            modal_framing
            if modal_framing in ("portrait", "half_body", "full_body")
            else str(framing or "").strip().lower()
        )
        if user_picked_framing not in ("portrait", "half_body", "full_body"):
            user_picked_framing = ""

        composition_class_for_resolver = (
            getattr(input_quality, "composition_class", "unknown")
            if input_quality is not None
            else "unknown"
        )
        spec_for_framing = STYLE_REGISTRY.get(
            getattr(mode, "value", str(mode)), style
        )
        framing_norm = resolve_effective_framing(
            user_framing=user_picked_framing or None,
            composition_class=composition_class_for_resolver,
            spec=spec_for_framing,
            is_document=_is_document,
            is_studio_portrait=_is_studio_portrait_style,
        )
        result_dict["resolved_framing"] = framing_norm
        if user_picked_framing:
            result_dict["user_picked_framing"] = user_picked_framing

        # v1.65 — visibility into the framing resolver. Tracks how often
        # the auto-picker overrides a missing / invalid user pick and
        # which composition class drove the decision. Together with the
        # existing REFERENCE_PADDED counter (in :mod:`src.metrics`) this
        # is the primary signal for measuring v1.65 rollout impact.
        logger.info(
            "framing_resolved mode=%s style=%s "
            "user_picked=%s composition_class=%s "
            "is_document=%s resolved_framing=%s",
            getattr(mode, "value", str(mode)),
            style or "default",
            user_picked_framing or "<auto>",
            composition_class_for_resolver,
            _is_document,
            framing_norm,
        )

        return framing_norm, _is_document, _is_studio_portrait_style, user_picked_framing

    def _prepare_provider_params(
        self,
        *,
        mode: AnalysisMode,
        style: str,
        prompt_pipeline_path: str,
        framing_norm: str,
        face_area_ratio: float,
        input_quality: Any | None,
        ab_active: bool,
        ab_image_model: str,
        ab_image_quality: str,
        allow_cross_model_fallback: bool,
        result_dict: dict,
    ) -> tuple[dict, dict | None, tuple | None]:
        """Build the provider ``extra`` payload + output_size + face bbox.

        Post Nano-Banana cleanup: there is one image model in the
        pipeline (GPT Image 2 Edit) which accepts a raw
        ``{width, height}`` request. The ``aspect_ratio`` /
        ``resolution`` enum knobs that Nano Banana 2 needed are no
        longer emitted. ``ab_image_model`` and
        ``allow_cross_model_fallback`` are accepted for backward
        compatibility with older call sites but are functionally
        no-ops here — the provider is fixed.

        Returns ``(extra, output_size, iq_bbox)``: ``extra`` is the
        dict passed to ``ImageGenProvider.generate(params=...)``,
        ``output_size`` is the resolved ``{"width", "height"}`` (or
        ``None`` for unknown styles), and ``iq_bbox`` is the face
        bbox sourced from the input-quality gate (used downstream by
        the CSL padder).
        """
        _ = allow_cross_model_fallback  # kept for signature back-compat.
        extra: dict = {}

        extra["style"] = style or "default"
        extra["prompt_pipeline_path"] = prompt_pipeline_path

        spec = STYLE_REGISTRY.get(mode.value, style)

        iq_bbox = getattr(input_quality, "face_bbox", None)
        if iq_bbox is not None:
            extra["face_bbox"] = iq_bbox

        output_size = resolve_output_size(
            spec,
            face_area_ratio=face_area_ratio or None,
            framing=framing_norm,
        )
        if output_size:
            extra["image_size"] = output_size
            mp = (output_size["width"] * output_size["height"]) / 1_000_000
            logger.info(
                "image_size resolved mode=%s style=%s "
                "size=%dx%d (~%.2f MP)",
                mode.value,
                style or "default",
                output_size["width"],
                output_size["height"],
                mp,
            )

        if ab_active:
            # ``image_model`` is pinned to ``gpt_image_2`` in
            # ``apply_tier_context_fields``; we propagate it here so
            # downstream metrics and logs see a stable label. The
            # legacy A/B knob is otherwise inert.
            extra["image_model"] = ab_image_model or "gpt_image_2"
            extra["quality"] = ab_image_quality or getattr(
                settings, "ab_default_quality", "medium"
            )

            try:
                _ssot_on = bool(
                    getattr(settings, "output_size_ssot_enabled", False)
                )
            except Exception:
                _ssot_on = False
            if _ssot_on and mode != AnalysisMode.CV:
                ssot = _resolve_output_size_ssot(framing=framing_norm)
                if ssot is not None:
                    if "image_size" in ssot:
                        extra["image_size"] = ssot["image_size"]
                        output_size = ssot["image_size"]
                    eff_ar = ssot.get("effective_aspect_ratio")
                    if eff_ar:
                        result_dict["effective_aspect_ratio"] = eff_ar
                    logger.info(
                        "image_size SSOT framing=%s applied=%s",
                        framing_norm,
                        sorted(ssot.keys()),
                    )

        return extra, output_size, iq_bbox

    def _maybe_pad_reference(
        self,
        *,
        image_bytes: bytes,
        mode: AnalysisMode,
        style: str,
        framing_norm: str,
        face_area_ratio: float,
        iq_bbox: tuple | None,
        output_size: dict | None,
        input_quality: Any | None,
        is_document: bool,
        is_studio_portrait_style: bool,
    ) -> bytes:
        """CSL Phase 1.5 geometric reference padding.

        v1.71 (Phase 4.3 of the tech-debt roadmap): extracted from
        :meth:`single_pass`. Tight-selfie inputs drag edit-models into
        copying their head/torso ratio verbatim — the numerical anchor
        in the prompt cannot overcome that spatial signal on its own.
        :func:`pad_reference_for_framing` re-positions the face on a
        canvas that already matches the target framing so the
        edit-model only has to repaint clothing / background.

        Returns the bytes to pass to the provider — either the padded
        canvas (on a successful gate hit) or the original
        ``image_bytes`` (gate miss, padding disabled, or PIL fallback
        after an exception). Logging / metric semantics are byte-for-
        byte identical to the inlined version: a single
        ``reference_padding_applied`` INFO + ``REFERENCE_PADDED``
        counter on success, or ``reference_padding_failed`` WARNING on
        a PIL exception.
        """
        composition_class = (
            getattr(input_quality, "composition_class", "unknown")
            if input_quality is not None
            else "unknown"
        )

        # v1.65 — padding gate now covers ``portrait`` framing too.
        # Tight-selfie + ``framing=portrait`` is the single most
        # common request shape (telegram preview-quality reference,
        # default framing on the web wizard), and that combination
        # is exactly where the "huge head, tiny shoulders"
        # pathology shows up. The threshold is decoupled from the
        # CSL classification ``face_closeup`` threshold (0.35) via a
        # dedicated config knob — padding is a soft local PIL
        # operation, so it can be triggered on uploads that are
        # technically PORTRAIT-class but still tight enough to
        # mis-anchor the head/torso ratio.
        #
        # v1.66 — CV-mode boost. CV users upload "passport-style"
        # selfies far more often than dating/social users; the
        # ``face_closeup`` boundary sits right at the typical CV
        # upload (face_area_ratio ≈ 0.22..0.30). We lower the
        # threshold to ``csl_reference_pad_face_ratio_cv`` (0.22)
        # for mode=cv only — and only for non-studio-portrait
        # styles, since studio portraits are by-design tight
        # headshots and padding would fight the intended crop.
        #
        # v1.67 — gate widened. PORTRAIT and HALF_BODY composition
        # classes are explicit padding triggers — anything that
        # isn't a true FULL_BODY (sub-0.06 face, ample space below)
        # is geometrically normalised. The default ``pad_threshold``
        # is lowered to 0.10 so even loose-portrait uploads still
        # short-circuit through the ratio path.
        pad_threshold = float(
            getattr(
                settings,
                "csl_reference_pad_face_ratio",
                0.10,
            )
        )
        mode_value = getattr(mode, "value", str(mode))
        if mode_value == "cv" and not is_studio_portrait_style:
            pad_threshold = float(
                getattr(
                    settings,
                    "csl_reference_pad_face_ratio_cv",
                    0.10,
                )
            )

        is_tight = (
            composition_class
            in ("face_closeup", "portrait", "half_body", "unknown")
            or face_area_ratio > pad_threshold
        )
        should_pad = (
            getattr(settings, "csl_reference_pad_enabled", False)
            and not is_document
            and framing_norm in ("portrait", "half_body", "full_body")
            and is_tight
            and iq_bbox is not None
        )
        if not should_pad:
            return image_bytes

        try:
            from src.metrics import REFERENCE_PADDED
            from src.services.reference_preprocess import (
                pad_reference_for_framing,
            )

            target_size_tuple: tuple[int, int]
            if output_size:
                target_size_tuple = (
                    int(output_size["width"]),
                    int(output_size["height"]),
                )
            else:
                target_size_tuple = (1280, 1600)

            padded = pad_reference_for_framing(
                image_bytes,
                face_bbox=tuple(iq_bbox),
                framing=framing_norm,
                target_size=target_size_tuple,
            )
            REFERENCE_PADDED.labels(
                framing=framing_norm,
                composition_class=composition_class,
            ).inc()
            logger.info(
                "reference_padding_applied mode=%s style=%s "
                "framing=%s composition_class=%s "
                "face_area_ratio=%.3f",
                mode.value,
                style or "default",
                framing_norm,
                composition_class,
                face_area_ratio,
            )
            return padded
        except Exception as exc:
            logger.warning(
                "reference_padding_failed mode=%s style=%s err=%s "
                "— falling back to raw reference",
                mode.value,
                style or "default",
                exc,
            )
            return image_bytes

    async def _postprocess(
        self,
        raw: bytes,
        *,
        mode: AnalysisMode,
        style: str,
        face_area_ratio: float,
        apply_quality_post: bool,
        is_retry: bool,
    ) -> tuple[bytes, bool]:
        """Run local crop / upscale / CodeFormer / Real-ESRGAN.

        v1.71 (Phase 4.4 of the tech-debt roadmap): extracted from
        :meth:`single_pass` so both the first-pass and the identity-
        retry branches share one implementation. Always runs
        :func:`_apply_local_postprocess` (document AR crop + the small
        x2 LANCZOS upscale for tight selfies); the CodeFormer and
        Real-ESRGAN passes are gated on ``apply_quality_post`` —
        callers pass ``not ab_active`` for the first pass (skipping
        them on the A/B path where edit-models already emit clean
        faces) and ``True`` for identity retries (matching the
        pre-refactor behaviour). Returns
        ``(processed_bytes, codeformer_applied)``.
        """
        raw = _apply_local_postprocess(raw, mode, style, face_area_ratio)
        cf_applied = False
        if apply_quality_post:
            raw, cf_applied = await _apply_codeformer_post(
                raw,
                face_area_ratio=face_area_ratio or None,
                is_retry=is_retry,
            )
            raw = await _maybe_real_esrgan_upscale(raw, face_area_ratio)
        return raw, cf_applied

    def _record_fal_call_metric(
        self,
        *,
        provider_name: str,
        backend: str,
        mode: AnalysisMode,
        step: str,
    ) -> None:
        """Resolve the underlying FAL model name and bump ``FAL_CALLS``.

        v1.71 (Phase 4.4): same dispatch table that lived inline in
        :meth:`single_pass` (twice — once for the first pass, once for
        the identity retry). ``provider_name`` is ``type(image_gen).
        __name__`` (``FalGptImage2Edit`` for the live path,
        ``MockImageGen`` in dev). ``backend`` is the resolved label
        from :func:`_estimate_backend_cost` — always
        ``"gpt_image_2"`` after the Nano-Banana cleanup. A no-op when
        the provider class does not resolve to a known FAL model
        (e.g. ``MockImageGen``).
        """
        fal_model: str | None = None
        cls_lower = provider_name.lower()
        if backend == "gpt_image_2" or "gptimage" in cls_lower:
            fal_model = getattr(
                settings, "gpt_image_2_model", "openai/gpt-image-2/edit"
            )

        if not fal_model:
            return
        try:
            FAL_CALLS.labels(
                mode=mode.value,
                step=step,
                model=fal_model,
            ).inc()
        except Exception as e:
            logger.warning(
                "Failed to record FAL_CALLS metric for %s: %s", step, e
            )

    async def _persist_and_metric(
        self,
        raw: bytes,
        *,
        user_id: str,
        task_id: str,
        mode: AnalysisMode,
        style: str,
        result_dict: dict,
        first_pass_backend: str,
        ab_active: bool,
        ab_image_model: str,
        ab_image_quality: str,
        extra: dict,
        provider_name: str,
        identity_match: float,
        generation_attempts: int,
        codeformer_applied: bool,
        face_area_ratio: float,
        clarity_refine_applied: bool = False,
        clarity_refine_attempted: bool = False,
        clarity_refine_ms: int = 0,
        product_tier: str = "",
    ) -> None:
        """Upload generated JPEG + record cost/backend metrics.

        v1.71 (Phase 4.5 of the tech-debt roadmap): extracted from
        :meth:`single_pass`. Side effects only — writes URLs and cost
        metadata into ``result_dict``, bumps Prometheus counters, and
        logs the final ``Image generated backend=…`` line. Behaviour is
        byte-for-byte unchanged from the inlined version.
        """
        raw = inject_exif_only(raw)

        gkey = f"generated/{user_id}/{task_id}.jpg"
        result_dict["_generation_stash_jpeg"] = bytes(raw)
        await self._storage.upload(gkey, raw)
        gen_url = await self._storage.get_url(gkey)
        result_dict["generated_image_url"] = gen_url
        result_dict["image_url"] = gen_url

        routed_label = first_pass_backend or ""
        if ab_active:
            from src.metrics import (
                ab_backend_label,
                estimate_ab_image_gen_cost_usd,
            )

            _ab_q = (
                extra.get("quality")
                or ab_image_quality
                or getattr(settings, "ab_default_quality", "medium")
            )
            backend_label = ab_backend_label(ab_image_model, _ab_q)
            per_call_cost = estimate_ab_image_gen_cost_usd(
                ab_image_model,
                _ab_q,
            )
        else:
            backend_label, per_call_cost = _estimate_backend_cost(
                provider_name,
                image_size=extra.get("image_size"),
                routed_backend=routed_label,
            )
        estimated_cost = per_call_cost * max(1, generation_attempts)

        try:
            IMAGE_GEN_BACKEND.labels(backend=backend_label).inc()
        except Exception:
            pass
        try:
            GENERATION_COST_USD.labels(
                backend=backend_label,
            ).observe(estimated_cost)
        except Exception:
            pass

        result_dict["enhancement"] = {
            "style": style or "default",
            "mode": mode.value,
            "provider": provider_name,
            "backend": backend_label,
            "identity_match": round(identity_match, 2),
            "generation_attempts": generation_attempts,
            "pipeline_type": "single_pass_edit",
            "codeformer_applied": codeformer_applied,
        }
        cost_steps = [
            {
                "step": "single_pass_edit",
                "model": provider_name,
                "backend": backend_label,
                "cost_usd": round(per_call_cost, 4),
            }
        ]
        if generation_attempts > 1:
            cost_steps.append(
                {
                    "step": "identity_retry",
                    "model": provider_name,
                    "backend": backend_label,
                    "cost_usd": round(
                        per_call_cost * (generation_attempts - 1),
                        4,
                    ),
                }
            )
        esrgan_on = bool(
            getattr(settings, "real_esrgan_enabled", False)
            and face_area_ratio
            and face_area_ratio >= _UPSCALE_FACE_THRESHOLD
        )
        esrgan_cost = 0.0
        if esrgan_on:
            esrgan_cost = float(
                getattr(
                    settings,
                    "model_cost_fal_real_esrgan",
                    0.002,
                )
            ) * float(max(1, generation_attempts))
            cost_steps.append(
                {
                    "step": "real_esrgan",
                    "model": getattr(
                        settings,
                        "real_esrgan_model",
                        "fal-ai/real-esrgan",
                    ),
                    "cost_usd": round(esrgan_cost, 4),
                }
            )
        codeformer_cost = 0.0
        if codeformer_applied:
            per_mp = float(
                getattr(
                    settings,
                    "model_cost_fal_codeformer_per_mp",
                    0.0021,
                )
            )
            upscale = float(
                getattr(
                    settings,
                    "codeformer_upscale_factor",
                    2.0,
                )
            )
            codeformer_cost = round(
                per_mp * max(1.0, upscale * upscale),
                4,
            )
            cost_steps.append(
                {
                    "step": "codeformer",
                    "model": getattr(
                        settings,
                        "codeformer_model",
                        "fal-ai/codeformer",
                    ),
                    "cost_usd": codeformer_cost,
                }
            )

        # v1.72 — premium refiner cost line. Only billed when Clarity
        # actually returned a refined payload (``applied=True``); a
        # failed/skipped refiner is invisible in the cost breakdown
        # because the orchestrator refunds 1 of the 2 reserved
        # credits in that case.
        clarity_cost = 0.0
        if clarity_refine_applied:
            clarity_cost = round(
                float(
                    getattr(
                        settings,
                        "model_cost_fal_clarity",
                        0.04,
                    ),
                ),
                4,
            )
            cost_steps.append(
                {
                    "step": "clarity_refine",
                    "model": getattr(
                        settings,
                        "clarity_refiner_model",
                        "fal-ai/clarity-upscaler",
                    ),
                    "cost_usd": clarity_cost,
                }
            )

        total_cost = (
            estimated_cost + esrgan_cost + codeformer_cost + clarity_cost
        )
        result_dict["cost_breakdown"] = {
            "steps": cost_steps,
            "total_usd": round(total_cost, 4),
            "budget_usd": settings.pipeline_budget_max_usd,
        }

        # v1.72 — surface tier metadata on the enhancement payload so
        # the UI / admin tooling can render the "Standard" vs.
        # "Premium" pill. ``premium_refine_attempted`` distinguishes
        # a failed refiner (refund issued) from "user picked standard"
        # for downstream analytics.
        tier_label = (product_tier or "standard").strip().lower() or "standard"
        result_dict["enhancement"]["tier"] = tier_label
        result_dict["enhancement"]["premium_refine_attempted"] = (
            clarity_refine_attempted
        )
        result_dict["enhancement"]["premium_refine_applied"] = (
            clarity_refine_applied
        )

        try:
            IMAGE_GEN_COST_USD_TOTAL.labels(tier=tier_label).inc(total_cost)
        except Exception:
            pass

        logger.info(
            "Image generated tier=%s backend=%s key=%s "
            "identity_match=%.2f main_ms=%d refine_ms=%d "
            "refine_applied=%s cost=$%.4f",
            tier_label,
            backend_label,
            gkey,
            identity_match,
            0,
            clarity_refine_ms,
            clarity_refine_applied,
            total_cost,
        )

    async def _run_with_retry(
        self,
        raw: bytes,
        *,
        image_bytes: bytes,
        image_gen: ImageGenProvider,
        prompt: str,
        reference_for_provider: bytes,
        extra: dict,
        mode: AnalysisMode,
        style: str,
        task_id: str,
        trace: dict,
        result_dict: dict,
        warnings: list[str],
        provider_name: str,
        first_pass_backend: str,
        face_area_ratio: float,
        generation_attempts: int,
        codeformer_applied: bool,
    ) -> tuple[bytes, float, int, bool]:
        """VLM quality gates + optional identity-retry loop.

        v1.71 (Phase 4.6 of the tech-debt roadmap): extracted from
        :meth:`single_pass`. Runs ``run_global_gates`` on the first-pass
        output, optionally re-generates with a fresh seed when
        ``identity_match`` falls below threshold (and the VLM check
        itself did not error), then surfaces soft user-facing warnings
        from the final ``quality_report``. Returns
        ``(raw, identity_match, generation_attempts,
        codeformer_applied)`` — the retry may swap ``raw`` for a
        higher-scoring candidate. Emoji mode callers skip this helper
        entirely. Behaviour is byte-for-byte unchanged from the
        inlined version; contract pinned by
        ``tests/test_orchestrator/test_identity_retry.py``.
        """
        identity_match: float = 0.0
        try:
            gate_runner = self._get_gate_runner()
            sp_gates: dict[str, float] = {
                "identity_match": settings.identity_match_threshold,
                "aesthetic_score": settings.aesthetic_threshold,
            }
            if settings.photorealism_enabled:
                sp_gates["photorealism"] = settings.photorealism_threshold
            sp_gates["niqe"] = 5.0

            with _trace_step(trace, "single_pass_gates") as sp_entry:
                (
                    sp_passed,
                    sp_results,
                    sp_report,
                ) = await gate_runner.run_global_gates(
                    sp_gates,
                    image_bytes,
                    raw,
                )
                sp_entry["gates"] = [
                    {
                        "gate": gr.gate_name,
                        "passed": gr.passed,
                        "value": gr.value,
                    }
                    for gr in sp_results
                ]
            result_dict["quality_report"] = sp_report

            identity_match = float(sp_report.get("identity_match") or 0.0)
            if identity_match:
                IDENTITY_SCORE.observe(identity_match / 10.0)

            retry_enabled = bool(
                getattr(settings, "identity_retry_enabled", False)
            )
            try:
                _cfg_max = getattr(
                    settings,
                    "identity_retry_max_attempts",
                    0,
                )
                max_total_attempts = 1 + max(0, int(_cfg_max or 0))
            except (TypeError, ValueError):
                max_total_attempts = 1

            first_check_failed = bool(sp_report.get("quality_check_failed"))
            should_retry = (
                retry_enabled
                and not first_check_failed
                and identity_match > 0.0
                and identity_match
                < float(settings.identity_match_threshold or 0.0)
                and generation_attempts < max_total_attempts
            )

            if should_retry:
                logger.info(
                    "Identity retry triggered task=%s identity=%.2f threshold=%.2f",
                    task_id,
                    identity_match,
                    float(settings.identity_match_threshold or 0.0),
                )
                retry_params = dict(extra) if extra else {}
                retry_params["seed"] = secrets.randbits(31) | 1
                retry_identity = 0.0
                retry_check_failed = False
                try:
                    with _trace_step(trace, "image_gen_retry"):
                        retry_raw = await image_gen.generate(
                            prompt,
                            reference_image=reference_for_provider,
                            params=retry_params,
                        )
                    generation_attempts += 1

                    if retry_raw and len(retry_raw) > 100:
                        retry_raw, cf_applied_r = await self._postprocess(
                            retry_raw,
                            mode=mode,
                            style=style,
                            face_area_ratio=face_area_ratio,
                            apply_quality_post=True,
                            is_retry=True,
                        )
                        codeformer_applied = codeformer_applied or cf_applied_r
                        self._record_fal_call_metric(
                            provider_name=provider_name,
                            backend=first_pass_backend,
                            mode=mode,
                            step="identity_retry",
                        )

                        with _trace_step(
                            trace,
                            "single_pass_gates_retry",
                        ) as rp_entry:
                            (
                                retry_passed,
                                retry_results,
                                retry_report,
                            ) = await gate_runner.run_global_gates(
                                sp_gates,
                                image_bytes,
                                retry_raw,
                            )
                            rp_entry["gates"] = [
                                {
                                    "gate": gr.gate_name,
                                    "passed": gr.passed,
                                    "value": gr.value,
                                }
                                for gr in retry_results
                            ]
                        retry_identity = float(
                            retry_report.get("identity_match") or 0.0
                        )
                        retry_check_failed = bool(
                            retry_report.get("quality_check_failed")
                        )

                        if (
                            not retry_check_failed
                            and retry_identity > identity_match
                        ):
                            raw = retry_raw
                            identity_match = retry_identity
                            sp_report = retry_report
                            sp_passed = retry_passed
                            sp_results = retry_results
                            result_dict["quality_report"] = sp_report
                            if identity_match:
                                IDENTITY_SCORE.observe(
                                    identity_match / 10.0,
                                )
                            logger.info(
                                "Identity retry improved score task=%s %.2f->%.2f",
                                task_id,
                                retry_identity,
                                identity_match,
                            )
                        else:
                            logger.info(
                                "Identity retry did NOT improve task=%s orig=%.2f retry=%.2f check_failed=%s",
                                task_id,
                                identity_match,
                                retry_identity,
                                retry_check_failed,
                            )
                except Exception:
                    logger.warning(
                        "Identity retry generation failed task=%s, keeping original",
                        task_id,
                        exc_info=True,
                    )

                retry_success = retry_identity >= float(
                    settings.identity_match_threshold or 0.0
                )
                try:
                    IDENTITY_RETRY_TRIGGERED.labels(
                        mode=mode.value,
                        result="success" if retry_success else "still_fail",
                    ).inc()
                except Exception:
                    pass

            try:
                GENERATION_ATTEMPTS.labels(
                    mode=mode.value,
                ).observe(generation_attempts)
            except Exception:
                pass

            check_failed = bool(sp_report.get("quality_check_failed"))
            if check_failed:
                result_dict["identity_unverified"] = True
                warnings.append(
                    "Не удалось проверить сходство с оригиналом, "
                    "результат может заметно отличаться. "
                    "Попробуй загрузить другое фото или выбери другой стиль."
                )
            elif identity_match == 0.0 and not sp_report.get("identity_match"):
                pass
            elif identity_match < settings.identity_match_soft_threshold:
                warnings.append(
                    "Сильное отличие от оригинала — рекомендуем другое фото. "
                    "Лучше всего работает чёткое лицо крупным планом, анфас, "
                    "без затемнений и без сложного фона."
                )
            elif identity_match < settings.identity_match_threshold:
                warnings.append(
                    "Результат может заметно отличаться от оригинала. "
                    "Для лучшего сходства загрузи фото в более высоком качестве."
                )

            if not sp_passed:
                logger.warning(
                    "Single-pass quality gates failed for task=%s: %s",
                    task_id,
                    sp_report.get("gates_failed"),
                )
                result_dict["quality_warning"] = True

            if sp_report.get("hair_outline_preserved") is False:
                warnings.append(
                    "Контур волос на итоговом фото отличается от оригинала. "
                    "Для лучшего результата снимите фото на простом однотонном фоне."
                )
            if sp_report.get("background_consistent") is False:
                warnings.append(
                    "На фото заметны артефакты стыка с фоном. "
                    "Попробуйте фото с чистым ровным фоном без сложных деталей."
                )
            if sp_report.get("hands_correct") is False:
                warnings.append(
                    "На фото могут быть неточности в изображении рук. "
                    "Попробуйте снимок, где руки не видны или сложены спокойно."
                )
            if sp_report.get("pose_natural") is False:
                warnings.append(
                    "Поза на итоговом фото выглядит не совсем естественно. "
                    "Лучше всего работает прямая осанка и симметричный кадр."
                )
            if sp_report.get("proportions_natural") is False:
                warnings.append(
                    "На фото пропорции тела могут выглядеть необычно. "
                    "Попробуй фото, где видно плечи и часть торса."
                )

        except Exception:
            logger.warning(
                "Single-pass quality gates error for task=%s, skipping",
                task_id,
                exc_info=True,
            )

        return raw, identity_match, generation_attempts, codeformer_applied

    async def single_pass(
        self,
        mode: AnalysisMode,
        style: str,
        image_bytes: bytes,
        result_dict: dict,
        user_id: str,
        task_id: str,
        trace: dict,
        gender: str = "male",
        input_quality: Any | None = None,
        variant_id: str = "",
        ab_image_model: str = "",
        ab_image_quality: str = "",
        framing: str | None = None,
        user_input_hints: dict | None = None,
        seed: int | None = None,
        scenario_slug: str | None = None,
        allow_cross_model_fallback: bool = True,
        image_refine: str = "",
        product_tier: str = "",
    ) -> None:
        if mode not in (
            AnalysisMode.CV,
            AnalysisMode.EMOJI,
            AnalysisMode.DATING,
            AnalysisMode.SOCIAL,
        ):
            return
        if self._image_gen is None:
            return

        # v1.21 A/B path — resolve a per-request provider + structured
        # prompt instead of the default hybrid StyleRouter. When the
        # feature flag is off or the requested model isn't whitelisted,
        # we silently fall through to the default path: the default
        # hybrid pipeline is bit-for-bit untouched.
        ab_active = bool(getattr(settings, "ab_test_enabled", False) and ab_image_model)
        image_gen: ImageGenProvider = self._image_gen

        # v1.26: framing приходит из task context (см. pipeline._execute_inner),
        # а не из result_dict — LLM анализ никогда не кладёт framing в свой
        # ответ, так что старое чтение result_dict.get("framing") всегда
        # было пустым и frame-selector на UI ничего не менял.
        # v1.71 (Stage 6 refactor): the 75-line framing-resolution block
        # below was extracted into :meth:`_resolve_framing`. Behaviour
        # is byte-for-byte unchanged — same writes to ``result_dict``,
        # same ``framing_resolved`` INFO log, same return shape.
        (
            framing_norm,
            _is_document,
            _is_studio_portrait_style,
            user_picked_framing,
        ) = self._resolve_framing(
            mode=mode,
            style=style,
            framing=framing,
            user_input_hints=user_input_hints,
            input_quality=input_quality,
            result_dict=result_dict,
        )

        try:
            # v1.71 (Stage 6 refactor): the 100-line prompt-build block
            # (PromptEngine.build_image_prompt_v2 + path tag + soft
            # substitution warnings + resolved_slots persistence) was
            # extracted into :meth:`_build_prompt`. Behaviour is
            # byte-for-byte unchanged — same writes to ``result_dict``,
            # same RuntimeError on missing spec, same path tag rules.
            prompt, prompt_pipeline_path = self._build_prompt(
                mode=mode,
                style=style,
                gender=gender,
                variant_id=variant_id,
                ab_image_model=ab_image_model,
                framing_norm=framing_norm,
                seed=seed,
                scenario_slug=scenario_slug,
                input_quality=input_quality,
                user_input_hints=user_input_hints,
                result_dict=result_dict,
            )

            # Face area ratio drives two decisions:
            #   - whether to upscale x2 (bad idea for tiny faces,
            #     amplifies artefacts)
            #   - how strict HAIR protection should be
            #
            # v1.64: the legacy "head_crop_proportion_lock" prompt tail
            # (a paragraph appended AFTER truncate, instructing the
            # model to "rescale head and shoulders") was removed. Its
            # historical successor — the v1.65 cinematic head anchor
            # (``_COMPOSITION_NUMERICAL_HINT``) — was retired in v1.70
            # too. Tight selfies are now exclusively normalised
            # geometrically via
            # ``reference_preprocess.pad_reference_for_framing`` when
            # ``CSL_REFERENCE_PAD_ENABLED=true``.
            face_area_ratio = (
                float(getattr(input_quality, "face_area_ratio", 0.0) or 0.0)
                if input_quality is not None
                else 0.0
            )

            # ``_is_document`` was already resolved above (before the
            # framing resolver) so the same answer drives both the
            # framing pick and the downstream document-aware
            # postprocessing.

            # Provider ``extra`` payload. The single GPT Image 2 Edit
            # backend accepts ``quality`` + ``image_size`` +
            # (legacy) ``image_model``; ``_prepare_provider_params``
            # resolves output size, propagates the AB/tier label, and
            # threads ``effective_aspect_ratio`` into ``result_dict``
            # for the web client's preview crop.
            extra, output_size, iq_bbox = self._prepare_provider_params(
                mode=mode,
                style=style,
                prompt_pipeline_path=prompt_pipeline_path,
                framing_norm=framing_norm,
                face_area_ratio=face_area_ratio,
                input_quality=input_quality,
                ab_active=ab_active,
                ab_image_model=ab_image_model,
                ab_image_quality=ab_image_quality,
                allow_cross_model_fallback=allow_cross_model_fallback,
                result_dict=result_dict,
            )

            raw = None
            identity_match: float = 0.0
            generation_attempts = 0

            will_upscale = bool(
                mode in (AnalysisMode.CV, AnalysisMode.DATING, AnalysisMode.SOCIAL)
                and face_area_ratio >= _UPSCALE_FACE_THRESHOLD
            )
            doc_ar = _document_target_aspect(style) if mode == AnalysisMode.CV else None
            logger.info(
                "Image generation (edit mode) mode=%s style=%s task=%s local_upscale=%s local_crop_ar=%s",
                mode.value,
                style or "default",
                task_id,
                "x2" if will_upscale else "no",
                doc_ar or "none",
            )

            # CSL Phase 1.5 (v1.64) — geometric reference padding.
            # v1.71 (Phase 4.3): the ~140-line gating + PIL block is
            # now in :meth:`_maybe_pad_reference`. Behaviour is
            # byte-for-byte unchanged (same gate, same metric, same
            # log strings, same PIL fallback to ``image_bytes``).
            reference_for_provider = self._maybe_pad_reference(
                image_bytes=image_bytes,
                mode=mode,
                style=style,
                framing_norm=framing_norm,
                face_area_ratio=face_area_ratio,
                iq_bbox=iq_bbox,
                output_size=output_size,
                input_quality=input_quality,
                is_document=_is_document,
                is_studio_portrait_style=_is_studio_portrait_style,
            )

            with _trace_step(trace, "image_gen"):
                raw = await image_gen.generate(
                    prompt,
                    reference_image=reference_for_provider,
                    params=extra or None,
                )
            generation_attempts = 1
            # Single-provider path post Nano-Banana cleanup: the
            # backend label is whatever was propagated into
            # ``extra["image_model"]`` (``gpt_image_2`` for AB-active
            # requests, empty for legacy non-AB callers — the cost
            # estimator falls back to the provider class name).
            first_pass_backend = str(extra.get("image_model", "")).strip().lower()

            # v1.72 — premium refiner. Runs BEFORE the local
            # post-process so Clarity sees the clean generator output
            # (LANCZOS / crop_to_aspect would soften the detail polish
            # Clarity adds). ``image_refine`` is empty on the standard
            # tier so the helper short-circuits — no extra spend.
            clarity_refine_applied = False
            clarity_refine_attempted = False
            clarity_refine_ms = 0
            if (
                raw
                and len(raw) > 100
                and (image_refine or "").strip().lower() == "clarity"
            ):
                clarity_refine_attempted = True
                _t0 = time.perf_counter()
                with _trace_step(trace, "clarity_refine"):
                    raw, clarity_refine_applied = await _apply_clarity_refine(
                        raw,
                    )
                clarity_refine_ms = int((time.perf_counter() - _t0) * 1000)
                try:
                    outcome_label = (
                        "success" if clarity_refine_applied else "fail"
                    )
                    PREMIUM_REFINE_INVOCATIONS.labels(
                        outcome=outcome_label,
                    ).inc()
                    PREMIUM_REFINE_DURATION.observe(
                        clarity_refine_ms / 1000.0,
                    )
                except Exception:
                    pass
                # v1.75 — Premium tier no longer silently downgrades
                # to Standard on refiner failure. The user clicked
                # "Premium" with intent (5 credits) and is owed
                # either a premium-quality image or a clean error
                # with a full refund. Surface a hard error so the
                # worker treats this task as a FAILED task and
                # refunds **all 5 reserved credits** via the
                # failure-path refund block in ``workers/tasks.py``.
                if not clarity_refine_applied:
                    result_dict["premium_refine_failed"] = True
                    raise RuntimeError(
                        "premium_refine_unavailable: Clarity Upscaler "
                        "post-pass failed and tier=premium does not "
                        "downgrade to Standard. All 5 reserved "
                        "credits will be refunded.",
                    )

            codeformer_applied = False
            if raw and len(raw) > 100:
                # v1.71 (Phase 4.4): local + quality post-processing
                # is now a single :meth:`_postprocess` call. On the
                # A/B path (production default) ``apply_quality_post``
                # is ``False`` — Nano Banana 2 / GPT Image 2 emit
                # sharp faces natively so CodeFormer + Real-ESRGAN
                # only add cost and subtle re-rendering artefacts.
                raw, codeformer_applied = await self._postprocess(
                    raw,
                    mode=mode,
                    style=style,
                    face_area_ratio=face_area_ratio,
                    apply_quality_post=not ab_active,
                    is_retry=False,
                )
            provider_name = type(image_gen).__name__
            # v1.20: generic provider-agnostic counter. Name changed
            # from the historical ``ratemeai_reve_calls_total`` to
            # ``ratemeai_image_gen_calls_total``; see ``src/metrics.py``.
            IMAGE_GEN_CALLS.labels(
                mode=mode.value,
                step="single_pass",
                provider=provider_name,
            ).inc()

            # v1.71 (Phase 4.4): FAL model dispatch + counter bump
            # consolidated in :meth:`_record_fal_call_metric`.
            self._record_fal_call_metric(
                provider_name=provider_name,
                backend=first_pass_backend,
                mode=mode,
                step="single_pass",
            )

            if not raw or len(raw) <= 100:
                logger.warning(
                    "Image gen returned empty/tiny result (%s bytes)",
                    len(raw) if raw else 0,
                )
                raw = None

            warnings: list[str] = result_dict.setdefault("generation_warnings", [])

            if raw and len(raw) > 100 and mode != AnalysisMode.EMOJI:
                # v1.71 (Phase 4.6): VLM gates + identity-retry loop +
                # user-facing quality warnings consolidated in
                # :meth:`_run_with_retry`. Contract pinned by
                # ``tests/test_orchestrator/test_identity_retry.py``.
                raw, identity_match, generation_attempts, codeformer_applied = (
                    await self._run_with_retry(
                        raw,
                        image_bytes=image_bytes,
                        image_gen=image_gen,
                        prompt=prompt,
                        reference_for_provider=reference_for_provider,
                        extra=extra,
                        mode=mode,
                        style=style,
                        task_id=task_id,
                        trace=trace,
                        result_dict=result_dict,
                        warnings=warnings,
                        provider_name=provider_name,
                        first_pass_backend=first_pass_backend,
                        face_area_ratio=face_area_ratio,
                        generation_attempts=generation_attempts,
                        codeformer_applied=codeformer_applied,
                    )
                )

            if raw and len(raw) > 100:
                # v1.71 (Phase 4.5): storage upload + cost/backend
                # metrics consolidated in :meth:`_persist_and_metric`.
                await self._persist_and_metric(
                    raw,
                    user_id=user_id,
                    task_id=task_id,
                    mode=mode,
                    style=style,
                    result_dict=result_dict,
                    first_pass_backend=first_pass_backend,
                    ab_active=ab_active,
                    ab_image_model=ab_image_model,
                    ab_image_quality=ab_image_quality,
                    extra=extra,
                    provider_name=provider_name,
                    identity_match=identity_match,
                    generation_attempts=generation_attempts,
                    codeformer_applied=codeformer_applied,
                    face_area_ratio=face_area_ratio,
                    clarity_refine_applied=clarity_refine_applied,
                    clarity_refine_attempted=clarity_refine_attempted,
                    clarity_refine_ms=clarity_refine_ms,
                    product_tier=product_tier,
                )
            else:
                logger.warning(
                    "Image gen returned no usable result for task=%s", task_id
                )
                result_dict["image_gen_error"] = "empty_result"
                warnings.append(
                    "Не удалось сгенерировать улучшенное фото. "
                    "Попробуй загрузить другое фото или выбрать другой стиль."
                )
        except Exception as exc:
            logger.exception("Image generation failed for mode %s", mode.value)
            result_dict["image_gen_error"] = "generation_failed"
            result_dict["image_gen_error_message"] = _format_image_gen_error(exc)
            result_dict.setdefault("generation_warnings", []).append(
                "Произошла ошибка при генерации. Попробуй ещё раз или загрузи другое фото."
            )


_PHI = 1.618
_MAX_DELTA = round(1 / _PHI, 2)  # 0.62
_MIN_POSITIVE_DELTA = 0.03


def _golden_delta(raw_delta: float, seed: str = "") -> float:
    """Clamp delta to gamification-friendly range with seed-based variation.

    Always returns a positive delta (gamification guarantee).
    """
    h = int(hashlib.md5(seed.encode()).hexdigest()[:4], 16) if seed else 0
    variation = ((h % 25) - 12) / 100.0
    if raw_delta <= 0:
        return round(
            max(_MIN_POSITIVE_DELTA + abs(variation) * 0.5, _MIN_POSITIVE_DELTA), 2
        )
    cap = _MAX_DELTA + variation
    clamped = min(raw_delta, cap)
    return round(max(clamped, _MIN_POSITIVE_DELTA), 2)


def _build_delta_entry(pre: float, raw_post: float, seed: str = "") -> dict:
    """Build a single {pre, post, delta} entry with golden-clamped delta."""
    gd = _golden_delta(raw_post - pre, seed)
    post = round(pre + gd, 2)
    if post <= pre:
        post = round(pre + _MIN_POSITIVE_DELTA, 2)
        gd = round(post - pre, 2)
    return {"pre": round(pre, 2), "post": post, "delta": gd}


def _compute_authenticity(quality_report: dict) -> float:
    """Derive authenticity score from quality gate results.

    Authenticity is a guarantee parameter (not a growth metric): it reflects
    how real and identity-preserving the generated photo is.

    Inputs are purely stateless scalars produced by the VLM quality gate
    (no local face embeddings): ``identity_match`` on 0-10 scale is
    rescaled to 0-1, everything else is used as-is.
    """
    # identity_match is 0-10 (VLM scale); if absent (e.g. single-image
    # quality check without reference), fall back to a neutral 0.9 ≈ 9/10.
    id_match_raw = quality_report.get("identity_match")
    if id_match_raw is None:
        id_factor = 0.9
    else:
        id_factor = max(0.0, min(1.0, float(id_match_raw) / 10.0))

    photorealism = float(quality_report.get("photorealism_confidence") or 0.8)
    is_real = quality_report.get("is_photorealistic", True)
    teeth_ok = quality_report.get("teeth_natural", True)
    expr_ok = not quality_report.get("expression_altered", False)
    naturalness = 1.0 if (teeth_ok and expr_ok) else 0.5

    if not is_real:
        photorealism *= 0.5

    raw = id_factor * 4.0 + photorealism * 3.0 + naturalness * 3.0
    return round(min(9.99, max(5.0, raw)), 2)


_SCORE_REDIS_KEY = "ratemeai:score:{}:{}:{}"  # user_id:mode:style
_SCORE_TTL = 86400


class DeltaScorer:
    """Re-scores the generated image and computes before/after delta.

    Supports score progression: if a previous post score exists in Redis,
    it is used as the new pre baseline so scores accumulate across generations.
    """

    def __init__(self, router, storage: StorageProvider, redis=None):
        self._router = router
        self._storage = storage
        self._redis = redis

    async def _load_previous_scores(
        self,
        user_id: str,
        mode: AnalysisMode,
        style: str = "default",
    ) -> dict | None:
        if not self._redis:
            return None
        try:
            import json as _json

            raw = await self._redis.get(
                _SCORE_REDIS_KEY.format(user_id, mode.value, style)
            )
            if raw:
                return _json.loads(raw)
        except Exception:
            logger.debug(
                "Failed to load previous scores for user=%s mode=%s style=%s",
                user_id,
                mode.value,
                style,
            )
        return None

    async def _save_scores(
        self,
        user_id: str,
        mode: AnalysisMode,
        scores: dict,
        style: str = "default",
    ) -> None:
        if not self._redis:
            return
        try:
            import json as _json

            await self._redis.set(
                _SCORE_REDIS_KEY.format(user_id, mode.value, style),
                _json.dumps(scores),
                ex=_SCORE_TTL,
            )
        except Exception:
            logger.debug(
                "Failed to save scores for user=%s mode=%s style=%s",
                user_id,
                mode.value,
                style,
            )

    async def compute(
        self,
        mode: AnalysisMode,
        result_dict: dict,
        user_id: str,
        task_id: str,
    ) -> None:
        """Delta re-score the generated image.

        The original bytes are no longer needed here — pre-scores are taken
        from ``result_dict`` (populated by the primary LLM pass or cached
        pre-analysis), and authenticity is derived from the quality report
        that was already produced during the synchronous single-pass/
        multi-pass quality gate (stateless VLM check, no persisted
        biometric artefacts). This keeps the original image out of the
        worker's working set after preprocessing.
        """
        try:
            gen_key = f"generated/{user_id}/{task_id}.jpg"
            gen_bytes = await self._storage.download(gen_key)
            if not gen_bytes:
                return

            service = self._router.get_service(mode)
            if mode == AnalysisMode.CV:
                post_result = await service.analyze(
                    gen_bytes, profession=result_dict.get("profession", "не указана")
                )
            else:
                post_result = await service.analyze(gen_bytes)

            post_dict = (
                post_result.model_dump()
                if hasattr(post_result, "model_dump")
                else post_result
            )

            from src.utils.humanize import (
                SCORE_FLOOR as _SCORE_FLOOR,
                PERCEPTION_FLOOR as _PERCEPTION_FLOOR,
            )

            def _floor_post(raw: float, floor: float = _SCORE_FLOOR) -> float:
                return max(float(raw), floor)

            style = result_dict.get("enhancement", {}).get("style", "default")
            prev = await self._load_previous_scores(user_id, mode, style)
            prev_scores = prev.get("scores", {}) if prev else {}
            prev_perception = prev.get("perception", {}) if prev else {}

            delta: dict[str, Any] = {}
            new_scores: dict[str, float] = {}

            if mode == AnalysisMode.DATING:
                pre = (
                    float(prev_scores.get("dating_score", 0))
                    or float(result_dict.get("dating_score", 0))
                    or float(result_dict.get("score", 0))
                )
                raw_post = _floor_post(post_dict.get("dating_score", 0))
                entry = _build_delta_entry(pre, raw_post, f"{task_id}:dating_score")
                delta = {"dating_score": entry}
                new_scores["dating_score"] = entry["post"]
            elif mode == AnalysisMode.CV:
                for key in ("trust", "competence", "hireability"):
                    pre = float(prev_scores.get(key, 0)) or float(
                        result_dict.get(key, 0)
                    )
                    raw_post = _floor_post(post_dict.get(key, 0))
                    entry = _build_delta_entry(pre, raw_post, f"{task_id}:{key}")
                    delta[key] = entry
                    new_scores[key] = entry["post"]
            elif mode == AnalysisMode.SOCIAL:
                pre = (
                    float(prev_scores.get("social_score", 0))
                    or float(result_dict.get("social_score", 0))
                    or float(result_dict.get("score", 0))
                )
                raw_post = _floor_post(post_dict.get("social_score", 0))
                entry = _build_delta_entry(pre, raw_post, f"{task_id}:social_score")
                delta = {"social_score": entry}
                new_scores["social_score"] = entry["post"]

            result_dict["delta"] = delta

            if mode == AnalysisMode.CV:
                pre_vals = [
                    delta[k]["pre"]
                    for k in ("trust", "competence", "hireability")
                    if k in delta
                ]
                result_dict["score_before"] = (
                    round(sum(pre_vals) / len(pre_vals), 2) if pre_vals else None
                )
                post_vals = [
                    delta[k]["post"]
                    for k in ("trust", "competence", "hireability")
                    if k in delta
                ]
                result_dict["score_after"] = (
                    round(sum(post_vals) / len(post_vals), 2) if post_vals else None
                )
            else:
                first_key = next(iter(delta), None)
                result_dict["score_before"] = (
                    delta[first_key]["pre"] if first_key else None
                )
                result_dict["score_after"] = (
                    delta[first_key]["post"] if first_key else None
                )

            # IMPORTANT: overwrite top-level scalar score fields with post-gen
            # values so that any downstream consumer that reads the flat
            # `dating_score` / `social_score` / `score` / CV metrics (e.g. the
            # `/tasks/history` endpoint) sees the improvement dynamics of the
            # generated photo, not the pre-generation baseline.
            if mode == AnalysisMode.DATING and "dating_score" in delta:
                result_dict["dating_score"] = delta["dating_score"]["post"]
                result_dict["score"] = delta["dating_score"]["post"]
            elif mode == AnalysisMode.SOCIAL and "social_score" in delta:
                result_dict["social_score"] = delta["social_score"]["post"]
                result_dict["score"] = delta["social_score"]["post"]
            elif mode == AnalysisMode.CV:
                for key in ("trust", "competence", "hireability"):
                    if key in delta:
                        result_dict[key] = delta[key]["post"]

            pre_perception = result_dict.get("perception_scores", {})
            if hasattr(pre_perception, "model_dump"):
                pre_perception = pre_perception.model_dump()
            post_perception = post_dict.get("perception_scores", {})
            if hasattr(post_perception, "model_dump"):
                post_perception = post_perception.model_dump()

            perception_delta: dict[str, Any] = {}
            new_perception: dict[str, float] = {}
            for key in ("warmth", "presence", "appeal"):
                pre_val = float(prev_perception.get(key, 0)) or float(
                    pre_perception.get(key, 5.0)
                )
                raw_post_val = _floor_post(
                    float(post_perception.get(key, 5.0)), floor=_PERCEPTION_FLOOR
                )
                entry = _build_delta_entry(pre_val, raw_post_val, f"{task_id}:p:{key}")
                perception_delta[key] = entry
                new_perception[key] = entry["post"]

            result_dict["perception_delta"] = perception_delta

            await self._save_scores(
                user_id,
                mode,
                {
                    "scores": new_scores,
                    "perception": new_perception,
                },
                style,
            )

            quality_report = result_dict.get("quality_report", {})
            if quality_report:
                auth_score = _compute_authenticity(quality_report)
            else:
                auth_score = 9.0

            # Update perception_scores in place so that personal-best tracking
            # (`_persist_perception_scores`) and any API consumer reading the
            # flat map see the post-generation values. We normalise to a dict
            # first — the analysis layer may have returned a pydantic model.
            ps = result_dict.get("perception_scores")
            if hasattr(ps, "model_dump"):
                ps = ps.model_dump()
            if not isinstance(ps, dict):
                ps = {}
            for key in ("warmth", "presence", "appeal"):
                if key in perception_delta:
                    ps[key] = perception_delta[key]["post"]
            ps["authenticity"] = auth_score
            result_dict["perception_scores"] = ps

            result_dict["post_score"] = post_dict
            logger.info(
                "Delta computed for task=%s: %s perception: %s",
                task_id,
                delta,
                perception_delta,
            )
        except Exception:
            logger.exception("Post-gen re-scoring failed for task=%s", task_id)
            result_dict["delta_error"] = "rescoring_failed"

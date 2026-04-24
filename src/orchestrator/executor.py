"""ImageGenerationExecutor and DeltaScorer — extracted from AnalysisPipeline.

Handles single-pass image generation and post-generation delta scoring
as standalone collaborators. Multi-pass plan execution lives in
:mod:`src.orchestrator.advanced.execute_plan` and is reserved for future
premium / advanced scenarios (see ``docs/architecture/reserved.md``).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
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
    STYLE_MODE_OVERRIDE,
    estimate_image_gen_cost_usd,
)
from src.models.enums import AnalysisMode
from src.orchestrator.errors import format_image_gen_error
from src.orchestrator.trace import trace_step as _trace_step
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import STYLE_REGISTRY, resolve_output_size
from src.providers.base import ImageGenProvider, StorageProvider
from src.services.postprocess import (
    crop_to_aspect,
    inject_exif_only,
    upscale_lanczos,
)

# Target aspect ratio for CV document styles. Applied *locally* after
# generation via PIL (see src.services.postprocess.crop_to_aspect) —
# none of the currently wired FAL edit models (FLUX.2, Seedream,
# PuLID) accept an arbitrary aspect_ratio knob, so we enforce it
# ourselves after the generation step.
_CV_DOCUMENT_ASPECT: dict[str, str] = {
    "photo_3x4": "3:4",  # 30×40 мм
    "passport_rf": "3:4",  # 35×45 мм ≈ 3:4
    "visa_eu": "3:4",  # 35×45 мм ≈ 3:4
    "visa_schengen": "3:4",  # 35×45 мм
    "visa_us": "1:1",  # 50×50 мм
    "photo_4x6": "2:3",  # 40×60 мм
    "driver_license": "3:4",
}


def _document_target_aspect(style: str) -> str | None:
    """Return the local-crop target AR for a CV document style, else None."""
    return _CV_DOCUMENT_ASPECT.get((style or "").strip())


# Face-area threshold above which we locally LANCZOS-upscale the
# generated image x2 (bigger faces benefit from extra detail; smaller
# faces just amplify upscaling artefacts).
_UPSCALE_FACE_THRESHOLD = 0.15


# Nano Banana 2 aspect-ratio enum (fal schema). See
# ``src/providers/image_gen/fal_nano_banana.py:_VALID_ASPECT_RATIOS``.
_NB2_ASPECT_BUCKETS: tuple[tuple[float, str], ...] = (
    # Ordered from tall portrait to wide landscape so ``min(..)`` picks
    # the closest bucket by signed distance from the requested ratio.
    (9 / 16, "9:16"),
    (2 / 3, "2:3"),
    (3 / 4, "3:4"),
    (4 / 5, "4:5"),
    (1.0, "1:1"),
    (5 / 4, "5:4"),
    (4 / 3, "4:3"),
    (3 / 2, "3:2"),
    (16 / 9, "16:9"),
    (21 / 9, "21:9"),
)


def _aspect_ratio_enum_for_size(width: int, height: int) -> str:
    """Snap an arbitrary ``(width, height)`` onto the NB2 AR enum.

    Nano Banana 2 Edit does not accept a raw ``{width, height}``; it
    needs an enum from the fixed list (``4:5``, ``3:4``, ``16:9`` …).
    We pick the closest bucket by the ratio ``width / height`` so a
    portrait StyleSpec (e.g. 1024x1536 from ``resolve_output_size``)
    maps to ``2:3`` and a CV landscape (e.g. 1536x1024) to ``3:2``.

    Returning ``auto`` defeats the purpose — the model then reframes
    4K outputs into square and crops the head out, which we saw in
    v1.22. Always return a concrete enum.
    """
    try:
        w = int(width or 0)
        h = int(height or 0)
    except (TypeError, ValueError):
        return "auto"
    if w <= 0 or h <= 0:
        return "auto"
    target = w / h
    return min(_NB2_ASPECT_BUCKETS, key=lambda b: abs(b[0] - target))[1]


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
    generation_mode: str,
    *,
    image_size: dict | None = None,
    routed_backend: str | None = None,
) -> tuple[str, float]:
    """Estimate per-call cost *and* label the effective backend.

    v1.20: for StyleRouter deployments we now read ``routed_backend``
    — the real label set by ``StyleRouter.generate()`` via a
    ContextVar — instead of guessing from ``generation_mode``. That
    way, when the router degrades ``identity_scene → scene_preserve``
    (face-crop failure), the Prometheus label and the cost math
    reflect the Seedream call that actually ran, not the PuLID one
    we asked for.

    For legacy direct-provider setups (no StyleRouter, no ContextVar)
    we fall back to ``estimate_image_gen_cost_usd`` keyed off the
    provider class name.
    """
    cls = (provider_name or "").lower()
    routed = (routed_backend or "").strip().lower()
    if cls == "stylerouter":
        if routed == "pulid":
            backend = "pulid"
            cost = float(getattr(settings, "model_cost_fal_pulid", 0.006))
        elif routed == "seedream":
            backend = "seedream"
            cost = float(getattr(settings, "model_cost_fal_seedream", 0.03))
        elif routed == "fallback":
            backend = "fallback"
            cost = float(
                estimate_image_gen_cost_usd(
                    "FalFlux2ImageGen",
                    image_size=image_size,
                )
            )
        else:
            # Router has not run yet (e.g. unit tests without a real
            # request) — derive from the *requested* mode as before
            # so legacy test expectations still hold.
            if (generation_mode or "").strip() == "scene_preserve":
                backend = "seedream"
                cost = float(getattr(settings, "model_cost_fal_seedream", 0.03))
            else:
                backend = "pulid"
                cost = float(getattr(settings, "model_cost_fal_pulid", 0.006))
        return backend, cost

    backend = cls or "fallback"
    if "pulid" in cls:
        backend = "pulid"
    elif "seedream" in cls:
        backend = "seedream"
    elif "flux" in cls:
        backend = "fallback"
    cost = float(estimate_image_gen_cost_usd(provider_name, image_size=image_size))
    return backend, cost


async def _apply_codeformer_post(
    raw: bytes,
    *,
    generation_mode: str | None = None,
    face_area_ratio: float | None = None,
    is_retry: bool = False,
) -> tuple[bytes, bool]:
    """Run CodeFormer face polish after the main generator.

    v1.19 gating:

    - Skips identity_scene (PuLID) by default (``codeformer_for_identity_scene``
      flag). The 25-step PuLID preset outputs sharp faces by itself and
      CodeFormer was nudging identity off.
    - Skips tiny faces (``face_area_ratio < codeformer_min_face_ratio``)
      — polish is imperceptible at that scale.
    - Skips retry calls by default (``codeformer_on_retry``) — the
      retry is about identity recovery, not sharpness.

    v1.18+ — FLUX Lightning (under PuLID) and Seedream-edit both
    produce slightly soft faces. CodeFormer re-sharpens facial
    features while ``fidelity`` (~0.5) keeps the identity from
    drifting toward the "perfect face" restoration extreme.

    Returns ``(bytes, applied)`` where ``applied`` indicates whether
    CodeFormer actually ran (False = feature disabled, no API key, or
    provider error — in which case the original bytes are returned).
    """
    if not raw or len(raw) <= 100:
        return raw, False
    if not bool(getattr(settings, "codeformer_enabled", False)):
        return raw, False

    if generation_mode == "identity_scene" and not bool(
        getattr(
            settings,
            "codeformer_for_identity_scene",
            False,
        )
    ):
        logger.debug(
            "CodeFormer skipped: identity_scene (PuLID handles face)",
        )
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

    Multi-pass execution (``execute_plan``) lives in
    :mod:`src.orchestrator.advanced.execute_plan` and is *not* wired into
    this class on purpose — see ``docs/architecture/reserved.md``.
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

        # Extract framing parameter if present
        framing = str(result_dict.get("framing", "")).strip().lower()
        if framing not in ("portrait", "half_body", "full_body"):
            framing = None

        image_gen: ImageGenProvider = self._image_gen

        try:
            desc = str(result_dict.get("base_description", ""))
            input_hints = (
                input_quality.to_prompt_hints() if input_quality is not None else None
            )

            prompt = self._prompt_engine.build_image_prompt(
                mode,
                style=style,
                base_description=desc,
                gender=gender,
                input_hints=input_hints,
                variant_id=variant_id,
                target_model=ab_image_model,
            )

            if variant_id:
                result_dict["variant_id"] = variant_id

            # Face area ratio drives two decisions:
            #   - whether to upscale x2 (bad idea for tiny faces, amplifies artefacts)
            #   - how strict HAIR protection should be
            face_area_ratio = (
                float(getattr(input_quality, "face_area_ratio", 0.0) or 0.0)
                if input_quality is not None
                else 0.0
            )

            # Provider ``extra`` payload. Provider-specific whitelists
            # apply: FalFlux2ImageGen accepts ``image_size`` + ``seed``,
            # PuLID accepts ``num_inference_steps`` + ``guidance_scale``
            # + ``id_scale``, Seedream accepts ``enhance_prompt_mode``.
            # Anything the StyleRouter does not recognise is stripped
            # before reaching the wire. Document AR crops and the x2
            # LANCZOS upscale still happen locally in
            # ``_apply_local_postprocess``.
            extra: dict = {}

            # Output resolution per style. FLUX.2 Pro Edit honours
            # ``image_size`` with a concrete ``{width, height}`` dict —
            # we pin each style to its target aspect (2 MP portrait for
            # headshot/full-body, 1 MP square for documents). Legacy
            # Kontext / Seedream providers silently ignore the key.
            spec = STYLE_REGISTRY.get(mode.value, style)
            # v1.18 hybrid pipeline: thread the StyleSpec generation mode
            # through ``params`` so :class:`StyleRouter` can route to
            # PuLID (identity_scene) vs Seedream (scene_preserve). The
            # field is ignored by legacy non-routing providers.
            generation_mode = (
                getattr(
                    spec,
                    "generation_mode",
                    "identity_scene",
                )
                if spec is not None
                else "identity_scene"
            )
            extra["generation_mode"] = generation_mode

            # v1.20: pass the face bbox discovered by the input-quality
            # gate through to StyleRouter → face_crop so we don't
            # re-run MediaPipe for the same image. Routers / providers
            # that don't understand the key strip it; see
            # :meth:`StyleRouter.generate`.
            iq_bbox = getattr(input_quality, "face_bbox", None)
            if iq_bbox is not None:
                extra["face_bbox"] = iq_bbox

            # v1.19+: identity_scene (PuLID) runs at 1 MP to avoid
            # duplicate-subject artefacts; scene_preserve stays at 2 MP.
            # Legacy FAL providers silently ignore ``image_size``.
            output_size = resolve_output_size(
                spec,
                face_area_ratio=face_area_ratio or None,
                generation_mode=generation_mode,
                framing=framing,
            )
            if output_size:
                extra["image_size"] = output_size
                mp = (output_size["width"] * output_size["height"]) / 1_000_000
                logger.info(
                    "image_size resolved mode=%s style=%s gen_mode=%s "
                    "size=%dx%d (~%.2f MP)",
                    mode.value,
                    style or "default",
                    generation_mode,
                    output_size["width"],
                    output_size["height"],
                    mp,
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
            # v1.20: reset the router backend ContextVar before each
            # call so leftover state from a previous request in the
            # same worker cannot poison the cost label.
            try:
                from src.providers.image_gen.unified import (
                    routed_backend_var,
                )

                routed_backend_var.set("")
            except Exception:
                pass
            # v1.21 A/B: inject ``quality`` into the provider params so
            # FalNanoBanana2Edit / FalGptImage2Edit pick the right tier.
            # Hybrid StyleRouter silently ignores the key.
            if ab_active:
                # v1.24.2: propagate the caller-selected A/B model into the
                # provider params so ``UnifiedImageGenProvider._pick_backend``
                # actually routes on it. Prior to this, ``extra`` held only
                # ``quality`` / ``aspect_ratio`` and the picker fell through
                # to its ``model_a`` (GPT-2) default on every request —
                # Nano Banana 2 was only reachable via the catch-fallback
                # path after GPT-2 raised. See unified.py::_pick_backend.
                extra["image_model"] = ab_image_model
                extra["quality"] = ab_image_quality or getattr(
                    settings, "ab_default_quality", "medium"
                )
                # v1.23: derive a Nano Banana 2 aspect_ratio enum from
                # the resolved StyleSpec output_size. NB2 does NOT
                # accept a raw ``{width, height}`` — it needs an enum
                # from its white-list (``4:5``, ``3:4``, ``16:9`` etc.).
                # Without this the provider defaults to ``auto`` and
                # tends to reframe portraits into square at 4K, which
                # crops the head and drops identity match. GPT Image 2
                # uses ``image_size`` (already in ``extra``) — no-op
                # here for that provider.
                if output_size and not extra.get("aspect_ratio"):
                    extra["aspect_ratio"] = _aspect_ratio_enum_for_size(
                        output_size["width"],
                        output_size["height"],
                    )
                # v1.23: strip the legacy ``generation_mode`` key for
                # the A/B path — NB2 / GPT-2 don't understand PuLID vs
                # Seedream semantics, and keeping it around makes
                # observability harder (looks like we're still routing
                # through StyleRouter).
                extra.pop("generation_mode", None)

            with _trace_step(trace, "image_gen"):
                raw = await image_gen.generate(
                    prompt,
                    reference_image=image_bytes,
                    params=extra or None,
                )
            generation_attempts = 1
            # v1.20: snapshot the routed backend *immediately* after
            # generate() so a retry call below cannot overwrite the
            # first-pass label before we read it.
            try:
                from src.providers.image_gen.unified import (
                    get_routed_backend,
                )

                first_pass_backend = get_routed_backend()
            except Exception:
                first_pass_backend = ""

            codeformer_applied = False
            if raw and len(raw) > 100:
                raw = _apply_local_postprocess(raw, mode, style, face_area_ratio)
                # v1.19: CodeFormer only runs for scene_preserve paths
                # (Seedream edits) and only when the face is large
                # enough to show polish. identity_scene outputs from
                # PuLID are already sharp at 25 steps.
                # v1.23: on the A/B path we DO NOT run CodeFormer /
                # Real-ESRGAN. Nano Banana 2 and GPT Image 2 already
                # emit clean, sharp faces at native resolution (1K–4K
                # for NB2, up to 2560 for GPT-2). CodeFormer subtly
                # re-renders facial features — exactly what we spent
                # the A/B model budget trying to avoid. Real-ESRGAN
                # x2 on an already-4K image only adds compression
                # artefacts and doubles FAL spend. The legacy
                # StyleRouter path keeps both stages for PuLID /
                # Seedream outputs that were trained at 1 MP.
                if not ab_active:
                    raw, cf_applied = await _apply_codeformer_post(
                        raw,
                        generation_mode=generation_mode,
                        face_area_ratio=face_area_ratio or None,
                        is_retry=False,
                    )
                    codeformer_applied = codeformer_applied or cf_applied
                    raw = await _maybe_real_esrgan_upscale(raw, face_area_ratio)
            provider_name = type(image_gen).__name__
            # v1.20: generic provider-agnostic counter. Name changed
            # from the historical ``ratemeai_reve_calls_total`` to
            # ``ratemeai_image_gen_calls_total``; see ``src/metrics.py``.
            IMAGE_GEN_CALLS.labels(
                mode=mode.value,
                step="single_pass",
                provider=provider_name,
            ).inc()

            fal_model: str | None = None
            if provider_name.lower() == "unifiedimagegenprovider":
                if first_pass_backend == "pulid":
                    fal_model = getattr(settings, "pulid_model", "fal-ai/pulid")
                elif first_pass_backend == "seedream":
                    fal_model = getattr(
                        settings,
                        "seedream_model",
                        "fal-ai/bytedance/seedream/v4/edit",
                    )
                elif first_pass_backend == "nano_banana_2":
                    fal_model = getattr(
                        settings, "nano_banana_model", "fal-ai/nano-banana-2/edit"
                    )
                elif first_pass_backend == "gpt_image_2":
                    fal_model = getattr(
                        settings, "gpt_image_2_model", "openai/gpt-image-2/edit"
                    )
            elif "nanobanana" in provider_name.lower():
                fal_model = getattr(
                    settings, "nano_banana_model", "fal-ai/nano-banana-2/edit"
                )
            elif "gptimage" in provider_name.lower():
                fal_model = getattr(
                    settings, "gpt_image_2_model", "openai/gpt-image-2/edit"
                )

            if fal_model:
                try:
                    FAL_CALLS.labels(
                        mode=mode.value,
                        step="single_pass",
                        model=fal_model,
                    ).inc()
                except Exception as e:
                    logger.warning(
                        "Failed to record FAL_CALLS metric for single_pass: %s", e
                    )

            if not raw or len(raw) <= 100:
                logger.warning(
                    "Image gen returned empty/tiny result (%s bytes)",
                    len(raw) if raw else 0,
                )
                raw = None

            warnings: list[str] = result_dict.setdefault("generation_warnings", [])

            if raw and len(raw) > 100 and mode != AnalysisMode.EMOJI:
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

                    # v1.17: VLM-driven identity retry loop.
                    # If the first generation came back with
                    # identity_match < threshold (a numeric score, not a
                    # VLM-check failure), re-run generate() with a fresh
                    # random seed and keep whichever output has the higher
                    # identity_match. We ignore quality_check_failed paths —
                    # the VLM can't tell us anything useful about that run
                    # and retrying doubles the cost without a decision
                    # signal. Capped at settings.identity_retry_max_attempts
                    # additional attempts (default 1).
                    # v1.23: the A/B path has its own feature flag so we
                    # can keep PuLID retries alive without blowing budget
                    # on NB2 / GPT-2 calls. The legacy retry sends
                    # ``pulid_mode`` + ``id_scale`` escalation which both
                    # A/B providers silently strip, so a retry under the
                    # old flag only bought a fresh seed at 2× cost.
                    if ab_active:
                        retry_enabled = bool(
                            getattr(settings, "ab_identity_retry_enabled", False)
                        )
                    else:
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
                        # Fresh positive 31-bit seed — matches the FAL
                        # provider default domain; | 1 avoids the rare
                        # zero case that some back-ends treat as "use
                        # default seed".
                        retry_params["seed"] = secrets.randbits(31) | 1
                        # v1.18: if PuLID's identity lock failed hard
                        # (<5.0), escalate to the strongest knob combo
                        # the model exposes: ``mode=extreme style`` +
                        # ``id_scale=1.0``. These are both clamped by
                        # the provider, so overshooting is safe.
                        soft_threshold = float(
                            settings.identity_match_soft_threshold or 0.0
                        )
                        is_identity_scene = generation_mode == "identity_scene"
                        if (
                            is_identity_scene
                            and identity_match > 0.0
                            and identity_match < soft_threshold
                        ):
                            # v1.19 retry escalation (FIXED).
                            #
                            # The v1.18 retry flipped PuLID into
                            # ``mode="extreme style"`` — but per the
                            # fal-ai/pulid schema that mode *weakens*
                            # identity in favour of stylisation, which
                            # is the opposite of what we want on an
                            # identity_match failure. Stay on
                            # ``fidelity`` and instead push id_scale,
                            # steps and guidance higher.
                            retry_params["pulid_mode"] = "fidelity"
                            retry_params["id_scale"] = float(
                                getattr(
                                    settings,
                                    "pulid_retry_id_scale",
                                    1.2,
                                )
                            )
                            retry_params["num_inference_steps"] = int(
                                getattr(
                                    settings,
                                    "pulid_retry_steps",
                                    8,
                                )
                            )
                            retry_params["guidance_scale"] = float(
                                getattr(
                                    settings,
                                    "pulid_retry_guidance_scale",
                                    1.4,
                                )
                            )
                            logger.info(
                                "PuLID retry strengthened task=%s "
                                "mode=fidelity id_scale=%.2f steps=%d "
                                "guidance=%.2f",
                                task_id,
                                retry_params["id_scale"],
                                retry_params["num_inference_steps"],
                                retry_params["guidance_scale"],
                            )
                            try:
                                STYLE_MODE_OVERRIDE.labels(
                                    from_mode="identity_scene",
                                    to_mode="identity_scene",
                                    reason="retry_escalate_pulid",
                                ).inc()
                            except Exception:
                                pass
                        retry_identity = 0.0
                        retry_check_failed = False
                        try:
                            with _trace_step(trace, "image_gen_retry"):
                                retry_raw = await image_gen.generate(
                                    prompt,
                                    reference_image=image_bytes,
                                    params=retry_params,
                                )
                            generation_attempts += 1

                            if retry_raw and len(retry_raw) > 100:
                                retry_raw = _apply_local_postprocess(
                                    retry_raw,
                                    mode,
                                    style,
                                    face_area_ratio,
                                )
                                retry_raw, cf_applied_r = await _apply_codeformer_post(
                                    retry_raw,
                                    generation_mode=generation_mode,
                                    face_area_ratio=(face_area_ratio or None),
                                    is_retry=True,
                                )
                                codeformer_applied = codeformer_applied or cf_applied_r
                                retry_raw = await _maybe_real_esrgan_upscale(
                                    retry_raw,
                                    face_area_ratio,
                                )
                                # v1.20: retry counter keyed on the
                                # *routed* backend so PuLID retries
                                # also land in Grafana. Falls back to
                                # the legacy class-name check for
                                # non-router provider setups.
                                try:
                                    from src.providers.image_gen.unified import (
                                        get_routed_backend,
                                    )

                                    retry_backend = get_routed_backend()
                                except Exception:
                                    retry_backend = ""
                                retry_fal_model: str | None = None
                                if provider_name.lower() == "unifiedimagegenprovider":
                                    if retry_backend == "pulid":
                                        retry_fal_model = getattr(
                                            settings,
                                            "pulid_model",
                                            "fal-ai/pulid",
                                        )
                                    elif retry_backend == "seedream":
                                        retry_fal_model = getattr(
                                            settings,
                                            "seedream_model",
                                            "fal-ai/bytedance/seedream/v4/edit",
                                        )
                                    elif retry_backend == "nano_banana_2":
                                        retry_fal_model = getattr(
                                            settings,
                                            "nano_banana_model",
                                            "fal-ai/nano-banana-2/edit",
                                        )
                                    elif retry_backend == "gpt_image_2":
                                        retry_fal_model = getattr(
                                            settings,
                                            "gpt_image_2_model",
                                            "openai/gpt-image-2/edit",
                                        )
                                elif "nanobanana" in provider_name.lower():
                                    retry_fal_model = getattr(
                                        settings,
                                        "nano_banana_model",
                                        "fal-ai/nano-banana-2/edit",
                                    )
                                elif "gptimage" in provider_name.lower():
                                    retry_fal_model = getattr(
                                        settings,
                                        "gpt_image_2_model",
                                        "openai/gpt-image-2/edit",
                                    )

                                if retry_fal_model:
                                    try:
                                        FAL_CALLS.labels(
                                            mode=mode.value,
                                            step="identity_retry",
                                            model=retry_fal_model,
                                        ).inc()
                                    except Exception:
                                        pass

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

                                # Keep the retry only if it delivers a
                                # strictly higher identity_match and the
                                # VLM check did not blow up on it. Ties
                                # fall back to the original — no reason
                                # to pay an extra FAL call and pick the
                                # later output arbitrarily.
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

                    # Soft, user-facing warnings when identity preservation
                    # drops. Three distinct states, each with its own UX:
                    #   1) quality_check_failed — VLM call / JSON parsing
                    #      actually errored. We must NOT treat this as a silent
                    #      pass (that was the pre-1.14.2 bug that delivered
                    #      mismatched photos to users). Surface an explicit
                    #      "unverified" warning so results.py can offer the
                    #      retry/accept keyboard.
                    #   2) identity_match is null with no error — VLM simply
                    #      had no reference to compare to; legitimate pass.
                    #   3) numeric score below soft/hard threshold — the
                    #      classical identity-drop UX messaging.
                    check_failed = bool(sp_report.get("quality_check_failed"))
                    if check_failed:
                        result_dict["identity_unverified"] = True
                        warnings.append(
                            "Не удалось проверить сходство с оригиналом, "
                            "результат может заметно отличаться. "
                            "Попробуй загрузить другое фото или выбери другой стиль."
                        )
                    elif identity_match == 0.0 and not sp_report.get("identity_match"):
                        # VLM returned null (not a failure, just no comparison)
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

                    # Actionable warnings from LLM quality check — surfaced as
                    # soft notices (we deliver the photo anyway per policy).
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

                    # await self._record_ab_metrics(task_id, sp_report)
                except Exception:
                    logger.warning(
                        "Single-pass quality gates error for task=%s, skipping",
                        task_id,
                        exc_info=True,
                    )

            if raw and len(raw) > 100:
                raw = inject_exif_only(raw)

                gkey = f"generated/{user_id}/{task_id}.jpg"
                await self._storage.upload(gkey, raw)
                gen_url = await self._storage.get_url(gkey)
                result_dict["generated_image_url"] = gen_url
                result_dict["image_url"] = gen_url

                # v1.20: read the *real* routed backend label from
                # the StyleRouter ContextVar (falling back to the
                # requested generation_mode only when the router did
                # not run, e.g. legacy direct-provider setups). This
                # keeps the budget math honest even when the router
                # degrades identity_scene → scene_preserve mid-call.
                try:
                    from src.providers.image_gen.unified import (
                        get_routed_backend,
                    )

                    routed_label = first_pass_backend or get_routed_backend()
                except Exception:
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
                        generation_mode,
                        image_size=extra.get("image_size"),
                        routed_backend=routed_label,
                    )
                estimated_cost = per_call_cost * max(1, generation_attempts)

                # v1.20: IMAGE_GEN_BACKEND is now emitted exclusively
                # by :class:`StyleRouter` — see ``_record_backend``.
                # For legacy direct-provider deployments (no router)
                # we still publish the metric here so dashboards keep
                # working during a gradual cutover.
                if provider_name.lower() != "stylerouter":
                    try:
                        IMAGE_GEN_BACKEND.labels(
                            backend=backend_label,
                            style_mode=generation_mode or "unknown",
                        ).inc()
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
                    "generation_mode": generation_mode,
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
                # v1.17 — attribute Real-ESRGAN spend when it actually
                # ran. We can't observe the provider call from here (it's
                # fire-and-forget inside _maybe_real_esrgan_upscale), so
                # we infer activation from the same flag+threshold gate
                # and trust the fallback path to keep us safe.
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
                # v1.18 — CodeFormer post-process spend.
                codeformer_cost = 0.0
                if codeformer_applied:
                    # Rough per-image estimate: output ≈ 1 MP × 2× upscale
                    # = 4 MP billable × $0.0021/MP ≈ $0.0084.
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
                result_dict["cost_breakdown"] = {
                    "steps": cost_steps,
                    "total_usd": round(
                        estimated_cost + esrgan_cost + codeformer_cost,
                        4,
                    ),
                    "budget_usd": settings.pipeline_budget_max_usd,
                }
                logger.info(
                    "Image generated backend=%s gen_mode=%s key=%s "
                    "identity_match=%.2f cost=$%.4f",
                    backend_label,
                    generation_mode,
                    gkey,
                    identity_match,
                    estimated_cost + esrgan_cost + codeformer_cost,
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

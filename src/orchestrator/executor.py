"""ImageGenerationExecutor and DeltaScorer — extracted from AnalysisPipeline.

Handles single-pass image generation and post-generation delta scoring
as standalone collaborators. Multi-pass plan execution lives in
:mod:`src.orchestrator.advanced.execute_plan` and is reserved for future
premium / advanced scenarios (see ``docs/architecture/reserved.md``).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable, Awaitable

from src.config import settings
from src.metrics import (
    FAL_CALLS,
    IDENTITY_SCORE,
    REVE_CALLS,
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
# Reve's /v1/image/edit endpoint does not accept aspect_ratio.
_CV_DOCUMENT_ASPECT: dict[str, str] = {
    "photo_3x4": "3:4",        # 30×40 мм
    "passport_rf": "3:4",      # 35×45 мм ≈ 3:4
    "visa_eu": "3:4",          # 35×45 мм ≈ 3:4
    "visa_schengen": "3:4",    # 35×45 мм
    "visa_us": "1:1",          # 50×50 мм
    "photo_4x6": "2:3",        # 40×60 мм
    "driver_license": "3:4",
}


def _document_target_aspect(style: str) -> str | None:
    """Return the local-crop target AR for a CV document style, else None."""
    return _CV_DOCUMENT_ASPECT.get((style or "").strip())


# Face-area threshold above which we locally LANCZOS-upscale the
# generated image x2 (bigger faces benefit from extra detail; smaller
# faces just amplify upscaling artefacts).
_UPSCALE_FACE_THRESHOLD = 0.15


def _apply_local_postprocess(
    raw: bytes, mode: AnalysisMode, style: str, face_area_ratio: float,
) -> bytes:
    """Apply local PIL post-processing (AR crop for documents, LANCZOS x2 for large faces).

    This replaces the previous Reve ``postprocessing=[{upscale}]`` and
    ``aspect_ratio`` fields that the Reve REST API does not accept.
    Silent-safe: any PIL failure returns the original bytes.
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

    if face_area_ratio and face_area_ratio >= _UPSCALE_FACE_THRESHOLD:
        try:
            raw = upscale_lanczos(raw, factor=2)
        except Exception:
            logger.debug("upscale_lanczos failed, using original", exc_info=True)

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
        self, mode: AnalysisMode, style: str, image_bytes: bytes,
        result_dict: dict, user_id: str, task_id: str, trace: dict,
        gender: str = "male",
        input_quality: Any | None = None,
        variant_id: str = "",
    ) -> None:
        if mode not in (AnalysisMode.CV, AnalysisMode.EMOJI, AnalysisMode.DATING, AnalysisMode.SOCIAL):
            return
        if self._image_gen is None:
            return

        try:
            desc = str(result_dict.get("base_description", ""))
            input_hints = input_quality.to_prompt_hints() if input_quality is not None else None
            prompt = self._prompt_engine.build_image_prompt(
                mode, style=style, base_description=desc, gender=gender,
                input_hints=input_hints,
                variant_id=variant_id,
            )
            if variant_id:
                result_dict["variant_id"] = variant_id

            # Face area ratio drives two decisions:
            #   - whether to upscale x2 (bad idea for tiny faces, amplifies artefacts)
            #   - how strict HAIR protection should be
            face_area_ratio = (
                float(getattr(input_quality, "face_area_ratio", 0.0) or 0.0)
                if input_quality is not None else 0.0
            )

            # Provider ``extra`` payload. Provider-specific whitelists
            # apply (FalFlux2ImageGen accepts ``image_size`` + ``seed``,
            # Reve ignores everything but its own fields). The legacy
            # ``use_edit`` flag was a Reve-era no-op from the provider's
            # perspective and has been removed — document AR crops and
            # the x2 LANCZOS upscale still happen locally in
            # ``_apply_local_postprocess``.
            extra: dict = {}

            # Output resolution per style. FLUX.2 Pro Edit honours
            # ``image_size`` with a concrete ``{width, height}`` dict —
            # we pin each style to its target aspect (2 MP portrait for
            # headshot/full-body, 1 MP square for documents). Legacy
            # Reve / Kontext providers silently ignore the key.
            spec = STYLE_REGISTRY.get(mode.value, style)
            output_size = resolve_output_size(spec)
            if output_size:
                extra["image_size"] = output_size
                mp = (output_size["width"] * output_size["height"]) / 1_000_000
                logger.info(
                    "image_size resolved mode=%s style=%s size=%dx%d (~%.2f MP)",
                    mode.value, style or "default",
                    output_size["width"], output_size["height"], mp,
                )

            raw = None
            identity_match: float = 0.0

            will_upscale = bool(
                mode in (AnalysisMode.CV, AnalysisMode.DATING, AnalysisMode.SOCIAL)
                and face_area_ratio >= _UPSCALE_FACE_THRESHOLD
            )
            doc_ar = _document_target_aspect(style) if mode == AnalysisMode.CV else None
            logger.info(
                "Image generation (edit mode) mode=%s style=%s task=%s local_upscale=%s local_crop_ar=%s",
                mode.value, style or "default", task_id,
                "x2" if will_upscale else "no",
                doc_ar or "none",
            )
            with _trace_step(trace, "image_gen"):
                raw = await self._image_gen.generate(
                    prompt, reference_image=image_bytes,
                    params=extra or None,
                )

            if raw and len(raw) > 100:
                raw = _apply_local_postprocess(raw, mode, style, face_area_ratio)
            provider_name = type(self._image_gen).__name__
            # Generic provider-agnostic counter — preserved from the
            # Reve-first era for dashboards that key off it.
            REVE_CALLS.labels(
                mode=mode.value,
                step="single_pass",
                provider=provider_name,
            ).inc()
            # Dedicated FAL counter: the ``model`` label (kontext vs
            # flux-2-pro/edit) lets us watch the Kontext→Flux2 cutover
            # and any rollback cleanly in Grafana.
            if "falflux" in provider_name.lower():
                fal_model = (
                    settings.fal2_model if "falflux2" in provider_name.lower()
                    else settings.fal_model
                )
                FAL_CALLS.labels(
                    mode=mode.value, step="single_pass", model=fal_model,
                ).inc()

            if not raw or len(raw) <= 100:
                logger.warning("Image gen returned empty/tiny result (%s bytes)", len(raw) if raw else 0)
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
                        sp_passed, sp_results, sp_report = await gate_runner.run_global_gates(
                            sp_gates, image_bytes, raw,
                        )
                        sp_entry["gates"] = [
                            {"gate": gr.gate_name, "passed": gr.passed, "value": gr.value}
                            for gr in sp_results
                        ]
                    result_dict["quality_report"] = sp_report

                    identity_match = float(sp_report.get("identity_match") or 0.0)
                    if identity_match:
                        IDENTITY_SCORE.observe(identity_match / 10.0)

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
                            task_id, sp_report.get("gates_failed"),
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
                    logger.warning("Single-pass quality gates error for task=%s, skipping", task_id, exc_info=True)

            if raw and len(raw) > 100:
                raw = inject_exif_only(raw)

                gkey = f"generated/{user_id}/{task_id}.jpg"
                await self._storage.upload(gkey, raw)
                gen_url = await self._storage.get_url(gkey)
                result_dict["generated_image_url"] = gen_url
                result_dict["image_url"] = gen_url

                estimated_cost = estimate_image_gen_cost_usd(
                    provider_name, image_size=extra.get("image_size"),
                )

                result_dict["enhancement"] = {
                    "style": style or "default",
                    "mode": mode.value,
                    "provider": provider_name,
                    "identity_match": round(identity_match, 2),
                    "generation_attempts": 1,
                    "pipeline_type": "single_pass_edit",
                }
                result_dict["cost_breakdown"] = {
                    "steps": [{"step": "single_pass_edit", "model": provider_name,
                               "cost_usd": estimated_cost}],
                    "total_usd": round(estimated_cost, 4),
                    "budget_usd": settings.pipeline_budget_max_usd,
                }
                logger.info("Image generated (edit mode): %s (identity_match=%.2f)", gkey, identity_match)
            else:
                logger.warning("Image gen returned no usable result for task=%s", task_id)
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
        return round(max(_MIN_POSITIVE_DELTA + abs(variation) * 0.5, _MIN_POSITIVE_DELTA), 2)
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
        self, user_id: str, mode: AnalysisMode, style: str = "default",
    ) -> dict | None:
        if not self._redis:
            return None
        try:
            import json as _json
            raw = await self._redis.get(_SCORE_REDIS_KEY.format(user_id, mode.value, style))
            if raw:
                return _json.loads(raw)
        except Exception:
            logger.debug("Failed to load previous scores for user=%s mode=%s style=%s", user_id, mode.value, style)
        return None

    async def _save_scores(
        self, user_id: str, mode: AnalysisMode, scores: dict, style: str = "default",
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
            logger.debug("Failed to save scores for user=%s mode=%s style=%s", user_id, mode.value, style)

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
                post_result = await service.analyze(gen_bytes, profession=result_dict.get("profession", "не указана"))
            else:
                post_result = await service.analyze(gen_bytes)

            post_dict = post_result.model_dump() if hasattr(post_result, "model_dump") else post_result

            from src.utils.humanize import SCORE_FLOOR as _SCORE_FLOOR, PERCEPTION_FLOOR as _PERCEPTION_FLOOR

            def _floor_post(raw: float, floor: float = _SCORE_FLOOR) -> float:
                return max(float(raw), floor)

            style = result_dict.get("enhancement", {}).get("style", "default")
            prev = await self._load_previous_scores(user_id, mode, style)
            prev_scores = prev.get("scores", {}) if prev else {}
            prev_perception = prev.get("perception", {}) if prev else {}

            delta: dict[str, Any] = {}
            new_scores: dict[str, float] = {}

            if mode == AnalysisMode.DATING:
                pre = float(prev_scores.get("dating_score", 0)) or float(result_dict.get("dating_score", 0)) or float(result_dict.get("score", 0))
                raw_post = _floor_post(post_dict.get("dating_score", 0))
                entry = _build_delta_entry(pre, raw_post, f"{task_id}:dating_score")
                delta = {"dating_score": entry}
                new_scores["dating_score"] = entry["post"]
            elif mode == AnalysisMode.CV:
                for key in ("trust", "competence", "hireability"):
                    pre = float(prev_scores.get(key, 0)) or float(result_dict.get(key, 0))
                    raw_post = _floor_post(post_dict.get(key, 0))
                    entry = _build_delta_entry(pre, raw_post, f"{task_id}:{key}")
                    delta[key] = entry
                    new_scores[key] = entry["post"]
            elif mode == AnalysisMode.SOCIAL:
                pre = float(prev_scores.get("social_score", 0)) or float(result_dict.get("social_score", 0)) or float(result_dict.get("score", 0))
                raw_post = _floor_post(post_dict.get("social_score", 0))
                entry = _build_delta_entry(pre, raw_post, f"{task_id}:social_score")
                delta = {"social_score": entry}
                new_scores["social_score"] = entry["post"]

            result_dict["delta"] = delta

            if mode == AnalysisMode.CV:
                pre_vals = [delta[k]["pre"] for k in ("trust", "competence", "hireability") if k in delta]
                result_dict["score_before"] = round(sum(pre_vals) / len(pre_vals), 2) if pre_vals else None
                post_vals = [delta[k]["post"] for k in ("trust", "competence", "hireability") if k in delta]
                result_dict["score_after"] = round(sum(post_vals) / len(post_vals), 2) if post_vals else None
            else:
                first_key = next(iter(delta), None)
                result_dict["score_before"] = delta[first_key]["pre"] if first_key else None
                result_dict["score_after"] = delta[first_key]["post"] if first_key else None

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
                pre_val = float(prev_perception.get(key, 0)) or float(pre_perception.get(key, 5.0))
                raw_post_val = _floor_post(float(post_perception.get(key, 5.0)), floor=_PERCEPTION_FLOOR)
                entry = _build_delta_entry(pre_val, raw_post_val, f"{task_id}:p:{key}")
                perception_delta[key] = entry
                new_perception[key] = entry["post"]

            result_dict["perception_delta"] = perception_delta

            await self._save_scores(user_id, mode, {
                "scores": new_scores,
                "perception": new_perception,
            }, style)

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
            logger.info("Delta computed for task=%s: %s perception: %s", task_id, delta, perception_delta)
        except Exception:
            logger.exception("Post-gen re-scoring failed for task=%s", task_id)
            result_dict["delta_error"] = "rescoring_failed"

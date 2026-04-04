from __future__ import annotations

import logging

from src.models.enums import AnalysisMode
from src.models.schemas import RatingResult
from src.orchestrator.router import ModeRouter
from src.orchestrator.merger import ResultMerger
from src.providers.base import ImageGenProvider, LLMProvider, StorageProvider
from src.prompts.engine import PromptEngine
from src.services.share import ShareCardGenerator
from src.utils.image import validate_and_normalize, has_face_heuristic
from src.utils.security import check_nsfw

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    def __init__(
        self,
        llm: LLMProvider,
        storage: StorageProvider,
        image_gen: ImageGenProvider | None = None,
    ):
        self._llm = llm
        self._prompt_engine = PromptEngine()
        self._router = ModeRouter(llm, self._prompt_engine)
        self._share_gen = ShareCardGenerator(storage)
        self._merger = ResultMerger()
        self._storage = storage
        self._image_gen = image_gen

    async def execute(
        self,
        mode: AnalysisMode,
        image_bytes: bytes,
        user_id: str,
        task_id: str,
        context: dict | None = None,
    ) -> dict:
        # --- Preprocessing ---
        image_bytes, meta = validate_and_normalize(image_bytes)

        if not has_face_heuristic(image_bytes):
            raise ValueError("На фото не обнаружено лицо. Пожалуйста, загрузите портретное фото.")

        is_safe, reason = await check_nsfw(self._llm, image_bytes)
        if not is_safe:
            raise ValueError(f"Фото не прошло модерацию: {reason}")

        # --- Analysis ---
        service = self._router.get_service(mode)

        if mode == AnalysisMode.CV:
            profession = (context or {}).get("profession", "не указана")
            result = await service.analyze(image_bytes, profession=profession)
        else:
            result = await service.analyze(image_bytes)

        if isinstance(result, RatingResult):
            result_dict = result.model_dump()
        else:
            result_dict = result.model_dump() if hasattr(result, "model_dump") else result

        # --- Image generation (CV / dating / emoji) ---
        if (
            mode in (AnalysisMode.CV, AnalysisMode.EMOJI, AnalysisMode.DATING)
            and self._image_gen is not None
        ):
            try:
                if mode == AnalysisMode.CV:
                    prompt = (
                        "Professional corporate headshot, soft studio lighting, neutral gray background, "
                        "sharp focus on face, business attire, photorealistic. Preserve the person's identity."
                    )
                    synopsis = str(result_dict.get("analysis", ""))[:400]
                    if synopsis:
                        prompt = f"{prompt} Notes: {synopsis}"
                    extra: dict = {}
                elif mode == AnalysisMode.DATING:
                    prompt = (
                        "Improved dating profile photo, warm natural lighting, "
                        "friendly confident expression, soft bokeh background, "
                        "photorealistic. Preserve the person's identity."
                    )
                    tips = str(result_dict.get("first_impression", ""))[:400]
                    if tips:
                        prompt = f"{prompt} Context: {tips}"
                    extra = {}
                else:
                    prompt = (
                        "Single cute sticker avatar portrait, bold outlines, flat colors, "
                        "same person as reference, friendly expression, square composition."
                    )
                    desc = str(result_dict.get("base_description", ""))[:400]
                    if desc:
                        prompt = f"{prompt} Character: {desc}"
                    extra = {}
                logger.info("Starting image generation for mode=%s task=%s", mode.value, task_id)
                raw = await self._image_gen.generate(
                    prompt,
                    reference_image=image_bytes,
                    params=extra or None,
                )
                if raw and len(raw) > 100:
                    gkey = f"generated/{user_id}/{task_id}.jpg"
                    await self._storage.upload(gkey, raw)
                    gen_url = await self._storage.get_url(gkey)
                    result_dict["generated_image_url"] = gen_url
                    result_dict["image_url"] = gen_url
                    logger.info("Image generated and stored: %s", gkey)
                else:
                    logger.warning("Image gen returned empty/tiny result (%s bytes)", len(raw) if raw else 0)
                    result_dict["image_gen_error"] = "empty_result"
            except Exception:
                logger.exception("Image generation failed for mode %s", mode.value)
                result_dict["image_gen_error"] = "generation_failed"

        # --- Share card (rating only) ---
        share_card_url = None
        if mode == AnalysisMode.RATING and isinstance(result, RatingResult):
            try:
                share_card_url = await self._share_gen.generate_rating_card(
                    result=result,
                    photo_bytes=image_bytes,
                    user_id=user_id,
                    task_id=task_id,
                )
            except Exception:
                logger.exception("Failed to generate share card")

        return self._merger.merge(result_dict, share_card_url, user_id)

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
from src.utils.security import check_nsfw, NSFW_INLINE_PREFIX, extract_nsfw_from_analysis

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
        image_bytes = await self._preprocess(image_bytes)

        result, result_dict = await self._analyze(mode, image_bytes, context)

        style = (context or {}).get("style", "")
        skip_gen = (context or {}).get("skip_image_gen", False)
        if skip_gen:
            result_dict["upgrade_prompt"] = True
        else:
            await self._generate_image(mode, style, image_bytes, result_dict, user_id, task_id)

        return await self._finalize(mode, result, result_dict, image_bytes, user_id, task_id)

    async def _preprocess(self, image_bytes: bytes) -> bytes:
        image_bytes, _meta = validate_and_normalize(image_bytes)

        if not has_face_heuristic(image_bytes):
            raise ValueError("На фото не обнаружено лицо. Пожалуйста, загрузите портретное фото.")

        return image_bytes

    async def _analyze(self, mode: AnalysisMode, image_bytes: bytes, context: dict | None) -> tuple:
        service = self._router.get_service(mode)

        if mode == AnalysisMode.CV:
            profession = (context or {}).get("profession", "не указана")
            result = await service.analyze(image_bytes, profession=profession)
        else:
            result = await service.analyze(image_bytes)

        raw_dict = result if isinstance(result, dict) else (result.model_dump() if hasattr(result, "model_dump") else result)

        is_safe, reason = extract_nsfw_from_analysis(raw_dict)
        if not is_safe:
            raise ValueError(f"Фото не прошло модерацию: {reason}")

        if isinstance(result, RatingResult):
            result_dict = result.model_dump()
        else:
            result_dict = raw_dict

        return result, result_dict

    async def _generate_image(
        self, mode: AnalysisMode, style: str, image_bytes: bytes,
        result_dict: dict, user_id: str, task_id: str,
    ) -> None:
        if mode not in (AnalysisMode.CV, AnalysisMode.EMOJI, AnalysisMode.DATING):
            return
        if self._image_gen is None:
            return

        try:
            desc = str(result_dict.get("base_description", ""))
            prompt = self._prompt_engine.build_image_prompt(mode, style=style, base_description=desc)

            extra: dict = {}
            if mode in (AnalysisMode.CV, AnalysisMode.DATING):
                extra = {"aspect_ratio": "auto", "test_time_scaling": 3}

            logger.info("Starting image generation for mode=%s style=%s task=%s", mode.value, style or "default", task_id)
            raw = await self._image_gen.generate(prompt, reference_image=image_bytes, params=extra or None)

            if raw and len(raw) > 100:
                gkey = f"generated/{user_id}/{task_id}.jpg"
                await self._storage.upload(gkey, raw)
                gen_url = await self._storage.get_url(gkey)
                result_dict["generated_image_url"] = gen_url
                result_dict["image_url"] = gen_url
                result_dict["enhancement"] = {
                    "style": style or "default",
                    "mode": mode.value,
                    "provider": type(self._image_gen).__name__,
                    "corrections_applied": [
                        "defect_correction",
                        "skin_enhancement",
                        "under_eye_cleanup",
                        "blemish_removal",
                        "tone_evening",
                    ],
                    "identity_preservation": "strict",
                    "photorealism_check": "enforced",
                }
                logger.info("Image generated and stored: %s", gkey)
            else:
                logger.warning("Image gen returned empty/tiny result (%s bytes)", len(raw) if raw else 0)
                result_dict["image_gen_error"] = "empty_result"
        except Exception:
            logger.exception("Image generation failed for mode %s", mode.value)
            result_dict["image_gen_error"] = "generation_failed"

    async def _finalize(
        self, mode: AnalysisMode, result, result_dict: dict,
        image_bytes: bytes, user_id: str, task_id: str,
    ) -> dict:
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

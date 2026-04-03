from __future__ import annotations

import logging

from src.models.enums import AnalysisMode
from src.models.schemas import RatingResult
from src.orchestrator.router import ModeRouter
from src.orchestrator.merger import ResultMerger
from src.providers.base import LLMProvider, StorageProvider
from src.prompts.engine import PromptEngine
from src.services.share import ShareCardGenerator
from src.utils.image import validate_and_normalize, has_face_heuristic
from src.utils.security import check_nsfw

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    def __init__(self, llm: LLMProvider, storage: StorageProvider):
        self._llm = llm
        self._prompt_engine = PromptEngine()
        self._router = ModeRouter(llm, self._prompt_engine)
        self._share_gen = ShareCardGenerator(storage)
        self._merger = ResultMerger()
        self._storage = storage

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

        # --- Post-processing ---
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

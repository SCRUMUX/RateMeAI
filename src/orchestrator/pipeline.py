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
        style = (context or {}).get("style", "")
        if (
            mode in (AnalysisMode.CV, AnalysisMode.EMOJI, AnalysisMode.DATING)
            and self._image_gen is not None
        ):
            try:
                if mode == AnalysisMode.CV:
                    prompt = self._build_cv_prompt(style)
                    extra: dict = {"aspect_ratio": "auto", "test_time_scaling": 3}
                elif mode == AnalysisMode.DATING:
                    prompt = self._build_dating_prompt(style)
                    extra = {"aspect_ratio": "auto", "test_time_scaling": 3}
                else:
                    prompt = (
                        "Cartoon sticker avatar of the person from <ref>0</ref>. "
                        "Keep recognizable facial proportions, face shape, hairstyle and hair color. "
                        "Bold outlines, flat vibrant colors, friendly expression, square composition."
                    )
                    desc = str(result_dict.get("base_description", ""))[:400]
                    if desc:
                        prompt = f"{prompt} Character: {desc}"
                    extra = {}
                logger.info("Starting image generation for mode=%s style=%s task=%s", mode.value, style or "default", task_id)
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
                    result_dict["enhancement"] = {
                        "style": style or "default",
                        "mode": mode.value,
                        "provider": "reve_remix",
                    }
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

    # ── Prompt builders ──

    _FACE_ANCHOR = (
        "STRICT IDENTITY RULE: the person's face shape, nose, eyes, eyebrows, "
        "lips, jawline, ears, and bone structure MUST remain pixel-identical to "
        "the reference photo. Do NOT reshape, resize, or reposition any facial "
        "feature. The person must be instantly recognizable."
    )

    _SKIN_ENHANCE = (
        "Enhance skin: remove blemishes, acne, and dark spots; even out skin "
        "tone; reduce visible pores and under-eye circles; add a healthy natural "
        "glow. Smooth wrinkles gently while keeping skin texture realistic — "
        "no plastic or airbrushed look."
    )

    _DATING_STYLES: dict[str, str] = {
        "warm_outdoor": (
            "Background: warm golden-hour outdoor scene with soft bokeh "
            "(park, city sunset, or seaside). "
            "Clothing: stylish casual outfit that flatters the person."
        ),
        "studio_elegant": (
            "Background: professional studio with soft gradient lighting. "
            "Clothing: elegant evening outfit (dark tones, well-fitted)."
        ),
        "cafe": (
            "Background: cozy upscale café or wine bar with warm ambient light. "
            "Clothing: smart-casual date-night outfit."
        ),
    }

    _CV_STYLES: dict[str, str] = {
        "corporate": (
            "Background: clean modern corporate office, neutral grey/white wall. "
            "Clothing: formal business suit with tie or blazer, crisp white shirt."
        ),
        "creative": (
            "Background: modern creative workspace with subtle design elements. "
            "Clothing: smart-casual — neat blazer over a crew-neck, no tie."
        ),
        "neutral": (
            "Background: solid light-grey professional studio backdrop. "
            "Clothing: classic professional attire appropriate for the industry."
        ),
    }

    def _build_dating_prompt(self, style: str = "") -> str:
        style_block = self._DATING_STYLES.get(style, self._DATING_STYLES["warm_outdoor"])
        return (
            "Transform this portrait into an attractive dating-profile photo. "
            f"{self._SKIN_ENHANCE} "
            "Add a warm, approachable, light smile with natural lip curvature. "
            "Brighten the whites of the eyes and subtly enhance iris color. "
            "Improve lighting to soft, flattering, directional golden-hour quality. "
            f"{style_block} "
            f"{self._FACE_ANCHOR} "
            "The final image must be indistinguishable from a real high-end photograph."
        )

    def _build_cv_prompt(self, style: str = "") -> str:
        style_block = self._CV_STYLES.get(style, self._CV_STYLES["corporate"])
        return (
            "Transform this portrait into a professional corporate headshot. "
            f"{self._SKIN_ENHANCE} "
            "Set expression to confident and approachable — subtle professional smile. "
            "Improve lighting to even, soft studio quality with catchlights in eyes. "
            f"{style_block} "
            f"{self._FACE_ANCHOR} "
            "The final image must look like a real executive portrait by a professional photographer."
        )

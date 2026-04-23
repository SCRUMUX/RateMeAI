"""Unified image generation provider.

Delegates to the appropriate backend based on the requested model and parameters.
Model A (High Quality): GPT-2
Model B (Fast): Nano Banana
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from src.providers.base import ImageGenProvider

logger = logging.getLogger(__name__)

routed_backend_var: ContextVar[str] = ContextVar("routed_backend_var", default="")

def get_routed_backend() -> str:
    """Return the backend label that actually ran the last generation."""
    return routed_backend_var.get()


class UnifiedImageGenProvider(ImageGenProvider):
    """Unified provider that routes to specific models based on the request."""

    def __init__(
        self,
        *,
        model_a: ImageGenProvider,
        model_b: ImageGenProvider,
        pulid: ImageGenProvider | None = None,
        seedream: ImageGenProvider | None = None,
        rave: ImageGenProvider | None = None,
    ):
        self._model_a = model_a
        self._model_b = model_b
        self._pulid = pulid
        self._seedream = seedream
        self._rave = rave

    async def close(self) -> None:
        for p in (
            self._model_a,
            self._model_b,
            self._pulid,
            self._seedream,
            self._rave,
        ):
            if p is not None:
                try:
                    await p.close()
                except Exception:
                    pass

    def _pick_backend(self, params: dict) -> tuple[ImageGenProvider, str]:
        """Pick the backend based on params."""
        # Check if a specific model is requested (e.g. via A/B test or explicit choice)
        requested_model = str(params.get("image_model", "")).strip().lower()

        if requested_model == "nano_banana_2":
            return self._model_b, "nano_banana_2"
        if requested_model == "gpt_image_2":
            return self._model_a, "gpt_image_2"

        # Check generation mode for specific handlers
        generation_mode = str(params.get("generation_mode", "")).strip().lower()
        if generation_mode == "identity_scene" and self._pulid is not None:
            return self._pulid, "pulid"
        if generation_mode == "scene_preserve" and self._seedream is not None:
            return self._seedream, "seedream"
        if generation_mode == "rave" and self._rave is not None:
            return self._rave, "rave"

        # Default to Model A (High Quality)
        return self._model_a, "gpt_image_2"

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        params = dict(params or {})

        provider, backend_label = self._pick_backend(params)
        routed_backend_var.set(backend_label)

        try:
            from src.metrics import IMAGE_GEN_BACKEND

            IMAGE_GEN_BACKEND.labels(
                backend=backend_label,
                style_mode=str(params.get("generation_mode", "unknown")),
            ).inc()
        except Exception:
            pass

        # If fallback is needed, we can catch exceptions and try Model B
        try:
            return await provider.generate(
                prompt=prompt,
                reference_image=reference_image,
                params=params,
            )
        except Exception as exc:
            if provider is self._model_a:
                logger.warning("Model A failed (%s), falling back to Model B", exc)
                routed_backend_var.set("nano_banana_2")
                try:
                    from src.metrics import STYLE_MODE_OVERRIDE

                    STYLE_MODE_OVERRIDE.labels(
                        from_mode="gpt_image_2",
                        to_mode="nano_banana_2",
                        reason="fallback_on_error",
                    ).inc()
                except Exception:
                    pass
                return await self._model_b.generate(
                    prompt=prompt,
                    reference_image=reference_image,
                    params=params,
                )
            raise

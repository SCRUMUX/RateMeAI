"""Unified image generation provider (v1.64 — FAL edit-only).

Routes between two FAL-hosted edit-mode models picked at request time
via ``params["image_model"]``:

* ``model_a`` — GPT Image 2 Edit (high quality, default).
* ``model_b`` — Nano Banana 2 Edit (faster A/B alternative).

Symmetric cross-model fallback: when the requested model fails and
``params["allow_cross_model_fallback"]`` is True (default), we retry
once on the other model and log a warning.

History
-------

Earlier revisions of this provider also dispatched to PuLID (identity
scene generation from a face crop) and Seedream (scene preservation)
based on the style's ``generation_mode``. In production the
``ab_test_enabled=True`` web path always set ``image_model`` upstream,
so the ``generation_mode`` fork was never reached and the two
specialised providers became dead code. v1.64 removed them entirely
along with their factory wiring, settings, schema fields and tests.
"""

from __future__ import annotations

import logging

from src.providers.base import ImageGenProvider

logger = logging.getLogger(__name__)


class UnifiedImageGenProvider(ImageGenProvider):
    """Routes between GPT Image 2 Edit and Nano Banana 2 Edit."""

    def __init__(
        self,
        *,
        model_a: ImageGenProvider,
        model_b: ImageGenProvider,
    ):
        self._model_a = model_a
        self._model_b = model_b

    async def close(self) -> None:
        for p in (self._model_a, self._model_b):
            if p is not None:
                try:
                    await p.close()
                except Exception:
                    pass

    def _pick_backend(self, params: dict) -> tuple[ImageGenProvider, str]:
        """Resolve the backend from ``params["image_model"]``.

        Defaults to Model A (GPT Image 2) when the requested model is
        empty or unrecognised — the same fallback the legacy
        StyleRouter used.
        """
        requested_model = str(params.get("image_model", "")).strip().lower()
        if requested_model == "nano_banana_2":
            return self._model_b, "nano_banana_2"
        return self._model_a, "gpt_image_2"

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        params = dict(params or {})

        provider, backend_label = self._pick_backend(params)

        try:
            from src.metrics import IMAGE_GEN_BACKEND

            IMAGE_GEN_BACKEND.labels(backend=backend_label).inc()
        except Exception:
            pass

        # v1.24.2: symmetric fallback. When the chosen model fails we
        # try the other one. Opt-out via
        # ``params["allow_cross_model_fallback"]=False``.
        allow_fb = bool(params.get("allow_cross_model_fallback", True))

        try:
            return await provider.generate(
                prompt=prompt,
                reference_image=reference_image,
                params=params,
            )
        except Exception as exc:
            if not allow_fb:
                raise
            if provider is self._model_a:
                other, other_label = self._model_b, "nano_banana_2"
            else:
                other, other_label = self._model_a, "gpt_image_2"

            logger.warning(
                "Model %s failed (%s), falling back to %s",
                backend_label,
                exc,
                other_label,
            )
            return await other.generate(
                prompt=prompt,
                reference_image=reference_image,
                params=params,
            )

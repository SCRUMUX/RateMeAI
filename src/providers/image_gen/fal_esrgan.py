"""FAL.ai Real-ESRGAN upscaler client (v1.17).

Thin client for ``fal-ai/real-esrgan``, used as the *final* upscale
step instead of PIL LANCZOS when ``settings.real_esrgan_enabled`` is
on and the generated photo has a large-enough face to benefit from a
diffusion-aware upscale.

Wire protocol lives in
:class:`src.providers.image_gen._fal_queue_base.FalQueueClient`. The
body shape is simpler than the edit providers (one image URL + scale
factor), so we only override :meth:`_build_body` and wrap
``_run_queue_sync`` in :meth:`upscale`.

Pricing
-------
Real-ESRGAN on FAL bills ~$0.001–$0.002 per image. We estimate
$0.002 for budget math (see ``settings.model_cost_fal_real_esrgan``).
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from PIL import Image

from src.providers.image_gen._fal_queue_base import FalQueueClient
from src.services.ai_transfer_guard import assert_external_transfer_allowed

logger = logging.getLogger(__name__)

# Real-ESRGAN on FAL accepts ``model`` among a few named upscaler
# weights. ``RealESRGAN_x4plus`` is the default on the docs page; we
# expose it here for completeness even though current callers always
# use the default.
_SUPPORTED_SCALES = frozenset({2, 3, 4})


class FalRealEsrganUpscaler(FalQueueClient):
    """FAL.ai Real-ESRGAN upscaler client."""

    # Real-ESRGAN responses historically use ``image: {url}``; newer
    # schemas sometimes switch to ``images: [{url}]``. Accept both,
    # preferring the older key.
    _image_response_keys = ("image", "images")

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/real-esrgan",
        api_host: str = "https://queue.fal.run",
        max_retries: int = 2,
        request_timeout: float = 90.0,
        poll_interval: float = 1.0,
    ):
        super().__init__(
            api_key,
            model=model,
            api_host=api_host,
            max_retries=max_retries,
            request_timeout=request_timeout,
            poll_interval=poll_interval,
            label="Real-ESRGAN",
        )

    # ------------------------------------------------------------------
    # Body builder
    # ------------------------------------------------------------------

    def _build_body(
        self,
        prompt: str | None = None,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Body for fal-ai/real-esrgan.

        The caller passes ``scale`` via ``params`` — :meth:`upscale`
        handles the wrapping.
        """
        if not reference_image:
            raise ValueError("FalRealEsrganUpscaler requires image bytes")
        extras = params or {}
        try:
            scale = int(extras.get("scale", 2))
        except (TypeError, ValueError):
            scale = 2
        scale_clamped = scale if scale in _SUPPORTED_SCALES else 2
        return {
            "image_url": self._data_url(reference_image),
            "scale": scale_clamped,
            "sync_mode": True,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _upscale_sync(self, image_bytes: bytes, scale: int) -> bytes:
        body = self._build_body(
            prompt=None,
            reference_image=image_bytes,
            params={"scale": scale},
        )
        logger.info(
            "FAL Real-ESRGAN request model=%s scale=x%d input_bytes=%d",
            self._model,
            body.get("scale"),
            len(image_bytes or b""),
        )
        return self._run_queue_sync(body)

    async def upscale(self, image_bytes: bytes, factor: int = 2) -> bytes:
        """Run Real-ESRGAN upscaling on ``image_bytes``.

        Returns the upscaled JPEG/PNG bytes. Raises ``RuntimeError`` on
        any terminal FAL error; the caller is expected to fall back to
        :func:`src.services.postprocess.upscale_lanczos` for continuity.
        """
        assert_external_transfer_allowed("fal_real_esrgan")
        raw = await asyncio.to_thread(
            self._upscale_sync,
            image_bytes,
            int(factor),
        )
        if raw and len(raw) > 100:
            return raw
        try:
            img = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92)
            return buf.getvalue()
        except Exception as exc:
            raise RuntimeError(
                f"FAL Real-ESRGAN: empty/invalid image ({exc})",
            ) from exc


__all__ = ["FalRealEsrganUpscaler"]

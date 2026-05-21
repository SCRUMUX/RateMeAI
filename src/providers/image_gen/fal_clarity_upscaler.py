"""FAL.ai Clarity Upscaler client (v1.72).

Premium-tier refiner that runs as the **post-process refinement
step** for paid generations. Unlike Real-ESRGAN
(``fal-ai/real-esrgan``, ~$0.002/img — used as a quality-of-life
upscaler when ``settings.real_esrgan_enabled`` is on), Clarity
Upscaler is a stable-diffusion-based super-resolution model that
adds visible pixel-level detail back into the image while keeping
the input geometry intact.

We use Clarity at ``upscale_factor=1`` (no resolution change) with
low ``creativity`` and high ``resemblance`` so the model acts as a
detail-enhancer, NOT a re-generator — facial features stay locked
to the input image (which is critical for our identity-preservation
contract) while skin pores, fabric textures, and background micro-
detail get a measurable polish.

Wire contract
-------------
::

    POST https://queue.fal.run/fal-ai/clarity-upscaler
    {
        "image_url":      "data:image/jpeg;base64,...",
        "upscale_factor": 1,
        "creativity":     0.2,
        "resemblance":    0.8,
        "dynamic":        5,
        "sync_mode":      true
    }

* ``creativity`` (0 – 1) — how much the model is allowed to invent
  new content. 0.2 keeps it conservative; >0.4 starts re-painting
  the face.
* ``resemblance`` (0 – 4) — how strongly the result is pinned to the
  input. 0.8 is a moderate-strong lock that allows the model to
  sharpen textures without dragging the face geometry around.
* ``dynamic`` (1 – 50) — HDR-like dynamic range boost.

The endpoint returns a single image; we accept the canonical
``image: {url}`` key first and fall back to ``images: [{url}]``.

Pricing
-------
Empirical: ~$0.04 per request at upscale_factor=1 (token-based,
see fal.ai/models/fal-ai/clarity-upscaler). Total premium cost
in v1.72 = gpt_image_2 medium ($0.06) + Clarity ($0.04) ≈ $0.10,
sitting comfortably under the $0.12 product cap.

Failure handling
----------------
Like CodeFormer, Clarity is wired as a **non-fatal** post-process:
any transport / API / parse error returns the input image
unchanged so the user always gets the standard-tier render even
if the refinement step fails. The orchestrator additionally
refunds 1 of the 2 reserved credits when the refiner fails on a
premium request (see ``src/api/deps.py``).
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
from typing import Any

from PIL import Image

from src.providers.image_gen._fal_queue_base import FalQueueClient
from src.services.ai_transfer_guard import assert_external_transfer_allowed

logger = logging.getLogger(__name__)


# Tuned for identity preservation. The defaults on fal.ai's playground
# (creativity=0.35, resemblance=0.6) routinely re-painted faces on
# our portrait references; values below are the empirical floor that
# still produced a visible texture polish on 5 control scenes from
# the v1.72 audit (dating/dubai_burj_khalifa, cv/corporate_executive,
# social/influencer_minimal, dating/rome_colosseum, cv/video_call).
_DEFAULT_CREATIVITY = 0.2
_DEFAULT_RESEMBLANCE = 0.8
_DEFAULT_DYNAMIC = 5


class FalClarityUpscaler(FalQueueClient):
    """FAL.ai Clarity Upscaler client (premium refiner)."""

    # The endpoint historically returns ``image: {url}``; some FAL
    # models switched to ``images: [{url}]`` in 2026. Accept both.
    _image_response_keys = ("image", "images")

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/clarity-upscaler",
        api_host: str = "https://queue.fal.run",
        max_retries: int = 2,
        request_timeout: float = 180.0,
        poll_interval: float = 2.0,
    ):
        super().__init__(
            api_key,
            model=model,
            api_host=api_host,
            max_retries=max_retries,
            request_timeout=request_timeout,
            poll_interval=poll_interval,
            label="ClarityUpscaler",
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
        """Body for fal-ai/clarity-upscaler.

        :param reference_image: bytes of the image to refine (output
            of the main render step).
        :param params: optional overrides for ``creativity`` /
            ``resemblance`` / ``dynamic`` / ``upscale_factor``.
        """
        if not reference_image:
            raise ValueError("FalClarityUpscaler requires image bytes")
        extras = params or {}
        try:
            upscale_factor = int(extras.get("upscale_factor", 1))
        except (TypeError, ValueError):
            upscale_factor = 1
        upscale_factor = max(1, min(4, upscale_factor))

        def _clamp_float(value: Any, default: float, lo: float, hi: float) -> float:
            try:
                f = float(value)
            except (TypeError, ValueError):
                return default
            if math.isnan(f) or math.isinf(f):
                return default
            if f < lo:
                return lo
            if f > hi:
                return hi
            return f

        creativity = _clamp_float(
            extras.get("creativity"), _DEFAULT_CREATIVITY, 0.0, 1.0,
        )
        resemblance = _clamp_float(
            extras.get("resemblance"), _DEFAULT_RESEMBLANCE, 0.0, 4.0,
        )
        dynamic = _clamp_float(
            extras.get("dynamic"), _DEFAULT_DYNAMIC, 1.0, 50.0,
        )

        return {
            "image_url": self._data_url(reference_image),
            "upscale_factor": upscale_factor,
            "creativity": creativity,
            "resemblance": resemblance,
            "dynamic": dynamic,
            "sync_mode": True,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _refine_sync(
        self,
        image_bytes: bytes,
        *,
        creativity: float | None,
        resemblance: float | None,
        dynamic: float | None,
        upscale_factor: int,
    ) -> bytes:
        body = self._build_body(
            prompt=None,
            reference_image=image_bytes,
            params={
                "creativity": creativity,
                "resemblance": resemblance,
                "dynamic": dynamic,
                "upscale_factor": upscale_factor,
            },
        )
        logger.info(
            "FAL Clarity refine request model=%s creativity=%s "
            "resemblance=%s dynamic=%s upscale=x%d input_bytes=%d",
            self._model,
            body.get("creativity"),
            body.get("resemblance"),
            body.get("dynamic"),
            body.get("upscale_factor"),
            len(image_bytes or b""),
        )
        return self._run_queue_sync(body)

    async def refine(
        self,
        image_bytes: bytes,
        *,
        creativity: float | None = None,
        resemblance: float | None = None,
        dynamic: float | None = None,
        upscale_factor: int = 1,
    ) -> bytes:
        """Run Clarity refinement on ``image_bytes``.

        Returns the refined JPEG/PNG bytes. On any terminal FAL
        error the caller (orchestrator) is expected to catch the
        exception and fall back to the un-refined input — Clarity
        is a quality-of-life polish, never load-bearing.
        """
        assert_external_transfer_allowed("fal_clarity_upscaler")
        raw = await asyncio.to_thread(
            self._refine_sync,
            image_bytes,
            creativity=creativity,
            resemblance=resemblance,
            dynamic=dynamic,
            upscale_factor=int(upscale_factor),
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
                f"FAL Clarity Upscaler: empty/invalid image ({exc})",
            ) from exc


__all__ = ["FalClarityUpscaler"]

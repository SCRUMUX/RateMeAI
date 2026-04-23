"""FAL.ai Nano Banana 2 Edit image-gen provider.

Additive v1.21 A/B-test provider — wired next to (not instead of) the
existing hybrid StyleRouter + PuLID / Seedream / FLUX.2 stack. Selected
per-request when the web UI sends ``image_model="nano_banana_2"``;
otherwise the default hybrid pipeline runs untouched.

Model: ``fal-ai/nano-banana-2/edit`` (Google Gemini 3.1 Flash Image).
Shares the FAL queue protocol (submit / poll / fetch / decode) with all
other providers, so it inherits from
:class:`src.providers.image_gen._fal_queue_base.FalQueueClient` and only
implements the model-specific request body.

Quality -> resolution enum mapping (per fal schema, v1.22):

* ``low``    — ``1K`` (~$0.08 / image, ≈ 1024px long edge)
* ``medium`` — ``2K`` (~$0.12 / image, ≈ 2048px long edge)
* ``high``   — ``4K`` (~$0.16 / image, ≈ 4096px long edge)

v1.22 bumped the floor from 0.5K to 1K because 512px portraits were
too blurry for production — the cheapest UI-visible output is now a
full ~1 MP image, matching the GPT Image 2 ``low`` tier.

The Nano Banana 2 Edit schema does **not** accept an ``{width, height}``
``image_size``; it exposes ``resolution`` (enum ``0.5K | 1K | 2K | 4K``)
and ``aspect_ratio`` (enum with ``auto``) instead — we rely on
``aspect_ratio="auto"`` so the model infers aspect from the reference
portrait and we never 422 on framing mismatches.

The ``num_images=1`` knob is fixed; we deliberately do not expose batch
generation so Prometheus cost accounting stays 1-call = 1-image.
"""
from __future__ import annotations

import asyncio
import io
import logging
import random
from typing import Any

from PIL import Image

from src.providers.base import ImageGenProvider
from src.providers.image_gen._fal_queue_base import FalQueueClient
from src.services.ai_transfer_guard import assert_external_transfer_allowed

logger = logging.getLogger(__name__)

_SEED_MAX = 2**31 - 1
_SEED_RNG = random.SystemRandom()


QualityTier = str  # "low" | "medium" | "high"


_QUALITY_TO_RESOLUTION: dict[str, str] = {
    "low": "1K",
    "medium": "2K",
    "high": "4K",
}

_VALID_ASPECT_RATIOS = frozenset({
    "auto", "21:9", "16:9", "3:2", "4:3", "5:4", "1:1",
    "4:5", "3:4", "2:3", "9:16", "4:1", "1:4", "8:1", "1:8",
})


def _resolution_for_quality(quality: str | None) -> str:
    q = (quality or "medium").strip().lower()
    return _QUALITY_TO_RESOLUTION.get(q, _QUALITY_TO_RESOLUTION["medium"])


class FalNanoBanana2Edit(FalQueueClient, ImageGenProvider):
    """FAL.ai Nano Banana 2 Edit client (reference-based image editing)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/nano-banana-2/edit",
        api_host: str = "https://queue.fal.run",
        output_format: str = "jpeg",
        default_quality: str = "medium",
        max_retries: int = 2,
        request_timeout: float = 180.0,
        poll_interval: float = 1.5,
    ):
        super().__init__(
            api_key,
            model=model,
            api_host=api_host,
            max_retries=max_retries,
            request_timeout=request_timeout,
            poll_interval=poll_interval,
            label="NanoBanana2",
        )
        fmt = (output_format or "jpeg").lower()
        self._output_format = fmt if fmt in ("jpeg", "png") else "jpeg"
        self._default_quality = (
            default_quality
            if default_quality in _QUALITY_TO_RESOLUTION
            else "medium"
        )

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------

    def _build_body(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> dict[str, Any]:
        if not reference_image:
            raise ValueError(
                "FAL Nano Banana 2 Edit requires reference_image",
            )

        extras = params or {}
        quality = str(extras.get("quality") or self._default_quality).lower()
        if quality not in _QUALITY_TO_RESOLUTION:
            quality = self._default_quality
        resolution = _resolution_for_quality(quality)

        aspect_ratio = str(extras.get("aspect_ratio") or "auto")
        if aspect_ratio not in _VALID_ASPECT_RATIOS:
            aspect_ratio = "auto"

        body: dict[str, Any] = {
            "prompt": prompt,
            "image_urls": [self._data_url(reference_image)],
            "num_images": 1,
            "output_format": self._output_format,
            "sync_mode": True,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
        }

        seed = extras.get("seed")
        if isinstance(seed, int):
            body["seed"] = seed
        else:
            body["seed"] = _SEED_RNG.randrange(1, _SEED_MAX)

        return body

    # ------------------------------------------------------------------

    def _generate_sync(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> bytes:
        if not reference_image:
            raise ValueError(
                "FalNanoBanana2Edit requires reference_image "
                "(Nano Banana 2 Edit is an image-to-image model)",
            )
        body = self._build_body(prompt, reference_image, params)
        logger.info(
            "FAL request model=%s prompt_len=%d resolution=%s aspect=%s keys=%s",
            self._model,
            len(prompt or ""),
            body.get("resolution"),
            body.get("aspect_ratio"),
            sorted(body.keys()),
        )
        return self._run_queue_sync(body)

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        assert_external_transfer_allowed("fal_nano_banana_2")
        raw = await asyncio.to_thread(
            self._generate_sync, prompt, reference_image, params,
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
                f"FAL Nano Banana 2: empty/invalid image ({exc})",
            ) from exc


__all__ = ["FalNanoBanana2Edit", "_resolution_for_quality"]

"""FAL.ai GPT Image 2 Edit image-gen provider.

Additive v1.21 A/B-test provider. Selected per-request when the web UI
sends ``image_model="gpt_image_2"``; otherwise the default hybrid
pipeline runs untouched.

Model: ``openai/gpt-image-2/edit`` (OpenAI ChatGPT Images 2.0 via fal).
The model accepts an explicit ``quality`` enum (``low`` / ``medium`` /
``high``) and a free-form ``image_size`` with both dimensions multiples
of 16. We forward ``quality`` verbatim and pick a square portrait size
per quality tier (1024 at low, 1536 at medium, 2048 at high) so the
request cost is predictable regardless of what the client uploads.

Empirical pricing (token-based — see fal model page):

* ``low``    ≈ $0.02-0.04 / image
* ``medium`` ≈ $0.05-0.08 / image (default)
* ``high``   ≈ $0.15-0.20 / image
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from PIL import Image

from src.providers.base import ImageGenProvider
from src.providers.image_gen._fal_queue_base import FalQueueClient
from src.services.ai_transfer_guard import assert_external_transfer_allowed

logger = logging.getLogger(__name__)


_QUALITY_TO_LONG_EDGE: dict[str, int] = {
    "low": 1024,
    "medium": 1536,
    "high": 2048,
}

_VALID_QUALITIES = frozenset(_QUALITY_TO_LONG_EDGE.keys())


def _long_edge_for_quality(quality: str | None) -> int:
    q = (quality or "medium").strip().lower()
    return _QUALITY_TO_LONG_EDGE.get(q, _QUALITY_TO_LONG_EDGE["medium"])


class FalGptImage2Edit(FalQueueClient, ImageGenProvider):
    """FAL.ai GPT Image 2 Edit client (OpenAI ChatGPT Images 2.0)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "openai/gpt-image-2/edit",
        api_host: str = "https://queue.fal.run",
        output_format: str = "jpeg",
        default_quality: str = "medium",
        max_retries: int = 2,
        request_timeout: float = 240.0,
        poll_interval: float = 2.0,
    ):
        super().__init__(
            api_key,
            model=model,
            api_host=api_host,
            max_retries=max_retries,
            request_timeout=request_timeout,
            poll_interval=poll_interval,
            label="GptImage2",
        )
        fmt = (output_format or "jpeg").lower()
        self._output_format = fmt if fmt in ("jpeg", "png", "webp") else "jpeg"
        self._default_quality = (
            default_quality if default_quality in _VALID_QUALITIES else "medium"
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
                "FAL GPT Image 2 Edit requires reference_image",
            )

        extras = params or {}
        quality = str(extras.get("quality") or self._default_quality).lower()
        if quality not in _VALID_QUALITIES:
            quality = self._default_quality
        long_edge = _long_edge_for_quality(quality)

        body: dict[str, Any] = {
            "prompt": prompt,
            "image_urls": [self._data_url(reference_image)],
            "quality": quality,
            "output_format": self._output_format,
            # Square portrait tier; both dimensions multiples of 16 are
            # required by the GPT Image 2 schema.
            "image_size": {"width": long_edge, "height": long_edge},
            "num_images": 1,
        }

        # Optional mask (future inpaint support — not used in MVP).
        mask_url = extras.get("mask_url")
        if isinstance(mask_url, str) and mask_url:
            body["mask_url"] = mask_url

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
                "FalGptImage2Edit requires reference_image "
                "(GPT Image 2 Edit is an image-to-image model)",
            )
        body = self._build_body(prompt, reference_image, params)
        logger.info(
            "FAL request model=%s prompt_len=%d quality=%s size=%s keys=%s",
            self._model,
            len(prompt or ""),
            body.get("quality"),
            body.get("image_size"),
            sorted(body.keys()),
        )
        return self._run_queue_sync(body)

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        assert_external_transfer_allowed("fal_gpt_image_2")
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
                f"FAL GPT Image 2: empty/invalid image ({exc})",
            ) from exc


__all__ = ["FalGptImage2Edit", "_long_edge_for_quality"]

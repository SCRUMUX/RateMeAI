"""FAL.ai GPT Image 2 Edit image-gen provider.

Additive v1.21 A/B-test provider. Selected per-request when the web UI
sends ``image_model="gpt_image_2"``; otherwise the default hybrid
pipeline runs untouched.

Model: ``openai/gpt-image-2/edit`` (OpenAI ChatGPT Images 2.0 via fal).
The model accepts an explicit ``quality`` enum (``low`` / ``medium`` /
``high``) and a free-form ``image_size`` with both dimensions multiples
of 16.

v1.23: switched the per-tier defaults from non-standard squares
(``1024² / 1536² / 2048²``) to OpenAI's officially-recommended sizes
from the GPT Image 2 docs (Image API guide and prompting cookbook):

* ``1024 x 1024`` square (low)
* ``1024 x 1536`` HD portrait (medium, default for portraits)
* ``1536 x 1024`` HD landscape (medium full-body)
* ``2560 x 1440`` 2K landscape (high; max reliability boundary)

The forced ``2048²`` we used in v1.22 is *not* in the recommended
list — that combination produced unstable latency and degraded
identity preservation, and on ``high`` it routinely tripped the
edge poll timeout. We now (a) honour an explicit ``image_size``
from the executor / StyleSpec when supplied and (b) fall back to
the white-listed sizes above.

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


_VALID_QUALITIES = frozenset(("low", "medium", "high"))

# OpenAI-recommended GPT Image 2 sizes (Image API guide, 2026 edition).
# Anything else either rounds DOWN to the nearest entry by total pixel
# count or is rejected. ``portrait`` / ``landscape`` is decided by the
# requested image_size aspect ratio.
_GPT2_PORTRAIT_SIZES: tuple[tuple[int, int], ...] = (
    (1024, 1024),
    (1024, 1536),
    (1440, 2560),
)
_GPT2_LANDSCAPE_SIZES: tuple[tuple[int, int], ...] = (
    (1024, 1024),
    (1536, 1024),
    (2560, 1440),
)


def _long_edge_for_quality(quality: str | None) -> int:
    """Backwards-compatible long-edge accessor for legacy tests.

    The provider no longer forces a square size, but a few legacy
    callsites (and tests) still ask "what's the canonical long edge
    for this quality tier?" — return the longest dimension of the
    portrait default per tier.
    """
    q = (quality or "medium").strip().lower()
    return {
        "low": 1024,
        "medium": 1536,
        "high": 2560,
    }.get(q, 1536)


def _default_size_for_quality(
    quality: str, *, portrait: bool = True,
) -> dict[str, int]:
    """Pick the OpenAI-recommended (width, height) for this tier."""
    table = _GPT2_PORTRAIT_SIZES if portrait else _GPT2_LANDSCAPE_SIZES
    idx = {"low": 0, "medium": 1, "high": 2}.get(quality, 1)
    w, h = table[idx]
    return {"width": w, "height": h}


def _sanitize_image_size(
    raw: Any, *, quality: str,
) -> dict[str, int]:
    """Snap an arbitrary ``{width, height}`` request onto a valid size.

    GPT Image 2 only ships a small set of officially-supported sizes
    on fal. Off-list values either fail the request outright or kick
    the model into a slow path. We respect the *aspect orientation*
    requested by the executor (portrait vs landscape) and pick the
    closest white-listed size for the active quality tier.
    """
    width = 0
    height = 0
    if isinstance(raw, dict):
        try:
            width = int(raw.get("width") or 0)
            height = int(raw.get("height") or 0)
        except (TypeError, ValueError):
            width = 0
            height = 0
    if width <= 0 or height <= 0:
        return _default_size_for_quality(quality, portrait=True)

    portrait = height >= width
    candidates = _GPT2_PORTRAIT_SIZES if portrait else _GPT2_LANDSCAPE_SIZES
    requested_pixels = width * height
    best = min(
        candidates, key=lambda wh: abs(wh[0] * wh[1] - requested_pixels),
    )
    return {"width": best[0], "height": best[1]}


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

    def _compress_reference(self, image_bytes: bytes, max_dim: int = 1536) -> bytes:
        """Compress the reference image to avoid proxy worker payload crashes.

        GPT Image 2 and Nano Banana 2 run through proxies (OpenAI/Google).
        Large data URIs (e.g. 5MB+) can crash the FAL proxy worker's JSON parser
        or exceed internal message broker limits, causing the request to hang
        IN_QUEUE forever (timeout after 240s) without showing up on the dashboard.
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
            if max(img.width, img.height) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
        except Exception as e:
            logger.warning("FalGptImage2Edit: failed to compress reference: %s", e)
            return image_bytes

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

        # Compress to prevent silent queue broker crashes on massive data URIs
        safe_reference = self._compress_reference(reference_image)

        extras = params or {}
        quality = str(extras.get("quality") or self._default_quality).lower()
        if quality not in _VALID_QUALITIES:
            quality = self._default_quality

        requested_size = extras.get("image_size")
        if requested_size:
            image_size = _sanitize_image_size(requested_size, quality=quality)
        else:
            image_size = _default_size_for_quality(quality, portrait=True)

        body: dict[str, Any] = {
            "prompt": prompt,
            "image_urls": [self._data_url(safe_reference)],
            "quality": quality,
            "output_format": self._output_format,
            "image_size": image_size,
            "num_images": 1,
            "sync_mode": True,
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


__all__ = [
    "FalGptImage2Edit",
    "_long_edge_for_quality",
    "_default_size_for_quality",
    "_sanitize_image_size",
]

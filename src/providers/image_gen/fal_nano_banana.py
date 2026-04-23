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

Quality -> resolution enum mapping (per fal schema, v1.24):

* ``low``    — ``1K``, fast mode     (~$0.08 / image, ≈ 1024px long edge)
* ``medium`` — ``2K``, fast mode     (~$0.12 / image, ≈ 2048px long edge)
* ``high``   — ``2K`` + thinking=high (~$0.12 / image, same pixels, +reasoning)

v1.22 bumped the floor from 0.5K to 1K because 512px portraits were
too blurry for production — the cheapest UI-visible output is now a
full ~1 MP image, matching the GPT Image 2 ``low`` tier.

v1.24 dropped the 4K tier and repurposed ``high`` as the
"reasoning-edit at 2K" knob — in production 4K added cost + latency
without a perceptible realism gain, while ``thinking_level="high"``
is the single biggest identity-preservation lever the NB2 endpoint
exposes. ``medium`` now runs the same 2K pixels without reasoning, so
the user-visible progression is: cheap/fast (1K) → more detail (2K)
→ more care for the face (2K + reasoning).

The Nano Banana 2 Edit schema does **not** accept an ``{width, height}``
``image_size``; it exposes ``resolution`` (enum ``0.5K | 1K | 2K | 4K``)
and ``aspect_ratio`` (enum with ``auto``) instead — we rely on
``aspect_ratio="auto"`` so the model infers aspect from the reference
portrait and we never 422 on framing mismatches.

The ``num_images=1`` knob is fixed; we deliberately do not expose batch
generation so Prometheus cost accounting stays 1-call = 1-image.

v1.23 identity-fidelity knobs (per FAL / Google docs and Nano Banana 2
prompting guide):

* ``thinking_level="high"`` is enabled for the ``high`` quality tier
  only (v1.24). The Gemini 3.1 Flash Image backing this endpoint
  supports a reasoning mode that plans the edit before rendering; in
  practice this is the single biggest lever for holding the reference
  face together on non-trivial edits. ``low`` / ``medium`` stay on
  fast mode so the cheaper tiers keep their 5-10 s latency budget.
* ``limit_generations=True`` is sent explicitly so the model cannot
  decide to emit multiple intermediate frames (which the FAL wrapper
  otherwise lets bleed through into cost/time).
* ``safety_tolerance="4"`` is the fal default but we pin it so our
  metrics and logs stay reproducible across deployments.
* ``aspect_ratio`` is caller-controlled (executor derives it from the
  StyleSpec), with ``auto`` as the backstop.
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
    # v1.24: ``high`` is now "2K + thinking=high" rather than "4K fast".
    # Resolution is capped at 2K — 4K added latency + cost without a
    # perceptible realism gain in our tests.
    "high": "2K",
}

_VALID_ASPECT_RATIOS = frozenset(
    {
        "auto",
        "21:9",
        "16:9",
        "3:2",
        "4:3",
        "5:4",
        "1:1",
        "4:5",
        "3:4",
        "2:3",
        "9:16",
        "4:1",
        "1:4",
        "8:1",
        "1:8",
    }
)

_VALID_THINKING_LEVELS = frozenset({"minimal", "high"})
_VALID_SAFETY_TOLERANCES = frozenset({"1", "2", "3", "4", "5", "6"})


def _resolution_for_quality(quality: str | None) -> str:
    q = (quality or "medium").strip().lower()
    return _QUALITY_TO_RESOLUTION.get(q, _QUALITY_TO_RESOLUTION["medium"])


def _thinking_level_for_quality(quality: str | None) -> str | None:
    """Pick the Gemini reasoning level for this quality tier.

    v1.24: only ``high`` opts into reasoning. ``low`` and ``medium``
    use the fast non-reasoning mode so their latency budget stays
    5-10 s; ``high`` trades ~40-60% extra latency for the strongest
    face-preservation signal the endpoint exposes.
    """
    q = (quality or "medium").strip().lower()
    if q == "high":
        return "high"
    return None


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
            default_quality if default_quality in _QUALITY_TO_RESOLUTION else "medium"
        )

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------

    def _compress_reference(self, image_bytes: bytes, max_dim: int = 1536) -> bytes:
        """Compress the reference image to avoid proxy worker payload crashes.

        Google Gemini 3.1 Flash Image via FAL.ai proxy. Large data URIs
        (e.g. 5MB+) can crash the FAL proxy worker's JSON parser or exceed
        internal message broker limits, causing the request to hang IN_QUEUE
        forever (timeout after 240s) without showing up on the dashboard.
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
            logger.warning("FalNanoBanana2Edit: failed to compress reference: %s", e)
            return image_bytes

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

        safe_reference = self._compress_reference(reference_image)

        extras = params or {}
        quality = str(extras.get("quality") or self._default_quality).lower()
        if quality not in _QUALITY_TO_RESOLUTION:
            quality = self._default_quality
        resolution = _resolution_for_quality(quality)

        aspect_ratio = str(extras.get("aspect_ratio") or "auto")
        if aspect_ratio not in _VALID_ASPECT_RATIOS:
            aspect_ratio = "auto"

        thinking_level = extras.get("thinking_level")
        if thinking_level is None:
            thinking_level = _thinking_level_for_quality(quality)
        elif thinking_level not in _VALID_THINKING_LEVELS:
            thinking_level = _thinking_level_for_quality(quality)

        safety_tolerance = str(extras.get("safety_tolerance") or "4")
        if safety_tolerance not in _VALID_SAFETY_TOLERANCES:
            safety_tolerance = "4"

        body: dict[str, Any] = {
            "prompt": prompt,
            "image_urls": [self._data_url(safe_reference)],
            "num_images": 1,
            "output_format": self._output_format,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "safety_tolerance": safety_tolerance,
            "limit_generations": True,
            "sync_mode": True,
        }

        if thinking_level:
            body["thinking_level"] = thinking_level

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
            "FAL request model=%s prompt_len=%d resolution=%s aspect=%s "
            "thinking=%s keys=%s",
            self._model,
            len(prompt or ""),
            body.get("resolution"),
            body.get("aspect_ratio"),
            body.get("thinking_level", "none"),
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
            self._generate_sync,
            prompt,
            reference_image,
            params,
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


__all__ = [
    "FalNanoBanana2Edit",
    "_resolution_for_quality",
    "_thinking_level_for_quality",
]

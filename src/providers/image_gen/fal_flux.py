"""FAL.ai FLUX.1 Kontext [pro] image-gen provider.

Legacy provider — as of v1.16 the default runtime is FLUX.2 Pro Edit
(``fal_flux2``), and as of v1.18 the primary path is the hybrid
StyleRouter (PuLID + Seedream + FLUX.2 fallback). FLUX.1 Kontext is
kept as a one-release rollback target, still reachable via
``IMAGE_GEN_STRATEGY=legacy`` + ``IMAGE_GEN_PROVIDER=fal_flux``. The
factory never picks it otherwise.

Wire contract
-------------
Queue submit:  ``POST  {host}/{model}`` body + Auth header

The submit response contains two fully-qualified URLs::

    {"request_id": "...", "status_url": "...", "response_url": "..."}

which we **must** reuse verbatim for status polling and result fetch.
Constructing ``{host}/{model}/requests/{id}/status`` manually breaks
for apps whose model path has sub-paths (e.g. ``fal-ai/flux-pro/kontext``)
— FAL returns HTTP 405 Method Not Allowed on such synthetic URLs while
the ``status_url`` from the response resolves correctly.

With ``sync_mode=True`` in the submit body the final image is returned
as a data URI inside ``response.images[0].url``, so we never need a
second HTTP fetch against ``fal.media``. This keeps every generation
at exactly 3 HTTP calls in the happy path (submit → status → result)
and avoids egress routing quirks on edge networks.

Queue / poll / fetch / decode lives in
:class:`src.providers.image_gen._fal_queue_base.FalQueueClient` (v1.20.0).
This file contributes only the Kontext-specific ``_build_body`` + the
``generate`` wrapper. The :class:`FalAPIError` hierarchy is defined in
the queue base; we re-export it here so older
``from src.providers.image_gen.fal_flux import FalAPIError`` imports
keep working.

Pricing
-------
$0.04 per image for ``fal-ai/flux-pro/kontext``, independent of output
megapixels. Tracked in ``settings.model_cost_fal_flux`` and by the
``ratemeai_fal_calls_total`` Prometheus counter.
"""
from __future__ import annotations

import asyncio
import io
import logging
import random
from typing import Any

from PIL import Image

from src.providers.base import ImageGenProvider
from src.providers.image_gen._fal_queue_base import (
    FalAPIError,
    FalContentViolationError,
    FalQueueClient,
    FalRateLimitError,
)
from src.services.ai_transfer_guard import assert_external_transfer_allowed

_SEED_MAX = 2**31 - 1
_SEED_RNG = random.SystemRandom()

logger = logging.getLogger(__name__)


class FalFluxImageGen(FalQueueClient, ImageGenProvider):
    """FAL.ai FLUX.1 Kontext [pro] client (image-to-image edit)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/flux-pro/kontext",
        api_host: str = "https://queue.fal.run",
        guidance_scale: float = 3.5,
        safety_tolerance: str = "2",
        output_format: str = "jpeg",
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
            label="Kontext",
        )
        self._guidance_scale = float(guidance_scale)
        self._safety_tolerance = str(safety_tolerance)
        self._output_format = output_format.lower()
        if self._output_format not in ("jpeg", "png"):
            self._output_format = "jpeg"

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Body builder — FLUX.1 Kontext Pro specific
    # ------------------------------------------------------------------

    def _build_body(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> dict[str, Any]:
        """Strict whitelist body for FLUX Kontext Pro.

        ``sync_mode=True`` instructs FAL to inline the result as a data
        URI so we can decode it directly after the result GET without a
        second fetch.
        """
        if not reference_image:
            raise ValueError("FAL FLUX Kontext requires reference_image")

        body: dict[str, Any] = {
            "prompt": prompt,
            "image_url": self._data_url(reference_image),
            "guidance_scale": self._guidance_scale,
            "num_images": 1,
            "output_format": self._output_format,
            "safety_tolerance": self._safety_tolerance,
            "sync_mode": True,
        }

        extras = params or {}
        seed = extras.get("seed")
        if isinstance(seed, int):
            body["seed"] = seed
        else:
            # Default to a fresh random seed on every call. FLUX Kontext is
            # composition-conservative with the reference image — rotating
            # the seed gives a small but consistent diversity boost without
            # costing anything extra (one generation per request).
            body["seed"] = _SEED_RNG.randrange(1, _SEED_MAX)
        aspect_ratio = extras.get("aspect_ratio")
        if isinstance(aspect_ratio, str) and aspect_ratio:
            body["aspect_ratio"] = aspect_ratio
        if extras.get("enhance_prompt") is True:
            body["enhance_prompt"] = True
        return body

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _generate_sync(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> bytes:
        if not reference_image:
            raise ValueError(
                "FalFluxImageGen requires reference_image "
                "(FLUX Kontext Pro is an image-to-image model)"
            )
        body = self._build_body(prompt, reference_image, params)
        logger.info(
            "FAL request model=%s prompt_len=%d keys=%s",
            self._model, len(prompt or ""), sorted(body.keys()),
        )
        return self._run_queue_sync(body)

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        assert_external_transfer_allowed("fal_flux")
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
            raise RuntimeError(f"FAL: empty/invalid image ({exc})") from exc


__all__ = [
    "FalFluxImageGen",
    "FalAPIError",
    "FalRateLimitError",
    "FalContentViolationError",
]

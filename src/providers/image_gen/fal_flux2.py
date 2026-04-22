"""FAL.ai FLUX.2 [pro] image-gen provider (edit endpoint).

StyleRouter's emergency fallback provider — every request that can't
be served by PuLID (identity_scene) or Seedream (scene_preserve) ends
up here. Succeeds the older Kontext-based ``FalFluxImageGen`` — both
share the same queue-submit / poll / fetch / decode wire protocol (see
:class:`src.providers.image_gen._fal_queue_base.FalQueueClient`), but
FLUX.2 Pro Edit has a materially different input shape:

- ``image_urls`` is a list of references (supports multi-reference
  out of the box) — we always send ``[reference_image]`` today, but
  the list signature unlocks style-reference photos later without a
  schema change.
- ``image_size`` replaces Kontext's ``aspect_ratio``. It accepts both
  a preset enum (``square_hd``, ``portrait_4_3`` …) and a custom
  ``{"width": W, "height": H}`` dict. This is the main reason we
  migrated: FLUX.2 Pro can actually produce 2 MP / 4 MP portraits,
  Kontext Pro was hard-capped at ~1 MP with no size control.
- No ``guidance_scale`` / ``enhance_prompt`` knobs (the model auto-
  tunes both). Prompt adherence is driven by the prompt itself.

Pricing
-------
``fal-ai/flux-2-pro/edit`` bills $0.03 for the first output megapixel
plus $0.015 per additional megapixel, rounded up, capped at 4 MP.
We run at 2 MP by default (portrait 4:3 → ≈1280×1600). The cost
observer in ``src/metrics.py`` computes the per-call dollar amount
from ``image_size`` to keep Prometheus accurate.
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

_SEED_MAX = 2**31 - 1
_SEED_RNG = random.SystemRandom()

logger = logging.getLogger(__name__)

# FLUX.2 Pro Edit preset sizes accepted verbatim by the API.
_PRESET_IMAGE_SIZES = frozenset({
    "auto",
    "square_hd",
    "square",
    "portrait_4_3",
    "portrait_16_9",
    "landscape_4_3",
    "landscape_16_9",
})


class FalFlux2ImageGen(FalQueueClient, ImageGenProvider):
    """FAL.ai FLUX.2 [pro] edit client (image-to-image edit, up to 4 MP)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/flux-2-pro/edit",
        api_host: str = "https://queue.fal.run",
        safety_tolerance: str = "2",
        output_format: str = "jpeg",
        default_image_size: Any = "portrait_4_3",
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
            label="Flux2",
        )
        tol = str(safety_tolerance or "2").strip()
        if tol not in {"1", "2", "3", "4", "5"}:
            tol = "2"
        self._safety_tolerance = tol
        self._output_format = output_format.lower()
        if self._output_format not in ("jpeg", "png"):
            self._output_format = "jpeg"
        self._default_image_size = default_image_size

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Body builder — FLUX.2 Pro Edit specific
    # ------------------------------------------------------------------

    @classmethod
    def _normalize_image_size(cls, value: Any) -> Any | None:
        """Return a value safe to put on the wire as ``image_size``.

        Accepts either a preset enum string (``portrait_4_3`` …) or a
        ``{"width": int, "height": int}`` dict. Unknown strings and
        malformed dicts fall back to ``None`` so the provider can
        substitute the configured default.
        """
        if isinstance(value, str):
            v = value.strip()
            if v in _PRESET_IMAGE_SIZES:
                return v
            return None
        if isinstance(value, dict):
            w = value.get("width")
            h = value.get("height")
            try:
                wi, hi = int(w), int(h)
            except (TypeError, ValueError):
                return None
            if wi < 64 or hi < 64 or wi > 4096 or hi > 4096:
                return None
            return {"width": wi, "height": hi}
        return None

    def _build_body(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> dict[str, Any]:
        """Strict whitelist body for FLUX.2 Pro Edit.

        ``sync_mode=True`` inlines the result as a data URI so we can
        decode it directly from the result GET, same as Kontext.
        ``image_urls`` is a **list** even for the single-reference
        case — the FLUX.2 schema requires it.
        """
        if not reference_image:
            raise ValueError("FAL FLUX.2 Pro Edit requires reference_image")

        body: dict[str, Any] = {
            "prompt": prompt,
            "image_urls": [self._data_url(reference_image)],
            "num_images": 1,
            "output_format": self._output_format,
            "safety_tolerance": self._safety_tolerance,
            "enable_safety_checker": True,
            "sync_mode": True,
        }

        extras = params or {}
        seed = extras.get("seed")
        if isinstance(seed, int):
            body["seed"] = seed
        else:
            # Default to a fresh random seed per call. Diversity service
            # relies on this for variant rotation without paying for a
            # second generation (see src/services/variation.py).
            body["seed"] = _SEED_RNG.randrange(1, _SEED_MAX)

        size = self._normalize_image_size(extras.get("image_size"))
        if size is None:
            size = self._normalize_image_size(self._default_image_size)
        if size is not None:
            body["image_size"] = size
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
                "FalFlux2ImageGen requires reference_image "
                "(FLUX.2 Pro Edit is an image-to-image model)"
            )
        body = self._build_body(prompt, reference_image, params)
        size_log = body.get("image_size", "default")
        logger.info(
            "FAL request model=%s prompt_len=%d size=%s keys=%s",
            self._model, len(prompt or ""), size_log, sorted(body.keys()),
        )
        return self._run_queue_sync(body)

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        assert_external_transfer_allowed("fal_flux2")
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


__all__ = ["FalFlux2ImageGen"]

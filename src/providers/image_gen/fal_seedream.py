"""FAL.ai Seedream v4 Edit provider — scene-preserving image edit (v1.18).

Seedream 4.0 (Bytedance) is a generative edit model with relatively
good identity preservation and support for up to 4 MP output at a flat
$0.03 per image. We use it for styles where the **original scene must
be preserved** (social_clean, cv_portrait, strict backgrounds).

Why Seedream and not FLUX.2 Pro Edit
------------------------------------
Same price point ($0.03), but Seedream v4 Edit:

- Supports native image_size up to 4 MP in the edit path (FLUX.2 Pro
  Edit bills per-megapixel, so 4 MP costs $0.075 there).
- Accepts multiple reference images (``image_urls`` list) out of the
  box — useful later for style-reference pairing.
- Stable identity preservation empirically — comparable to FLUX.2
  Edit on frontal portraits, sometimes better on 3/4 angles.

Wire contract
-------------
    POST https://queue.fal.run/fal-ai/bytedance/seedream/v4/edit
    {
        "prompt": "...",
        "image_urls": ["data:image/jpeg;base64,..."],
        "image_size": {"width": 2048, "height": 2048} | "portrait_4_3",
        "num_images": 1,
        "enable_safety_checker": true,
        "enhance_prompt_mode": "standard" | "fast",
        "seed": <int>
    }

Note: Seedream does NOT accept ``safety_tolerance`` or ``output_format``
knobs (those are FLUX-specific) — sending them is ignored but we omit
them to keep the wire cleaner.

Pricing
-------
$0.03 per image (flat, up to 4 MP). Tracked as
``settings.model_cost_fal_seedream``.
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

_PRESET_IMAGE_SIZES = frozenset({
    "square_hd",
    "square",
    "portrait_4_3",
    "portrait_16_9",
    "landscape_4_3",
    "landscape_16_9",
})

_ENHANCE_MODES = frozenset({"standard", "fast"})


class FalSeedreamImageGen(FalQueueClient, ImageGenProvider):
    """FAL.ai Seedream v4 Edit client."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/bytedance/seedream/v4/edit",
        api_host: str = "https://queue.fal.run",
        enhance_prompt_mode: str = "standard",
        enable_safety_checker: bool = True,
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
            label="Seedream",
        )
        mode = (enhance_prompt_mode or "standard").strip()
        self._enhance_mode = mode if mode in _ENHANCE_MODES else "standard"
        self._safety = bool(enable_safety_checker)
        self._default_image_size = default_image_size

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Body builder
    # ------------------------------------------------------------------

    @classmethod
    def _normalize_image_size(cls, value: Any) -> Any | None:
        if isinstance(value, str):
            v = value.strip()
            if v in _PRESET_IMAGE_SIZES:
                return v
            return None
        if isinstance(value, dict):
            w, h = value.get("width"), value.get("height")
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
        if not reference_image:
            raise ValueError(
                "FalSeedreamImageGen requires reference_image "
                "(Seedream v4 Edit is an image-to-image model)"
            )

        extras = params or {}
        image_urls: list[str] = [self._data_url(reference_image)]
        for extra in extras.get("extra_reference_images") or []:
            if isinstance(extra, (bytes, bytearray)) and extra:
                image_urls.append(self._data_url(bytes(extra)))
            if len(image_urls) >= 10:
                break

        body: dict[str, Any] = {
            "prompt": prompt,
            "image_urls": image_urls,
            "num_images": 1,
            "enable_safety_checker": self._safety,
            "enhance_prompt_mode": (
                extras.get("enhance_prompt_mode") or self._enhance_mode
            ),
        }

        if body["enhance_prompt_mode"] not in _ENHANCE_MODES:
            body["enhance_prompt_mode"] = "standard"

        seed = extras.get("seed")
        if isinstance(seed, int):
            body["seed"] = seed
        else:
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
        body = self._build_body(prompt, reference_image, params)
        logger.info(
            "FAL Seedream request model=%s prompt_len=%d size=%s "
            "enhance=%s refs=%d",
            self._model, len(prompt or ""),
            body.get("image_size", "default"),
            body.get("enhance_prompt_mode"),
            len(body.get("image_urls") or []),
        )
        return self._run_queue_sync(body)

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        assert_external_transfer_allowed("fal_seedream")
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
                f"FAL Seedream: empty/invalid image ({exc})",
            ) from exc


__all__ = ["FalSeedreamImageGen"]

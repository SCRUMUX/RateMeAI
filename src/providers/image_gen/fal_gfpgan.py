"""FAL.ai GFPGAN face-restoration client (v1.17).

Thin client for ``fal-ai/gfpgan``, used as a *pre-clean* step before
the main generator when the input photo has a blurry / low-quality
face (see :mod:`src.services.face_prerestore` for activation rules).
Unlike the FLUX.2 or Seedream providers this is NOT an
``ImageGenProvider`` — GFPGAN does not accept a prompt; it just takes
one input image and returns a restored version. The public surface
is :meth:`FalGfpganRestorer.restore`.

Wire protocol lives in
:class:`src.providers.image_gen._fal_queue_base.FalQueueClient` — the
FAL queue contract is uniform across models and there is no
behavioural reason to maintain a private copy of it per provider
(v1.20.0 unification).

Pricing
-------
fal-ai/gfpgan bills ~$0.001–$0.002 per image (flat). We treat it as
$0.002 for budget math (``settings.model_cost_fal_gfpgan``).
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


class FalGfpganRestorer(FalQueueClient):
    """FAL.ai GFPGAN face-restoration client.

    Single-method surface: :meth:`restore`. Any error (transport, HTTP
    4xx/5xx, NSFW, parse) bubbles up so the caller can fall back to
    the original image — pre-restoration is always optional, never
    load-bearing.
    """

    # GFPGAN returns either ``image: {url}`` or ``images: [{url}]``.
    # Prefer the plural form used by newer schemas.
    _image_response_keys = ("images", "image")

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/gfpgan",
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
            label="GFPGAN",
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
        """Body for fal-ai/gfpgan.

        ``prompt`` is unused (GFPGAN has no prompt); the signature
        matches :meth:`FalQueueClient._build_body` only so subclassing
        stays consistent. Callers should use :meth:`restore` instead.
        """
        if not reference_image:
            raise ValueError("FalGfpganRestorer requires image bytes")
        return {
            "image_url": self._data_url(reference_image),
            "sync_mode": True,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _restore_sync(self, image_bytes: bytes) -> bytes:
        body = self._build_body(
            prompt=None,
            reference_image=image_bytes,
            params=None,
        )
        logger.info(
            "FAL GFPGAN request model=%s input_bytes=%d",
            self._model,
            len(image_bytes or b""),
        )
        return self._run_queue_sync(body)

    async def restore(self, image_bytes: bytes) -> bytes:
        """Run GFPGAN face-restoration on ``image_bytes``.

        Returns the restored JPEG/PNG bytes. Raises :class:`RuntimeError`
        on any terminal FAL error. The caller is expected to fall back
        to the original bytes on failure — pre-restoration is a
        nice-to-have, never a load-bearing stage.
        """
        assert_external_transfer_allowed("fal_gfpgan")
        raw = await asyncio.to_thread(self._restore_sync, image_bytes)
        if raw and len(raw) > 100:
            return raw
        # Unusually small payload — try to salvage via PIL round-trip
        # (mirrors fal_flux2 behaviour).
        try:
            img = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92)
            return buf.getvalue()
        except Exception as exc:
            raise RuntimeError(
                f"FAL GFPGAN: empty/invalid image ({exc})",
            ) from exc


__all__ = ["FalGfpganRestorer"]

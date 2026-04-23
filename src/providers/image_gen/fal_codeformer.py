"""FAL.ai CodeFormer face restoration (v1.18).

CodeFormer is a transformer-based blind face restoration model with a
tunable *fidelity* knob (0 = strongest restoration / most "perfect"
features, 1 = closest to the input / most identity-preserving).

In the v1.18 pipeline we run CodeFormer as the **final face-polish**
step right after the main generator (PuLID or Seedream). It fixes the
soft/blurry face that both FLUX-Lightning (PuLID, 4-step) and Seedream
sometimes produce, without meaningfully changing the identity.

Wire contract
-------------
    POST https://queue.fal.run/fal-ai/codeformer
    {
        "image_url": "data:image/jpeg;base64,...",
        "fidelity": 0.5,
        "upscale_factor": 2,
        "aligned": false,
        "only_center_face": false,
        "face_upscale": true,
        "seed": <int>
    }

Unlike an image generator, CodeFormer does NOT take a prompt and does
NOT implement ``ImageGenProvider``. It has a single method
``restore(image_bytes)`` whose failure is always treated as non-fatal
by the caller (we keep the original image if restoration fails).

Pricing
-------
$0.0021 per megapixel (see fal.ai/models/fal-ai/codeformer). On a
1 MP input with ``upscale_factor=2`` we pay ~$0.0084 worst-case.
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


class FalCodeFormerRestorer(FalQueueClient):
    """FAL.ai CodeFormer face-restoration client."""

    # CodeFormer returns a single ``image`` object, not a plural list.
    _image_response_keys = ("image", "images")

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/codeformer",
        api_host: str = "https://queue.fal.run",
        fidelity: float = 0.5,
        upscale_factor: float = 2.0,
        face_upscale: bool = True,
        only_center_face: bool = False,
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
            label="CodeFormer",
        )
        self._fidelity = max(0.0, min(1.0, float(fidelity)))
        self._upscale_factor = max(1.0, min(4.0, float(upscale_factor)))
        self._face_upscale = bool(face_upscale)
        self._only_center_face = bool(only_center_face)

    # ------------------------------------------------------------------
    # Body builder
    # ------------------------------------------------------------------

    def _build_body(
        self,
        prompt: str | None = None,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Strict whitelist body for fal-ai/codeformer.

        The ``prompt`` parameter is unused (CodeFormer has no prompt);
        the signature matches :class:`FalQueueClient._build_body` only
        for consistency — callers should use :meth:`restore` instead.
        """
        if not reference_image:
            raise ValueError("FalCodeFormerRestorer requires image bytes")
        extras = params or {}
        body: dict[str, Any] = {
            "image_url": self._data_url(reference_image),
            "fidelity": float(
                extras.get("fidelity")
                if extras.get("fidelity") is not None
                else self._fidelity
            ),
            "upscale_factor": float(
                extras.get("upscale_factor") or self._upscale_factor,
            ),
            "face_upscale": bool(
                extras.get("face_upscale")
                if extras.get("face_upscale") is not None
                else self._face_upscale
            ),
            "only_center_face": bool(
                extras.get("only_center_face")
                if extras.get("only_center_face") is not None
                else self._only_center_face
            ),
            "sync_mode": True,
        }
        body["fidelity"] = max(0.0, min(1.0, body["fidelity"]))
        body["upscale_factor"] = max(1.0, min(4.0, body["upscale_factor"]))
        seed = extras.get("seed")
        if isinstance(seed, int):
            body["seed"] = seed
        return body

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _restore_sync(
        self,
        image_bytes: bytes,
        params: dict | None = None,
    ) -> bytes:
        body = self._build_body(
            prompt=None,
            reference_image=image_bytes,
            params=params,
        )
        logger.info(
            "FAL CodeFormer request model=%s fidelity=%.2f upscale=%.1f "
            "face_upscale=%s",
            self._model,
            body.get("fidelity"),
            body.get("upscale_factor"),
            body.get("face_upscale"),
        )
        return self._run_queue_sync(body)

    async def restore(
        self,
        image_bytes: bytes,
        *,
        fidelity: float | None = None,
        upscale_factor: float | None = None,
    ) -> bytes:
        """Run CodeFormer on ``image_bytes`` and return the restored bytes.

        Raises :class:`RuntimeError` on any terminal FAL failure. The
        caller is expected to fall back to the original image on
        failure — face-restoration is always optional, never
        load-bearing.
        """
        assert_external_transfer_allowed("fal_codeformer")
        params: dict[str, Any] = {}
        if fidelity is not None:
            params["fidelity"] = fidelity
        if upscale_factor is not None:
            params["upscale_factor"] = upscale_factor
        raw = await asyncio.to_thread(
            self._restore_sync,
            image_bytes,
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
                f"FAL CodeFormer: empty/invalid image ({exc})",
            ) from exc


__all__ = ["FalCodeFormerRestorer"]

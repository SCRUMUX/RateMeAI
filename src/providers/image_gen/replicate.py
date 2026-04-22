"""Reserved: Replicate FLUX provider.

Disabled in the current runtime (``IMAGE_GEN_PROVIDER=reve``). Kept as
the baseline for:

* Phase 3 FLUX integration via FAL.ai — its input/output contract
  (prompt + aspect_ratio + reference image) maps directly onto the
  forthcoming ``FluxFALProvider``;
* manual override for debugging (``IMAGE_GEN_PROVIDER=replicate``);
* capability-based routing inside
  :mod:`src.orchestrator.advanced.model_router`.

See ``docs/architecture/reserved.md`` for activation instructions.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.providers.base import ImageGenProvider, StorageProvider
from src.services.ai_transfer_guard import assert_external_transfer_allowed

logger = logging.getLogger(__name__)

_REVE_ONLY_PARAMS = {"test_time_scaling"}
_VALID_FLUX_ASPECT_RATIOS = {
    "1:1", "16:9", "9:16", "21:9", "9:21",
    "4:3", "3:4", "4:5", "5:4", "2:3", "3:2",
}


class ReplicateImageGen(ImageGenProvider):
    """Replicate predictions API; reference image is uploaded to storage and passed as URL."""

    def __init__(self, api_token: str, model_version: str, storage: StorageProvider):
        self._token = api_token.strip()
        self._version = model_version.strip()
        self._is_model_name = "/" in self._version
        self._storage = storage
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=30.0),
            headers={
                "Authorization": f"Token {self._token}",
                "Content-Type": "application/json",
            },
        )

    async def close(self):
        await self._client.aclose()

    @staticmethod
    def _clean_params(params: dict | None) -> dict:
        """Remove Reve-specific params and normalize FLUX-compatible ones."""
        if not params:
            return {}
        cleaned = {k: v for k, v in params.items() if k not in _REVE_ONLY_PARAMS}
        ar = cleaned.get("aspect_ratio")
        if ar and ar not in _VALID_FLUX_ASPECT_RATIOS:
            cleaned.pop("aspect_ratio", None)
        return cleaned

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException, TimeoutError)),
    )
    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        assert_external_transfer_allowed("replicate")
        if not self._version:
            raise ValueError("REPLICATE_MODEL_VERSION is required for image generation")

        params = dict(params) if params else {}

        image_url = None
        if reference_image:
            key = f"temp/replicate/{uuid.uuid4()}.jpg"
            await self._storage.upload(key, reference_image)
            image_url = await self._storage.get_url(key)

        mask_url = None
        mask_bytes = params.pop("mask_image", None)
        params.pop("mask_region", None)
        if mask_bytes and isinstance(mask_bytes, bytes):
            mkey = f"temp/replicate/{uuid.uuid4()}_mask.png"
            await self._storage.upload(mkey, mask_bytes)
            mask_url = await self._storage.get_url(mkey)

        prompt_strength = params.pop("prompt_strength", None)
        params = self._clean_params(params)

        inp: dict = {
            "prompt": prompt,
            "output_format": "jpg",
            "output_quality": 90,
            "safety_tolerance": 5,
        }
        if image_url:
            inp["image"] = image_url
            if prompt_strength is not None:
                inp["prompt_strength"] = float(prompt_strength)
        if mask_url:
            inp["mask"] = mask_url
        if params:
            inp.update(params)

        if self._is_model_name:
            url = f"https://api.replicate.com/v1/models/{self._version}/predictions"
            body: dict = {"input": inp}
        else:
            url = "https://api.replicate.com/v1/predictions"
            body = {"version": self._version, "input": inp}

        r = await self._client.post(url, json=body)
        r.raise_for_status()
        pred = r.json()
        status_url = pred["urls"]["get"]

        for _ in range(90):
            pr = await self._client.get(status_url)
            pr.raise_for_status()
            data = pr.json()
            st = data.get("status")
            if st == "succeeded":
                out = data.get("output")
                break
            if st == "failed":
                raise RuntimeError(data.get("error", "replicate failed"))
            await asyncio.sleep(2)
        else:
            raise TimeoutError("replicate prediction timeout")

        if isinstance(out, list):
            if not out:
                raise RuntimeError("Replicate returned empty output list")
            img_url = out[0]
        else:
            img_url = out
        if not img_url:
            return b""

        ir = await self._client.get(img_url)
        ir.raise_for_status()
        return ir.content

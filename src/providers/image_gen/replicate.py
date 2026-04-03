from __future__ import annotations

import asyncio
import logging
import uuid

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.providers.base import ImageGenProvider, StorageProvider

logger = logging.getLogger(__name__)


class ReplicateImageGen(ImageGenProvider):
    """Replicate predictions API; reference image is uploaded to storage and passed as URL."""

    def __init__(self, api_token: str, model_version: str, storage: StorageProvider):
        self._token = api_token.strip()
        self._version = model_version.strip()
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

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, TimeoutError)),
    )
    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        if not self._version:
            raise ValueError("REPLICATE_MODEL_VERSION is required for image generation")

        image_url = None
        if reference_image:
            key = f"temp/replicate/{uuid.uuid4()}.jpg"
            await self._storage.upload(key, reference_image)
            image_url = await self._storage.get_url(key)

        inp: dict = {"prompt": prompt}
        if image_url:
            inp["image"] = image_url
        if params:
            inp.update(params)

        r = await self._client.post(
            "https://api.replicate.com/v1/predictions",
            json={"version": self._version, "input": inp},
        )
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

        img_url = out[0] if isinstance(out, list) else out
        if not img_url:
            return b""

        ir = await self._client.get(img_url)
        ir.raise_for_status()
        return ir.content

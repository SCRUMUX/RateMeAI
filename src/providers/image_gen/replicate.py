from __future__ import annotations

import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.providers.base import ImageGenProvider

logger = logging.getLogger(__name__)


class ReplicateImageGen(ImageGenProvider):
    """Replicate API integration for image generation with identity preservation."""

    def __init__(self, api_token: str):
        self._api_token = api_token
        self._client = httpx.AsyncClient(timeout=120.0)
        self._base_url = "https://api.replicate.com/v1"

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=5, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
    )
    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        # Placeholder — full Replicate integration is Phase 2 of the roadmap.
        # In MVP, image generation modes (dating/cv) use mock.
        raise NotImplementedError("Replicate integration is scheduled for Phase 2")

    async def close(self):
        await self._client.aclose()

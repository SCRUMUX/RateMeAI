from __future__ import annotations

from src.providers.base import ImageGenProvider


class MockImageGen(ImageGenProvider):
    """Returns the reference image unchanged for testing and dev loopback."""

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        if reference_image:
            return reference_image
        return b""

    async def close(self):
        pass

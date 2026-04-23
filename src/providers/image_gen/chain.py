"""Reserved: fallback chain image generator.

Not wired into the current runtime factory (the active provider is
``ReveImageGen``). Kept as a scaffold for scenario-based fallback
chains — for instance, a future ``scenario=document_passport_rf``
might prefer FLUX first and degrade to Reve on failure. The chain
will be reactivated from the Scenario Engine once it exposes
``preferred_provider_hint``.

See ``docs/architecture/reserved.md``.
"""

from __future__ import annotations

import logging
from typing import Sequence

from src.providers.base import ImageGenProvider

logger = logging.getLogger(__name__)


class ChainImageGen(ImageGenProvider):
    """Try multiple providers in order; first successful result wins."""

    def __init__(self, providers: Sequence[ImageGenProvider]):
        if not providers:
            raise ValueError("ChainImageGen requires at least one provider")
        self._providers = list(providers)

    @property
    def providers(self) -> list[ImageGenProvider]:
        """Public read-only access to the chain's provider list."""
        return list(self._providers)

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        last_err: Exception | None = None
        for i, provider in enumerate(self._providers):
            name = type(provider).__name__
            try:
                result = await provider.generate(prompt, reference_image, params)
                if result and len(result) > 100:
                    logger.info(
                        "ChainImageGen: %s succeeded (%d bytes)", name, len(result)
                    )
                    return result
                logger.warning(
                    "ChainImageGen: %s returned empty/tiny result, trying next", name
                )
            except Exception as e:
                logger.warning(
                    "ChainImageGen: %s failed (%s), trying next provider", name, e
                )
                last_err = e
        if last_err:
            raise last_err
        return b""

    async def close(self):
        for p in self._providers:
            if hasattr(p, "close"):
                try:
                    await p.close()
                except Exception:
                    pass

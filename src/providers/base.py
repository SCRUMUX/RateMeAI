from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        temperature: float = 0.7,
    ) -> dict:
        """Send image + prompt to vision model, return parsed JSON."""

    @abstractmethod
    async def generate_text(self, prompt: str) -> str:
        """Generate text completion."""

    async def compare_images(
        self,
        image_a_bytes: bytes,
        image_b_bytes: bytes,
        prompt: str,
        *,
        temperature: float = 0.0,
    ) -> dict:
        """Send two images + prompt to the VLM in a single call.

        Default implementation: raise NotImplementedError. Providers that
        support multi-image vision (OpenRouter) should override this.
        Used by the quality-gate VLM identity check — no embeddings, no
        persistent state.
        """
        raise NotImplementedError(
            "This LLM provider does not support multi-image comparison"
        )

    async def close(self) -> None:
        """Release resources (HTTP clients, connections)."""


class ImageGenProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        """Generate image from prompt, optionally using reference image for identity preservation."""

    async def close(self) -> None:
        """Release resources."""


class StorageProvider(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes) -> str:
        """Upload data, return storage key (use get_url for public URL)."""

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download data by key."""

    @abstractmethod
    async def get_url(self, key: str) -> str:
        """Return public/presigned URL for the key."""

    async def delete(self, key: str) -> None:
        """Delete data by key when provider supports it."""

    async def close(self) -> None:
        """Release resources."""

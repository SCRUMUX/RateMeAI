from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def analyze_image(self, image_bytes: bytes, prompt: str) -> dict:
        """Send image + prompt to vision model, return parsed JSON."""

    @abstractmethod
    async def generate_text(self, prompt: str) -> str:
        """Generate text completion."""

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

    async def close(self) -> None:
        """Release resources."""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def analyze_image(self, image_bytes: bytes, prompt: str) -> dict:
        """Send image + prompt to vision model, return parsed JSON."""

    @abstractmethod
    async def generate_text(self, prompt: str) -> str:
        """Generate text completion."""


class ImageGenProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        """Generate image from prompt, optionally using reference image for identity preservation."""


class StorageProvider(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes) -> str:
        """Upload data, return access URL."""

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download data by key."""

    @abstractmethod
    async def get_url(self, key: str) -> str:
        """Return public/presigned URL for the key."""

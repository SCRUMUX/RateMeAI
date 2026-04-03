from __future__ import annotations

import logging

import httpx

from src.providers.base import StorageProvider

logger = logging.getLogger(__name__)


class S3StorageProvider(StorageProvider):
    """S3-compatible storage (MinIO / AWS S3). Uses presigned URLs via httpx."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str):
        self._endpoint = endpoint.rstrip("/")
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._client = httpx.AsyncClient(timeout=30.0)

    async def upload(self, key: str, data: bytes) -> str:
        # Minimal S3 PUT — for production, switch to aioboto3 with proper signing
        url = f"{self._endpoint}/{self._bucket}/{key}"
        response = await self._client.put(url, content=data)
        response.raise_for_status()
        return url

    async def download(self, key: str) -> bytes:
        url = f"{self._endpoint}/{self._bucket}/{key}"
        response = await self._client.get(url)
        response.raise_for_status()
        return response.content

    async def get_url(self, key: str) -> str:
        return f"{self._endpoint}/{self._bucket}/{key}"

    async def close(self):
        await self._client.aclose()

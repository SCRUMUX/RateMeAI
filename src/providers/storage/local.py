from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote
import contextlib

import aiofiles
import httpx

from src.providers.base import StorageProvider

logger = logging.getLogger(__name__)


class LocalStorageProvider(StorageProvider):
    def __init__(
        self,
        base_path: str,
        public_base_url: str,
        *,
        http_fallback_base: str | None = None,
    ):
        self._base = Path(base_path).resolve()
        self._base.mkdir(parents=True, exist_ok=True)
        self._public_base = public_base_url.rstrip("/")
        self._http_fallback_base = (http_fallback_base or "").rstrip("/") or None
        self._http_client: httpx.AsyncClient | None = None

    @property
    def base_path(self) -> Path:
        return self._base

    async def upload(self, key: str, data: bytes) -> str:
        path = self._base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return key

    async def download(self, key: str) -> bytes:
        path = self._base / key
        if path.exists():
            async with aiofiles.open(path, "rb") as f:
                return await f.read()

        if self._http_fallback_base:
            enc = quote(key, safe="/")
            url = f"{self._http_fallback_base}/storage/{enc}"
            try:
                if self._http_client is None:
                    self._http_client = httpx.AsyncClient(timeout=120.0, follow_redirects=True)
                resp = await self._http_client.get(url)
                resp.raise_for_status()
                data = resp.content
                logger.info("Storage download via HTTP fallback: %s", key)
                return data
            except Exception:
                logger.exception("Storage HTTP fallback failed for key=%s url=%s", key, url)

        raise FileNotFoundError(f"File not found: {key}")

    async def get_url(self, key: str) -> str:
        enc = key.replace(" ", "%20")
        return f"{self._public_base}/storage/{enc}"

    async def delete(self, key: str) -> None:
        path = self._base / key
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        parent = path.parent
        while parent != self._base and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def get_absolute_path(self, key: str) -> str:
        return str(self._base / key)

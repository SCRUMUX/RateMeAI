from __future__ import annotations

import os
from pathlib import Path

import aiofiles

from src.providers.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(self, base_path: str):
        self._base = Path(base_path).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

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
        if not path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def get_url(self, key: str) -> str:
        return f"/storage/{key}"

    def get_absolute_path(self, key: str) -> str:
        return str(self._base / key)

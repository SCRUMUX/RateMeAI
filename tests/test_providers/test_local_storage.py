import tempfile

import pytest

from src.providers.storage.local import LocalStorageProvider


@pytest.mark.asyncio
async def test_local_storage_key_and_url():
    with tempfile.TemporaryDirectory() as tmp:
        s = LocalStorageProvider(tmp, "http://api.test")
        key = await s.upload("folder/file.bin", b"hello")
        assert key == "folder/file.bin"
        data = await s.download(key)
        assert data == b"hello"
        url = await s.get_url(key)
        assert url == "http://api.test/storage/folder/file.bin"

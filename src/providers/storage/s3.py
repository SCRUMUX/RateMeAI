from __future__ import annotations

import logging
from urllib.parse import quote

import aioboto3
from botocore.config import Config as BotoConfig

from src.providers.base import StorageProvider

logger = logging.getLogger(__name__)


class S3StorageProvider(StorageProvider):
    """S3-compatible storage with SigV4 signing (AWS, MinIO, R2, Railway buckets)."""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "auto",
        public_base_url: str | None = None,
        presign_ttl_seconds: int = 3600,
    ):
        self._endpoint = endpoint_url.rstrip("/")
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._region = region
        self._public_base = public_base_url.rstrip("/") if public_base_url else None
        self._presign_ttl = presign_ttl_seconds
        self._session = aioboto3.Session()
        addressing = "path" if "localhost" in endpoint_url or "127.0.0.1" in endpoint_url else "auto"
        self._config = BotoConfig(signature_version="s3v4", s3={"addressing_style": addressing})

    def _client_ctx(self):
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=self._config,
        )

    async def upload(self, key: str, data: bytes) -> str:
        async with self._client_ctx() as client:
            await client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    async def download(self, key: str) -> bytes:
        async with self._client_ctx() as client:
            resp = await client.get_object(Bucket=self._bucket, Key=key)
            body = resp["Body"]
            return await body.read()

    async def get_url(self, key: str) -> str:
        if self._public_base:
            enc = quote(key, safe="/")
            return f"{self._public_base}/{enc}"

        async with self._client_ctx() as client:
            # aiobotocore exposes sync presign on the client
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=self._presign_ttl,
            )

    async def close(self):
        pass

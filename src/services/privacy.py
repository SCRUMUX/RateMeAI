"""Privacy layer: EXIF/ICC strip, normalize, in-memory handoff to pipeline.

The layer replaces the previous ``storage.upload("inputs/{user}/{uuid}.jpg")``
path. Its invariants:

1. Original bytes are **never** persisted to durable storage (S3 / local
   filesystem). They live only in process memory and a short-lived Redis
   stash (default 15 minutes) until the worker picks them up.
2. All EXIF / ICC / XMP metadata is explicitly stripped during normalize.
3. No biometric feature vectors (face embeddings, ArcFace descriptors)
   are computed, cached or persisted anywhere. Identity preservation is
   verified via a stateless VLM check at quality-gate time (see
   src/services/quality_gates.py), which operates on two in-memory
   images in a single LLM call and retains no per-user state.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

from redis.asyncio import Redis

from src.config import settings
from src.utils.image import validate_and_normalize
from src.utils.redis_keys import task_input_cache_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SanitizedImage:
    """Output of PrivacyLayer.sanitize_and_normalize."""

    bytes_: bytes
    meta: dict

    @property
    def size(self) -> int:
        return len(self.bytes_)


class PrivacyLayer:
    """Stateless helpers + Redis I/O for the sanitized image lifecycle."""

    def __init__(self, redis: Redis | None = None):
        self._redis = redis

    @staticmethod
    def sanitize_and_normalize(raw: bytes) -> SanitizedImage:
        """Strip EXIF/ICC, normalize resolution, re-encode as clean JPEG.

        ``validate_and_normalize`` is the single source of truth for both the
        quality checks and the metadata scrubbing; we wrap it so callers get
        a single name to audit against.
        """
        clean_bytes, meta = validate_and_normalize(raw)
        return SanitizedImage(bytes_=clean_bytes, meta=meta)

    async def stash_for_pipeline(
        self,
        img: SanitizedImage,
        task_id: str,
        market_id: str | None = None,
        ttl: int | None = None,
    ) -> str | None:
        """Short-lived Redis handoff to the worker. Returns the key or None."""
        if self._redis is None:
            return None
        key = task_input_cache_key(task_id, market_id)
        payload = base64.b64encode(img.bytes_).decode("ascii")
        effective_ttl = ttl if ttl is not None else settings.privacy_stash_ttl_seconds
        try:
            await self._redis.set(key, payload, ex=effective_ttl)
        except Exception:
            logger.warning("privacy.stash_failed", exc_info=True)
            return None
        return key

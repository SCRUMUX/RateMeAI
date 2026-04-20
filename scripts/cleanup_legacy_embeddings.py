"""One-shot cleanup of legacy Redis biometric artefacts.

Background: prior to the v1.10 privacy overhaul the system persisted
ArcFace face embeddings in Redis under keys of the form
``ratemeai:embedding:*`` for up to 72 hours. After the overhaul this
class of data is no longer produced, but any embeddings that were
cached before the deploy will remain until their TTL expires.

This script force-deletes all such keys immediately after deploy so the
Redis instance contains *zero* biometric artefacts, regardless of TTL.

Usage:
    python scripts/cleanup_legacy_embeddings.py [--redis-url URL] [--dry-run]

Safe to run multiple times; idempotent.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

logger = logging.getLogger("cleanup_legacy_embeddings")


async def _cleanup(redis_url: str, dry_run: bool) -> int:
    import redis.asyncio as redis_async

    client = redis_async.from_url(redis_url, decode_responses=True)
    try:
        patterns = (
            "ratemeai:embedding:*",
            "ratemeai:embedding:*:*",
        )
        deleted = 0
        for pattern in patterns:
            cursor = 0
            while True:
                cursor, batch = await client.scan(cursor=cursor, match=pattern, count=500)
                if batch:
                    if dry_run:
                        for k in batch:
                            logger.info("[dry-run] would DEL %s", k)
                    else:
                        await client.delete(*batch)
                    deleted += len(batch)
                if cursor == 0:
                    break
        logger.info(
            "cleanup_legacy_embeddings: %s %d key(s)",
            "would delete" if dry_run else "deleted",
            deleted,
        )
        return deleted
    finally:
        await client.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        help="Redis URL (defaults to $REDIS_URL or localhost).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only log matching keys, do not delete.",
    )
    args = parser.parse_args()
    asyncio.run(_cleanup(args.redis_url, args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())

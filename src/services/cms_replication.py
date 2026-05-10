"""CMS replication client + receiver helpers (Variant B).

Architecture:

* Editor (Railway) — every successful ``save_landing_content()`` from
  the admin API kicks off a background HTTP push to every URL in
  ``settings.resolved_cms_follower_urls``.
* Follower (RU edge) — exposes ``POST /internal/cms/replicate`` that
  verifies the HMAC signature, validates the payload shape and writes
  it through ``landing_store.save_landing_content()``.
* Safety net — followers also run an hourly ARQ cron
  (``cms_safety_pull_cron`` in :mod:`src.workers.tasks`) that pulls a
  full snapshot from the editor and rewrites local JSON whenever the
  hash drifts.

The HMAC signature is ``HMAC-SHA256(secret, raw_body_bytes)``,
hex-encoded, sent in the ``X-Replication-Signature`` header. The body
is JSON with the contract:

    {
        "market": "ru",
        "content_hash": "<sha256>",
        "payload": {"pages": {...}}
    }

``content_hash`` lets the receiver skip writes when the local file
already matches (avoids spurious cache invalidations and disk churn
when both sides are in sync).
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
from hashlib import sha256
from typing import Any

import httpx

from src.config import settings
from src.services import landing_store

logger = logging.getLogger(__name__)

REPLICATE_PATH = "/internal/cms/replicate"
SNAPSHOT_PATH = "/internal/cms/snapshot"
SIGNATURE_HEADER = "X-Replication-Signature"

# Push & pull share the same client knobs. Single attempt at the
# transport layer; retries are handled by the ARQ task wrapper so we
# do not re-fire on a follower that's intentionally returning 4xx.
_PUSH_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
_PULL_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)


def _shared_secret() -> str:
    """Return the configured replication secret (or empty string).

    Centralised so callers do not depend on the env-var fallback chain
    in ``settings.resolved_cms_replication_secret`` directly.
    """
    return settings.resolved_cms_replication_secret


def sign_payload(secret: str, body: bytes) -> str:
    """Compute the hex-encoded HMAC-SHA256 signature for ``body``."""
    return hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Constant-time signature check used by the follower receiver."""
    if not secret or not signature:
        return False
    expected = sign_payload(secret, body)
    return hmac.compare_digest(expected, signature.strip())


def build_payload(market: str, document: dict[str, Any]) -> dict[str, Any]:
    """Bundle a CMS document with its market id and stable hash."""
    return {
        "market": market,
        "content_hash": landing_store.content_hash(document),
        "payload": document,
    }


def encode_payload(payload: dict[str, Any]) -> bytes:
    """Serialise a payload deterministically so push & pull hash matches."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


async def _push_to_follower(
    client: httpx.AsyncClient,
    follower_url: str,
    payload: dict[str, Any],
    secret: str,
) -> bool:
    """Send a single replication push. Returns True on 2xx, False otherwise."""
    body = encode_payload(payload)
    signature = sign_payload(secret, body)
    url = follower_url.rstrip("/") + REPLICATE_PATH
    try:
        resp = await client.post(
            url,
            content=body,
            headers={
                SIGNATURE_HEADER: signature,
                "Content-Type": "application/json",
            },
        )
    except Exception as exc:  # pragma: no cover — network errors logged, not raised
        logger.warning("cms_replication: push to %s failed: %s", url, exc)
        return False
    if 200 <= resp.status_code < 300:
        logger.info(
            "cms_replication: push ok url=%s status=%s",
            url,
            resp.status_code,
        )
        return True
    body_text = (resp.text or "")[:200]
    logger.warning(
        "cms_replication: push rejected url=%s status=%s body=%s",
        url,
        resp.status_code,
        body_text,
    )
    return False


async def push_to_followers(market: str, document: dict[str, Any]) -> dict[str, bool]:
    """Push ``document`` to every configured follower URL.

    Returns ``{follower_url: success}``. Never raises — caller decides
    what to do with partial failures (typically log & rely on the
    hourly safety-pull on the follower).
    """
    if not settings.is_cms_editor:
        logger.debug("cms_replication: skip push, role=%s", settings.resolved_cms_role)
        return {}
    followers = settings.resolved_cms_follower_urls
    if not followers:
        return {}
    secret = _shared_secret()
    if not secret:
        logger.error(
            "cms_replication: no shared secret configured — refusing to push"
        )
        return {url: False for url in followers}
    payload = build_payload(market, document)
    results: dict[str, bool] = {}
    async with httpx.AsyncClient(timeout=_PUSH_TIMEOUT) as client:
        coros = [_push_to_follower(client, url, payload, secret) for url in followers]
        for url, ok in zip(followers, await asyncio.gather(*coros)):
            results[url] = ok
    return results


def schedule_replication(market: str, document: dict[str, Any]) -> None:
    """Fire-and-forget replication trigger for the editor admin path.

    We intentionally use a detached ``asyncio.create_task`` rather than
    blocking the admin response — landing pages tolerate a few seconds
    of staleness, and the follower's hourly safety-pull catches anything
    we drop here. When called from a non-async context (tests) the call
    silently no-ops.
    """
    if not settings.is_cms_editor:
        return
    if not settings.resolved_cms_follower_urls:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (sync admin handler in tests). Skip — the
        # safety-pull cron on the follower will eventually reconcile.
        logger.debug("cms_replication: no running loop, skipping push")
        return
    task = loop.create_task(push_to_followers(market, document))
    # Keep a strong reference until the task completes — otherwise the
    # task may be garbage-collected mid-flight on Python 3.11+.
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


async def fetch_snapshot_from_master(market: str) -> dict[str, Any] | None:
    """Pull a CMS snapshot for ``market`` from the editor (follower side)."""
    base = (settings.cms_master_url or "").strip().rstrip("/")
    if not base:
        logger.debug("cms_replication: no master url, snapshot skipped")
        return None
    secret = _shared_secret()
    if not secret:
        logger.error(
            "cms_replication: no shared secret on follower — cannot pull snapshot"
        )
        return None
    url = f"{base}{SNAPSHOT_PATH}?market={market}"
    # Pull authenticates with the same HMAC over the URL bytes; this is
    # cheaper than POSTing a body just to authenticate a GET.
    signature = sign_payload(secret, url.encode("utf-8"))
    try:
        async with httpx.AsyncClient(timeout=_PULL_TIMEOUT) as client:
            resp = await client.get(url, headers={SIGNATURE_HEADER: signature})
    except Exception as exc:  # pragma: no cover — network errors are non-fatal
        logger.warning("cms_replication: snapshot pull failed: %s", exc)
        return None
    if resp.status_code != 200:
        logger.warning(
            "cms_replication: snapshot pull rejected status=%s body=%s",
            resp.status_code,
            (resp.text or "")[:200],
        )
        return None
    try:
        data = resp.json()
    except Exception:
        logger.exception("cms_replication: snapshot pull returned non-JSON")
        return None
    if not isinstance(data, dict):
        logger.warning("cms_replication: snapshot payload is not a dict")
        return None
    return data


def apply_snapshot(market: str, payload: dict[str, Any]) -> bool:
    """Persist a snapshot to local disk. Returns True if disk was rewritten."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    document = payload
    # Accept both a raw document ({"pages": {...}}) and an envelope
    # ({"payload": {...}, "content_hash": "...", "market": "ru"}).
    if "pages" not in document and isinstance(document.get("payload"), dict):
        document = document["payload"]
    if "pages" not in document or not isinstance(document.get("pages"), dict):
        raise ValueError("payload missing 'pages' map")
    current = landing_store.load_landing_content_fresh(market)
    if landing_store.content_hash(current) == landing_store.content_hash(document):
        logger.debug("cms_replication: snapshot matches local content, no write")
        return False
    landing_store.save_landing_content(document, market=market)
    logger.info(
        "cms_replication: applied snapshot market=%s pages=%d",
        market,
        len(document.get("pages") or {}),
    )
    return True

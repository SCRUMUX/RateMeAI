"""Tests for ``src.services.cms_replication`` and the
``/internal/cms/...`` receivers (Variant B).

Replication is a small surface but a security-critical one — a missing
HMAC check would let any RU-edge-egress IP rewrite the entire landing
CMS. We pin both the helper layer (sign / verify / apply_snapshot) and
the FastAPI handlers that call it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.api import internal_cms
from src.config import settings
from src.services import cms_replication, landing_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def landing_disk(tmp_path: Path, monkeypatch):
    """Redirect landing storage to ``tmp_path`` and seed a known doc."""
    fake_ru = tmp_path / "landing_content.json"
    fake_ru.write_text(
        json.dumps(
            {
                "pages": {
                    "home": {
                        "blocks": [
                            {
                                "id": "footer",
                                "type": "footer",
                                "enabled": True,
                                "data": {"copyright": "© seed"},
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(landing_store, "LANDING_PATH", fake_ru)
    landing_store.invalidate_cache()
    yield tmp_path
    landing_store.invalidate_cache()


@pytest.fixture
def replication_secret(monkeypatch):
    secret = "test-replication-secret-please-rotate"
    monkeypatch.setattr(settings, "cms_replication_secret", secret, raising=False)
    monkeypatch.setattr(settings, "internal_api_key", "fallback-only", raising=False)
    return secret


# ---------------------------------------------------------------------------
# HMAC helpers
# ---------------------------------------------------------------------------


def test_sign_and_verify_roundtrip():
    body = b'{"market":"ru","content_hash":"abc","payload":{"pages":{}}}'
    sig = cms_replication.sign_payload("secret", body)
    assert cms_replication.verify_signature("secret", body, sig) is True


def test_verify_rejects_wrong_secret():
    body = b"hello"
    sig = cms_replication.sign_payload("secret-A", body)
    assert cms_replication.verify_signature("secret-B", body, sig) is False


def test_verify_rejects_tampered_body():
    body = b"hello"
    sig = cms_replication.sign_payload("secret", body)
    assert cms_replication.verify_signature("secret", b"hello!", sig) is False


def test_verify_rejects_empty_signature_or_secret():
    assert cms_replication.verify_signature("", b"x", "deadbeef") is False
    assert cms_replication.verify_signature("secret", b"x", "") is False


def test_build_payload_includes_market_and_hash(landing_disk):
    document = landing_store.load_landing_content("ru")
    payload = cms_replication.build_payload("ru", document)
    assert payload["market"] == "ru"
    assert payload["content_hash"] == landing_store.content_hash(document)
    assert payload["payload"] is document


# ---------------------------------------------------------------------------
# apply_snapshot
# ---------------------------------------------------------------------------


def test_apply_snapshot_writes_when_hash_drifts(landing_disk):
    new_doc = {
        "pages": {
            "home": {
                "blocks": [
                    {
                        "id": "footer",
                        "type": "footer",
                        "enabled": True,
                        "data": {"copyright": "© replicated"},
                    }
                ]
            }
        }
    }
    rewritten = cms_replication.apply_snapshot("ru", new_doc)
    assert rewritten is True
    persisted = json.loads(
        (landing_disk / "landing_content.json").read_text(encoding="utf-8")
    )
    assert persisted["pages"]["home"]["blocks"][0]["data"]["copyright"] == "© replicated"


def test_apply_snapshot_noop_when_hash_matches(landing_disk):
    current = landing_store.load_landing_content("ru")
    rewritten = cms_replication.apply_snapshot("ru", current)
    assert rewritten is False


def test_apply_snapshot_accepts_envelope(landing_disk):
    document = {
        "pages": {
            "home": {
                "blocks": [
                    {
                        "id": "footer",
                        "type": "footer",
                        "enabled": True,
                        "data": {"copyright": "© envelope"},
                    }
                ]
            }
        }
    }
    envelope = cms_replication.build_payload("ru", document)
    rewritten = cms_replication.apply_snapshot("ru", envelope)
    assert rewritten is True


def test_apply_snapshot_rejects_missing_pages(landing_disk):
    with pytest.raises(ValueError):
        cms_replication.apply_snapshot("ru", {"foo": "bar"})


# ---------------------------------------------------------------------------
# /internal/cms/replicate
# ---------------------------------------------------------------------------


def _build_request(body: bytes, query: str = "") -> Request:
    """Minimal Starlette Request that returns ``body`` from .body() / .json()."""
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/internal/cms/replicate",
        "headers": [],
        "query_string": query.encode("utf-8"),
    }
    received = {"sent": False}

    async def receive():
        if received["sent"]:
            return {"type": "http.disconnect"}
        received["sent"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_replicate_rejected_when_role_not_follower(
    landing_disk, replication_secret, monkeypatch
):
    monkeypatch.setattr(settings, "cms_role", "editor", raising=False)
    body = cms_replication.encode_payload(
        cms_replication.build_payload(
            "ru", landing_store.load_landing_content("ru")
        )
    )
    sig = cms_replication.sign_payload(replication_secret, body)
    request = _build_request(body)
    with pytest.raises(HTTPException) as exc:
        await internal_cms.replicate(request, x_replication_signature=sig)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_replicate_rejected_with_bad_signature(
    landing_disk, replication_secret, monkeypatch
):
    monkeypatch.setattr(settings, "cms_role", "follower", raising=False)
    body = cms_replication.encode_payload(
        cms_replication.build_payload(
            "ru", landing_store.load_landing_content("ru")
        )
    )
    request = _build_request(body)
    with pytest.raises(HTTPException) as exc:
        await internal_cms.replicate(request, x_replication_signature="cafef00d")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_replicate_writes_payload_on_valid_signature(
    landing_disk, replication_secret, monkeypatch
):
    monkeypatch.setattr(settings, "cms_role", "follower", raising=False)
    new_document = {
        "pages": {
            "home": {
                "blocks": [
                    {
                        "id": "footer",
                        "type": "footer",
                        "enabled": True,
                        "data": {"copyright": "© via webhook"},
                    }
                ]
            }
        }
    }
    payload = cms_replication.build_payload("ru", new_document)
    body = cms_replication.encode_payload(payload)
    sig = cms_replication.sign_payload(replication_secret, body)

    request = _build_request(body)
    result = await internal_cms.replicate(request, x_replication_signature=sig)
    assert result["status"] == "ok"
    assert result["market"] == "ru"
    assert result["rewritten"] is True

    persisted = json.loads(
        (landing_disk / "landing_content.json").read_text(encoding="utf-8")
    )
    assert (
        persisted["pages"]["home"]["blocks"][0]["data"]["copyright"]
        == "© via webhook"
    )


@pytest.mark.asyncio
async def test_replicate_rejects_unknown_market(
    landing_disk, replication_secret, monkeypatch
):
    monkeypatch.setattr(settings, "cms_role", "follower", raising=False)
    payload = {
        "market": "xx",
        "content_hash": "abc",
        "payload": {"pages": {}},
    }
    body = cms_replication.encode_payload(payload)
    sig = cms_replication.sign_payload(replication_secret, body)
    request = _build_request(body)
    with pytest.raises(HTTPException) as exc:
        await internal_cms.replicate(request, x_replication_signature=sig)
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# /internal/cms/snapshot
# ---------------------------------------------------------------------------


def _build_get_request(path: str) -> Request:
    """Build a minimal Starlette GET Request with full URL preserved."""
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": path.split("?", 1)[0],
        "headers": [(b"host", b"testserver")],
        "query_string": (path.split("?", 1)[1] if "?" in path else "").encode("utf-8"),
        "scheme": "https",
        "server": ("testserver", 443),
        "root_path": "",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_snapshot_requires_editor_role(
    landing_disk, replication_secret, monkeypatch
):
    monkeypatch.setattr(settings, "cms_role", "follower", raising=False)
    request = _build_get_request("/internal/cms/snapshot?market=ru")
    sig = cms_replication.sign_payload(replication_secret, str(request.url).encode())
    with pytest.raises(HTTPException) as exc:
        await internal_cms.snapshot(request, market="ru", x_replication_signature=sig)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_snapshot_returns_signed_payload_for_editor(
    landing_disk, replication_secret, monkeypatch
):
    monkeypatch.setattr(settings, "cms_role", "editor", raising=False)
    request = _build_get_request("/internal/cms/snapshot?market=ru")
    sig = cms_replication.sign_payload(replication_secret, str(request.url).encode())
    result = await internal_cms.snapshot(
        request, market="ru", x_replication_signature=sig
    )
    assert result["market"] == "ru"
    assert "content_hash" in result
    assert "payload" in result and "pages" in result["payload"]


@pytest.mark.asyncio
async def test_snapshot_rejects_bad_signature(
    landing_disk, replication_secret, monkeypatch
):
    monkeypatch.setattr(settings, "cms_role", "editor", raising=False)
    request = _build_get_request("/internal/cms/snapshot?market=ru")
    with pytest.raises(HTTPException) as exc:
        await internal_cms.snapshot(
            request, market="ru", x_replication_signature="not-a-real-sig"
        )
    assert exc.value.status_code == 403

"""PII-firewall golden tests for the edge → primary remote-AI hop.

These tests are the structural counterpart to ``model_config =
ConfigDict(extra="forbid")`` on ``RemoteAnalysisRequest`` in
[src/api/v1/internal.py](src/api/v1/internal.py): on the *primary*
side any unknown field returns HTTP 422; on the *edge* side this
suite ensures the client itself never tries to send one.

Two assertions:

1. **Whitelist** — the JSON keys submitted by ``submit_task`` are
   exactly the set of edge → primary fields the architecture allows.
   Anyone who adds a new keyword arg must (a) extend the whitelist,
   (b) re-justify why the new field is not PII.

2. **PII blacklist** — the serialized JSON body must not contain
   regexp-matchable identifiers (``email``, ``phone``, ``telegram``,
   first/last names, ``@gmail|@yandex|@vk``). This is a coarse
   structural check, but it catches the most likely accidents:
   someone passing ``user.email`` or ``user.first_name`` into the
   payload by mistake.

The test does **not** hit a real Primary — it intercepts
``httpx.AsyncClient.post`` and inspects the JSON body in-memory.
"""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.config import settings


# Exactly the set of keys ``submit_task`` is allowed to send.
# Keep in sync with ``RemoteAnalysisRequest`` (src/api/v1/internal.py).
ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "image_b64",
        "mode",
        "style",
        "profession",
        "enhancement_level",
        "pre_analysis_id",
        "variant_id",
        "edge_task_id",
        "market_id",
        "scenario_slug",
        "scenario_type",
        "entry_mode",
        "trace_id",
        "policy_flags",
        "artifact_refs",
        "image_model",
        "image_quality",
        "tier",
        "framing",
        "input_hints",
        "source",
        # Composition Safety Layer (Phase 3) — advanced-override flag.
        # Edge propagates the user's explicit consent to bypass the
        # CSL hard-stop; primary re-validates the override against its
        # own ``composition_safety_advanced_override`` flag.
        "skip_composition_safety",
    }
)

# Regex patterns that should never appear in the serialized payload.
# Each row: (display_name, compiled regex).
PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email_attr", re.compile(r'"\s*email\s*"', re.I)),
    ("phone_attr", re.compile(r'"\s*phone(_number)?\s*"', re.I)),
    ("telegram_id_attr", re.compile(r'"\s*telegram_id\s*"', re.I)),
    ("telegram_username_attr", re.compile(r'"\s*telegram_username\s*"', re.I)),
    ("first_name_attr", re.compile(r'"\s*first_name\s*"', re.I)),
    ("last_name_attr", re.compile(r'"\s*last_name\s*"', re.I)),
    ("display_name_attr", re.compile(r'"\s*display_name\s*"', re.I)),
    ("user_id_attr", re.compile(r'"\s*user_id\s*"', re.I)),
    ("ip_attr", re.compile(r'"\s*(remote_ip|ip_address|client_ip)\s*"', re.I)),
    ("language_code_attr", re.compile(r'"\s*language_code\s*"', re.I)),
    # Common email-shaped values (catches a stringified email value
    # even if the key is innocent).
    ("email_value", re.compile(r"[A-Za-z0-9._%+\-]+@(gmail|yandex|vk|mail|outlook)\.[A-Za-z]{2,}", re.I)),
)


@pytest.fixture
def _ai_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure RemoteAIService to think it's a real edge."""
    monkeypatch.setattr(
        settings, "remote_ai_backend_url", "https://primary.example.com", raising=False
    )
    monkeypatch.setattr(settings, "internal_api_key", "test-internal-key", raising=False)


@pytest.fixture
def captured_payloads() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def patched_post(captured_payloads: list[dict[str, Any]]):
    """Intercept httpx POST, capture the JSON body, return a 200."""
    async def _fake_post(self, url: str, **kwargs):  # noqa: ANN001
        body = kwargs.get("json") or {}
        captured_payloads.append(body)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"remote_task_id": "task-uuid-fake"})
        resp.text = json.dumps({"remote_task_id": "task-uuid-fake"})
        resp.status_code = 200
        return resp

    with patch("httpx.AsyncClient.post", new=_fake_post):
        yield


@pytest.mark.asyncio
async def test_submit_task_payload_keys_are_whitelisted(
    _ai_settings,
    captured_payloads: list[dict[str, Any]],
    patched_post,
) -> None:
    """Whitelist firewall: every key in the payload is an architectural ally."""
    from src.services.remote_ai import RemoteAIService

    svc = RemoteAIService()
    try:
        await svc.submit_task(
            image_b64="ZmFrZQ==",
            mode="rating",
            style="cinematic",
            profession="actor",
            enhancement_level=1,
            pre_analysis_id="pa-1",
            variant_id="v-1",
            edge_task_id="edge-task-1",
            market_id="ru",
            scenario_slug="visa-photo",
            scenario_type="document",
            entry_mode="document",
            trace_id="trace-1",
            policy_flags={"consent_data_processing": True, "consent_ai_transfer": True},
            artifact_refs={"original": "redis://stash/abc"},
            image_model="gpt_image_2",
            image_quality="low",
            framing="portrait",
            input_hints={"lighting": "soft"},
            source="telegram_bot",
        )
    finally:
        await svc.close()

    assert captured_payloads, "submit_task did not call httpx.post"
    payload = captured_payloads[-1]
    actual_keys = set(payload.keys())
    extra = actual_keys - ALLOWED_KEYS
    assert not extra, (
        f"submit_task is sending UNKNOWN keys to primary: {sorted(extra)}. "
        f"Either add them to ALLOWED_KEYS *and* extend the "
        f"RemoteAnalysisRequest schema, or revert the edge change."
    )
    # Soft check: payload should contain at least the non-string-empty
    # arguments we passed. We don't enforce all 20 keys since some are
    # optional in the future.
    assert "image_b64" in actual_keys
    assert "mode" in actual_keys


@pytest.mark.asyncio
async def test_submit_task_payload_has_no_pii(
    _ai_settings,
    captured_payloads: list[dict[str, Any]],
    patched_post,
) -> None:
    """Blacklist firewall: no PII attribute names or email-shaped values."""
    from src.services.remote_ai import RemoteAIService

    svc = RemoteAIService()
    try:
        await svc.submit_task(
            image_b64="ZmFrZQ==",
            mode="rating",
            edge_task_id="edge-task-pii-check",
            market_id="ru",
            trace_id="trace-pii-check",
            policy_flags={"consent_data_processing": True, "consent_ai_transfer": True},
        )
    finally:
        await svc.close()

    assert captured_payloads
    body = json.dumps(captured_payloads[-1])
    for name, pattern in PII_PATTERNS:
        match = pattern.search(body)
        assert not match, (
            f"PII guard tripped: pattern {name!r} matched at {match.span() if match else '?'} "
            f"in payload — this means submit_task is leaking PII from the edge "
            f"to the primary backend. Body fragment: {body[:280]}…"
        )


@pytest.mark.asyncio
async def test_submit_task_policy_flags_are_ephemeral(
    _ai_settings,
    captured_payloads: list[dict[str, Any]],
    patched_post,
) -> None:
    """Architectural guarantee: edge requests carry the ephemeral contract."""
    from src.services.remote_ai import RemoteAIService

    svc = RemoteAIService()
    try:
        await svc.submit_task(
            image_b64="ZmFrZQ==",
            mode="rating",
            edge_task_id="edge-task-policy",
            market_id="ru",
            trace_id="trace-policy",
            policy_flags={"consent_data_processing": True, "consent_ai_transfer": True},
        )
    finally:
        await svc.close()

    assert captured_payloads
    flags = captured_payloads[-1]["policy_flags"]
    assert flags.get("delete_after_process") is True, (
        "edge request must mark its data as delete-after-process; without this "
        "the primary worker may keep regional photos in storage / Redis longer "
        "than 152-ФЗ allows."
    )
    assert flags.get("retention_policy") == "ephemeral"
    assert flags.get("data_class") == "regional_photo"

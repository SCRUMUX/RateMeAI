"""Edge → primary tier forwarding (v1.78).

Premium on ailookstudio.ru must send ``tier`` in the remote-AI JSON payload
so primary ``process_analysis_remote`` does not rebuild ctx as standard.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.config import settings


@pytest.fixture
def _ai_settings(monkeypatch):
    monkeypatch.setattr(
        settings, "remote_ai_backend_url", "https://primary.example.com", raising=False
    )
    monkeypatch.setattr(settings, "internal_api_key", "test-internal-key", raising=False)


@pytest.fixture
def captured_payloads() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def patched_post(captured_payloads: list[dict[str, Any]]):
    async def _fake_post(self, url: str, **kwargs):  # noqa: ANN001
        captured_payloads.append(kwargs.get("json") or {})
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"remote_task_id": "task-uuid-fake"})
        resp.text = json.dumps({"remote_task_id": "task-uuid-fake"})
        resp.status_code = 200
        return resp

    with patch("httpx.AsyncClient.post", new=_fake_post):
        yield


@pytest.mark.asyncio
async def test_submit_task_forwards_tier_premium(
    _ai_settings,
    captured_payloads: list[dict[str, Any]],
    patched_post,
) -> None:
    from src.services.remote_ai import RemoteAIService

    svc = RemoteAIService()
    try:
        await svc.submit_task(
            image_b64="ZmFrZQ==",
            mode="dating",
            style="paris_eiffel",
            tier="premium",
            image_quality="high",
            image_model="gpt_image_2",
        )
    finally:
        await svc.close()

    assert captured_payloads
    payload = captured_payloads[-1]
    assert payload.get("tier") == "premium"
    assert payload.get("image_quality") == "high"

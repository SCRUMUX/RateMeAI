"""Verify that OpenRouterLLM's tenacity retry policy covers the exceptions we
care about in production (B1 fix).

Prior to this, the retry decorator only matched ``httpx.HTTPStatusError`` and
``httpx.ConnectError`` — a ``ReadTimeout`` from a slow OpenRouter response
killed the task on the first attempt, and a 4xx that is terminal (401/403/404)
pointlessly retried three times, eating the ARQ ``job_timeout`` budget.
"""

from __future__ import annotations

import httpx
import pytest
from tenacity import RetryError

from src.providers.llm.openrouter import (
    OpenRouterLLM,
    _is_retryable_openrouter,
)


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict | None = None):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = "fake"

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}",
                request=httpx.Request("POST", "http://x"),
                response=httpx.Response(self.status_code),
            )


# ---------------------------------------------------------------------------
# Unit-level: the classifier accepts/rejects the right exception shapes.
# ---------------------------------------------------------------------------


def test_classifier_retries_read_timeout():
    exc = httpx.ReadTimeout("slow", request=httpx.Request("POST", "http://x"))
    assert _is_retryable_openrouter(exc)


def test_classifier_retries_write_timeout():
    exc = httpx.WriteTimeout("slow", request=httpx.Request("POST", "http://x"))
    assert _is_retryable_openrouter(exc)


def test_classifier_retries_pool_timeout():
    exc = httpx.PoolTimeout("slow")
    assert _is_retryable_openrouter(exc)


def test_classifier_retries_connect_error():
    exc = httpx.ConnectError("down", request=httpx.Request("POST", "http://x"))
    assert _is_retryable_openrouter(exc)


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
def test_classifier_retries_transient_statuses(status):
    exc = httpx.HTTPStatusError(
        str(status),
        request=httpx.Request("POST", "http://x"),
        response=httpx.Response(status),
    )
    assert _is_retryable_openrouter(exc)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_classifier_does_not_retry_terminal_statuses(status):
    exc = httpx.HTTPStatusError(
        str(status),
        request=httpx.Request("POST", "http://x"),
        response=httpx.Response(status),
    )
    assert not _is_retryable_openrouter(exc)


def test_classifier_does_not_retry_generic_exception():
    assert not _is_retryable_openrouter(ValueError("json parse failed"))


# ---------------------------------------------------------------------------
# End-to-end: the tenacity decorator on analyze_image actually re-invokes on
# transient errors and stops fast on terminal ones.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_image_retries_read_timeout_then_succeeds(monkeypatch):
    llm = OpenRouterLLM(api_key="k", base_url="http://x", model="m")

    calls = {"n": 0}
    success_body = {
        "choices": [
            {"message": {"content": '{"ok": true}'}},
        ]
    }

    async def fake_post(url, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ReadTimeout("slow", request=httpx.Request("POST", url))
        return _FakeResponse(200, success_body)

    # Short-circuit tenacity's wait so the test runs instantly.
    monkeypatch.setattr(
        "src.providers.llm.openrouter.wait_exponential",
        lambda **_: lambda *_a, **_kw: 0,
    )
    monkeypatch.setattr(llm._client, "post", fake_post)

    # Bypass the AI-transfer guard for this unit test.
    monkeypatch.setattr(
        "src.providers.llm.openrouter.assert_external_transfer_allowed",
        lambda _: None,
    )

    # Use retry's sleep hook to avoid real wait between attempts.
    import tenacity

    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_a, **_k: None)

    res = await llm.analyze_image(b"x", "prompt")
    assert res == {"ok": True}
    assert calls["n"] == 3

    await llm.close()


@pytest.mark.asyncio
async def test_analyze_image_does_not_retry_on_401(monkeypatch):
    llm = OpenRouterLLM(api_key="k", base_url="http://x", model="m")

    calls = {"n": 0}

    async def fake_post(url, **kwargs):
        calls["n"] += 1
        return _FakeResponse(401)

    monkeypatch.setattr(llm._client, "post", fake_post)
    monkeypatch.setattr(
        "src.providers.llm.openrouter.assert_external_transfer_allowed",
        lambda _: None,
    )

    import tenacity

    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_a, **_k: None)

    with pytest.raises((httpx.HTTPStatusError, RetryError)):
        await llm.analyze_image(b"x", "prompt")

    # Critical: a terminal 401 must NOT burn all 3 attempts.
    assert calls["n"] == 1

    await llm.close()

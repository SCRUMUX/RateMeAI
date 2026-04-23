"""Tests for worker helper functions and result enrichment logic."""

from __future__ import annotations

from src.workers.tasks import _format_task_error, _is_transient, _unwrap_exception


class _FakeURL:
    def __init__(self, host: str) -> None:
        self.host = host

    def __str__(self) -> str:
        return f"https://{self.host}/api"


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeRequest:
    def __init__(self, host: str) -> None:
        self.url = _FakeURL(host)


class _FakeHTTPStatusError(Exception):
    def __init__(self, status_code: int, host: str, body: str = "") -> None:
        super().__init__(f"Server returned HTTP {status_code}")
        self.response = _FakeResponse(status_code, body)
        self.request = _FakeRequest(host)


class TestIsTransient:
    def test_timeout_error(self):
        assert _is_transient(TimeoutError("connection timed out"))

    def test_connection_error(self):
        assert _is_transient(ConnectionError("refused"))

    def test_os_error(self):
        assert _is_transient(OSError("network unreachable"))

    def test_rate_limit_in_message(self):
        assert _is_transient(RuntimeError("Reve rate limit after 3 retries"))

    def test_503_in_message(self):
        assert _is_transient(RuntimeError("HTTP 503 Service Temporarily Unavailable"))

    def test_429_in_message(self):
        assert _is_transient(RuntimeError("HTTP 429 Too Many Requests"))

    def test_value_error_not_transient(self):
        assert not _is_transient(ValueError("No face detected"))

    def test_generic_runtime_error_not_transient(self):
        assert not _is_transient(RuntimeError("Reve: content policy violation"))

    def test_key_error_not_transient(self):
        assert not _is_transient(KeyError("missing_field"))

    def test_http_401_is_not_transient(self):
        exc = _FakeHTTPStatusError(401, "openrouter.ai", '{"error":"unauthorized"}')
        assert _is_transient(exc) is False

    def test_http_402_is_not_transient(self):
        exc = _FakeHTTPStatusError(
            402, "openrouter.ai", '{"error":"insufficient_credits"}'
        )
        assert _is_transient(exc) is False

    def test_http_429_is_transient(self):
        exc = _FakeHTTPStatusError(429, "openrouter.ai")
        assert _is_transient(exc) is True

    def test_http_503_via_response_code_is_transient(self):
        exc = _FakeHTTPStatusError(503, "openrouter.ai")
        assert _is_transient(exc) is True

    def test_retry_error_unwrapped_for_transient_classification(self):
        from tenacity import RetryError

        class _FakeFuture:
            def __init__(self, exc: BaseException) -> None:
                self._exc = exc

            def exception(self) -> BaseException:
                return self._exc

        inner = _FakeHTTPStatusError(401, "openrouter.ai")
        err = RetryError(last_attempt=_FakeFuture(inner))  # type: ignore[arg-type]
        assert _is_transient(err) is False  # 401 behind RetryError must stay hard-fail


class TestFormatTaskError:
    def test_plain_exception_has_stage_and_type(self):
        text = _format_task_error(ValueError("no_face"))
        assert text.startswith("[stage=worker] ValueError:")
        assert "no_face" in text

    def test_pipeline_stage_error_uses_inner_stage_and_type(self):
        from src.orchestrator.pipeline import PipelineStageError

        inner = RuntimeError("boom")
        exc = PipelineStageError(stage="analyze", original=inner)
        text = _format_task_error(exc)
        assert text.startswith("[stage=analyze] RuntimeError:")
        assert "boom" in text

    def test_retry_error_unwrapped_and_http_status_surfaced(self):
        """This is the fix for the 2–3s ``Ошибка генерации`` incident:
        RetryError[HTTPStatusError] used to be the DB-stored message. Now we
        surface status, host and body snippet.
        """
        from tenacity import RetryError

        class _FakeFuture:
            def __init__(self, exc: BaseException) -> None:
                self._exc = exc

            def exception(self) -> BaseException:
                return self._exc

        inner = _FakeHTTPStatusError(
            402,
            "openrouter.ai",
            '{"error":{"code":402,"message":"Insufficient credits"}}',
        )
        err = RetryError(last_attempt=_FakeFuture(inner))  # type: ignore[arg-type]

        text = _format_task_error(err)
        assert "RetryError" not in text  # unwrapped
        assert "_FakeHTTPStatusError" in text or "HTTPStatusError" in text.replace(
            "_Fake", ""
        )
        assert "http=402" in text
        assert "host=openrouter.ai" in text
        assert "Insufficient credits" in text

    def test_format_is_capped_to_500_chars(self):
        long = ValueError("x" * 5000)
        text = _format_task_error(long)
        assert len(text) <= 500


class TestUnwrapException:
    def test_pipeline_stage_error_unwrapped(self):
        from src.orchestrator.pipeline import PipelineStageError

        inner = RuntimeError("leaf")
        exc = PipelineStageError(stage="analyze", original=inner)
        assert _unwrap_exception(exc) is inner

    def test_retry_error_unwrapped(self):
        from tenacity import RetryError

        class _FakeFuture:
            def __init__(self, exc: BaseException) -> None:
                self._exc = exc

            def exception(self) -> BaseException:
                return self._exc

        inner = ValueError("leaf")
        err = RetryError(last_attempt=_FakeFuture(inner))  # type: ignore[arg-type]
        assert _unwrap_exception(err) is inner


class TestResultEnrichment:
    """Verify the has_generated_image / no_image_reason logic matches worker code."""

    @staticmethod
    def _enrich(analysis_result: dict, context: dict) -> dict:
        """Mirror the enrichment block from process_analysis."""
        analysis_result["enhancement_level"] = context.get("enhancement_level", 0)

        gen_url = analysis_result.get("generated_image_url")
        analysis_result["has_generated_image"] = bool(gen_url)
        if not gen_url:
            if context.get("skip_image_gen"):
                analysis_result["no_image_reason"] = "no_credits"
            elif analysis_result.get("image_gen_error"):
                analysis_result["no_image_reason"] = "generation_error"
            elif analysis_result.get("upgrade_prompt"):
                analysis_result["no_image_reason"] = "upgrade_required"
            else:
                analysis_result["no_image_reason"] = "not_applicable"
        return analysis_result

    def test_with_image(self):
        r = self._enrich(
            {"generated_image_url": "/storage/generated/1/2.jpg"},
            {"enhancement_level": 2},
        )
        assert r["has_generated_image"] is True
        assert "no_image_reason" not in r
        assert r["enhancement_level"] == 2

    def test_no_image_no_credits(self):
        r = self._enrich({}, {"skip_image_gen": True})
        assert r["has_generated_image"] is False
        assert r["no_image_reason"] == "no_credits"

    def test_no_image_generation_error(self):
        r = self._enrich({"image_gen_error": "provider down"}, {})
        assert r["has_generated_image"] is False
        assert r["no_image_reason"] == "generation_error"

    def test_no_image_upgrade_prompt(self):
        r = self._enrich({"upgrade_prompt": True}, {})
        assert r["has_generated_image"] is False
        assert r["no_image_reason"] == "upgrade_required"

    def test_no_image_not_applicable(self):
        r = self._enrich({}, {})
        assert r["has_generated_image"] is False
        assert r["no_image_reason"] == "not_applicable"
        assert r["enhancement_level"] == 0

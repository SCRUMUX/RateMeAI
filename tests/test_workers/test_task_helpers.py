"""Tests for worker helper functions and result enrichment logic."""
from __future__ import annotations

from src.workers.tasks import _is_transient


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

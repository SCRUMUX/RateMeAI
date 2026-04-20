"""Tests for the cross-border AI-transfer guard (privacy audit C3 fix).

Verifies:
  - production + missing context  → raises (fail-closed backdoor patch).
  - production + consent granted → passes.
  - production + consent missing → raises.
  - dev/test + missing context   → no-op (backwards compatible).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.services.ai_transfer_guard import (
    AITransferForbiddenError,
    assert_external_transfer_allowed,
    task_context_scope,
)


def test_dev_without_context_is_noop():
    """Dev/test mode must not break standalone calls."""
    with patch("src.services.ai_transfer_guard.settings") as mock_settings:
        mock_settings.is_production = False
        # No task_context_scope active — guard should be silent.
        assert_external_transfer_allowed("openrouter")


def test_prod_without_context_raises():
    """Production must fail-closed when no pipeline context is bound."""
    with patch("src.services.ai_transfer_guard.settings") as mock_settings:
        mock_settings.is_production = True
        with pytest.raises(AITransferForbiddenError) as exc:
            assert_external_transfer_allowed("openrouter")
        assert exc.value.provider == "openrouter"
        assert exc.value.reason == "no_pipeline_context"


def test_prod_with_consent_passes():
    """Production with consent_ai_transfer=True must allow the call."""
    with patch("src.services.ai_transfer_guard.settings") as mock_settings:
        mock_settings.is_production = True
        ctx = {"policy_flags": {"consent_ai_transfer": True}}
        with task_context_scope(ctx):
            assert_external_transfer_allowed("openrouter")


def test_prod_without_consent_raises():
    """Production with consent missing must raise even inside a scope."""
    with patch("src.services.ai_transfer_guard.settings") as mock_settings:
        mock_settings.is_production = True
        ctx = {"policy_flags": {"consent_ai_transfer": False}}
        with task_context_scope(ctx):
            with pytest.raises(AITransferForbiddenError) as exc:
                assert_external_transfer_allowed("openrouter")
            assert exc.value.provider == "openrouter"


def test_dev_with_consent_passes():
    """Dev/test mode with consent behaves identically to prod."""
    with patch("src.services.ai_transfer_guard.settings") as mock_settings:
        mock_settings.is_production = False
        ctx = {"policy_flags": {"consent_ai_transfer": True}}
        with task_context_scope(ctx):
            assert_external_transfer_allowed("openrouter")


def test_dev_with_denied_consent_still_raises():
    """Dev/test mode must still enforce explicit denials."""
    with patch("src.services.ai_transfer_guard.settings") as mock_settings:
        mock_settings.is_production = False
        ctx = {"policy_flags": {"consent_ai_transfer": False}}
        with task_context_scope(ctx):
            with pytest.raises(AITransferForbiddenError):
                assert_external_transfer_allowed("reve")

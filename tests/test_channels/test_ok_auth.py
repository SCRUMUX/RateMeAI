"""Tests for OK auth signature verification."""
from __future__ import annotations

import hashlib
from unittest.mock import patch

from src.channels.ok_auth import verify_ok_auth_sig


@patch("src.channels.ok_auth.settings")
def test_valid_sig(mock_s):
    mock_s.ok_app_secret_key = "secret123"
    uid = "user1"
    sk = "session_key"
    expected = hashlib.md5(f"{uid}{sk}secret123".encode()).hexdigest()
    assert verify_ok_auth_sig(uid, sk, expected) is True


@patch("src.channels.ok_auth.settings")
def test_invalid_sig(mock_s):
    mock_s.ok_app_secret_key = "secret123"
    assert verify_ok_auth_sig("user1", "sk", "wrong") is False


@patch("src.channels.ok_auth.settings")
def test_empty_secret(mock_s):
    mock_s.ok_app_secret_key = ""
    assert verify_ok_auth_sig("u", "s", "x") is False

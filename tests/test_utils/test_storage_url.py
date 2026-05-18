"""Tests for ``normalize_storage_url``."""

from src.utils.storage_url import normalize_storage_url


def test_normalize_rewrites_storage_path_to_new_base():
    out = normalize_storage_url(
        "https://legacy.up.railway.app/storage/generated/u/t.jpg",
        "https://app-production-6986.up.railway.app",
    )
    assert (
        out == "https://app-production-6986.up.railway.app/storage/generated/u/t.jpg"
    )


def test_normalize_relative_key():
    out = normalize_storage_url("generated/u/t.jpg", "https://api.example.com")
    assert out == "https://api.example.com/storage/generated/u/t.jpg"


def test_normalize_passthrough_non_storage_http():
    out = normalize_storage_url("https://cdn.example.com/x.jpg", "https://api.example.com")
    assert out == "https://cdn.example.com/x.jpg"

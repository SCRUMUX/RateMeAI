"""Tests for catalog API endpoints."""
from __future__ import annotations


def test_list_modes(client):
    r = client.get("/api/v1/catalog/modes")
    assert r.status_code == 200
    data = r.json()
    assert "dating" in data["modes"]
    assert "cv" in data["modes"]
    assert "social" in data["modes"]


def test_list_styles_dating(client):
    r = client.get("/api/v1/catalog/styles?mode=dating")
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "dating"
    assert data["count"] > 0
    style = data["styles"][0]
    assert "key" in style
    assert "label" in style
    assert "hook" in style


def test_list_styles_unknown_mode(client):
    r = client.get("/api/v1/catalog/styles?mode=nonexistent")
    assert r.status_code == 404

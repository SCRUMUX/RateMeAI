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


# ----------------------------------------------------------------------
# style-schema-v2 (PR4) — ``?schema=v2`` contract
# ----------------------------------------------------------------------


def test_list_styles_schema_v2_includes_schema_version(client):
    """Each entry carries a per-style ``schema_version`` (1 or 2)."""
    r = client.get("/api/v1/catalog/styles?mode=dating&schema=v2")
    assert r.status_code == 200
    data = r.json()
    assert data["schema"] == "v2"
    assert data["count"] > 0
    for style in data["styles"]:
        assert "schema_version" in style
        assert style["schema_version"] in (1, 2)


def test_options_v1_default_unchanged(client):
    """Legacy clients (no schema param) keep receiving the v1 shape."""
    list_resp = client.get("/api/v1/catalog/styles?mode=dating")
    style_id = list_resp.json()["styles"][0]["key"]

    r = client.get(f"/api/v1/catalog/styles/{style_id}/options")
    assert r.status_code == 200
    data = r.json()
    assert data["style_id"] == style_id
    assert "options" in data
    assert "schema_version" not in data


def test_options_v2_falls_back_for_v1_styles(client):
    """Un-migrated styles return the v1 payload with ``schema_version: 1``."""
    from src.services.style_loader import load_styles_from_json

    v1_style = next(
        s for s in load_styles_from_json()
        if int(s.get("schema_version") or 0) != 2
    )
    style_id = v1_style["id"]

    r = client.get(f"/api/v1/catalog/styles/{style_id}/options?schema=v2")
    assert r.status_code == 200
    data = r.json()
    assert data["style_id"] == style_id
    assert data["schema_version"] == 1
    assert isinstance(data["options"], dict)


def test_options_v2_unit_for_migrated_entry(tmp_path, monkeypatch):
    """Unit-level check of the v2 options payload shape without FastAPI.

    Patches ``load_styles_from_json`` so the test is independent of
    whatever's in the committed ``data/styles.json`` at the time the
    suite runs — this matters because PR3 migrates entries in batches.
    """
    from src.services import style_catalog

    fake_entry = {
        "id": "unit_v2_style",
        "mode": "dating",
        "schema_version": 2,
        "trigger": "gym",
        "background": {
            "base": "modern indoor gym with equipment",
            "lock": "flexible",
            "overrides_allowed": ["rooftop_gym", "beach_gym"],
        },
        "clothing": {
            "default": "athletic training outfit",
            "allowed": ["tank_top", "hoodie"],
            "gender_neutral": True,
        },
        "weather": {"enabled": False, "allowed": [], "default_na": True},
        "context_slots": {
            "lighting": ["warm", "cool"],
            "framing": ["portrait", "half_body"],
            "angle_placement": ["front", "three_quarter"],
        },
        "quality_identity": {"base": "", "per_model_tail": {}},
    }

    monkeypatch.setattr(
        "src.services.style_loader.load_styles_from_json",
        lambda: [fake_entry],
    )

    payload = style_catalog.get_style_options_v2("unit_v2_style")
    assert payload is not None
    assert payload["schema_version"] == 2
    assert payload["trigger"] == "gym"

    assert payload["context_slots"]["lighting"] == ["warm", "cool"]
    assert payload["context_slots"]["framing"] == ["portrait", "half_body"]
    assert payload["context_slots"]["angle_placement"] == ["front", "three_quarter"]

    assert payload["weather"] == {
        "enabled": False,
        "allowed": [],
        "default_na": True,
    }
    assert payload["clothing"]["default"] == "athletic training outfit"
    assert payload["clothing"]["allowed"] == ["tank_top", "hoodie"]
    assert payload["background"]["lock"] == "flexible"
    assert payload["background"]["overrides_allowed"] == ["rooftop_gym", "beach_gym"]


def test_get_style_options_v2_returns_none_for_v1(monkeypatch):
    """``get_style_options_v2`` signals not-yet-migrated with ``None``."""
    from src.services import style_catalog

    monkeypatch.setattr(
        "src.services.style_loader.load_styles_from_json",
        lambda: [
            {
                "id": "legacy_style",
                "mode": "dating",
                "allowed_variations": {"lighting": ["warm"]},
            }
        ],
    )
    assert style_catalog.get_style_options_v2("legacy_style") is None

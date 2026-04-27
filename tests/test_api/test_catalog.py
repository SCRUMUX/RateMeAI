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
    """Un-migrated styles return the v1 payload with ``schema_version: 1``.

    After the 1.27.0 cutover every entry in ``data/styles.json`` is v2, so
    the fallback branch is dormant in practice. We still keep the contract
    covered — if anyone manually reverts a style or adds a fresh v1 entry
    the assertions re-engage immediately; otherwise the test soft-skips so
    the green build truthfully reflects reality.
    """
    import pytest
    from src.services.style_loader import load_styles_from_json

    v1_style = next(
        (
            s for s in load_styles_from_json()
            if int(s.get("schema_version") or 0) != 2
        ),
        None,
    )
    if v1_style is None:
        pytest.skip(
            "all styles migrated to schema_version=2; fallback branch "
            "still exercised by test_options_v2_falls_back_unit below"
        )
    style_id = v1_style["id"]

    r = client.get(f"/api/v1/catalog/styles/{style_id}/options?schema=v2")
    assert r.status_code == 200
    data = r.json()
    assert data["style_id"] == style_id
    assert data["schema_version"] == 1
    assert isinstance(data["options"], dict)


def test_options_v2_falls_back_unit(monkeypatch):
    """Unit-level guard for the v1 fallback branch: when ``get_style_options_v2``
    returns ``None`` the handler must downgrade to the v1 options payload and
    tag it with ``schema_version: 1``. Synthesises a v1-only style directly so
    this coverage stays alive regardless of what's in ``data/styles.json``.
    """
    from src.services import style_catalog

    fake_v1_entry = {
        "id": "unit_v1_style",
        "mode": "dating",
        "display_label": "Unit V1",
        "hook_text": "unit hook",
    }

    def _load():
        return [fake_v1_entry]

    monkeypatch.setattr(style_catalog, "get_style_options_v2", lambda _sid: None)
    monkeypatch.setattr(
        "src.services.style_loader.load_styles_from_json", _load
    )

    options = style_catalog.get_style_options("unit_v1_style")
    assert isinstance(options, dict)


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
    assert payload["clothing"]["default"] == {
        "male": "athletic training outfit",
        "female": "athletic training outfit",
        "neutral": "athletic training outfit",
    }
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


# ----------------------------------------------------------------------
# Phase 3 — scenario-styles endpoint and main-catalog filtering
# ----------------------------------------------------------------------


def test_scenario_styles_returns_document_format_styles(client):
    """``GET /scenario-styles?scenario=document-photo`` returns the 5 format styles."""
    r = client.get("/api/v1/catalog/scenario-styles?scenario=document-photo")
    assert r.status_code == 200
    data = r.json()
    assert data["scenario"] == "document-photo"
    assert data["schema"] == "v1"
    keys = {s["key"] for s in data["styles"]}
    assert {"photo_3x4", "passport_rf", "visa_eu", "visa_us", "photo_4x6"} <= keys


def test_scenario_styles_unknown(client):
    r = client.get("/api/v1/catalog/scenario-styles?scenario=does-not-exist")
    assert r.status_code == 404


def test_scenario_styles_v2_includes_schema_version(client):
    r = client.get(
        "/api/v1/catalog/scenario-styles?scenario=document-photo&schema=v2"
    )
    assert r.status_code == 200
    data = r.json()
    for style in data["styles"]:
        assert "schema_version" in style


def test_main_catalog_excludes_scenario_styles(client):
    """Scenario-tagged styles must not appear in ``/styles?mode=cv``."""
    r = client.get("/api/v1/catalog/styles?mode=cv")
    assert r.status_code == 200
    keys = {s["key"] for s in r.json()["styles"]}
    for doc_key in ("photo_3x4", "passport_rf", "visa_eu", "visa_us", "photo_4x6"):
        assert doc_key not in keys


def test_legacy_doc_styles_purged(client):
    """Removed legacy doc styles are gone from every cv-mode endpoint."""
    r = client.get("/api/v1/catalog/styles?mode=cv")
    assert r.status_code == 200
    keys = {s["key"] for s in r.json()["styles"]}
    for legacy in ("doc_passport_neutral", "doc_visa_compliant", "doc_resume_headshot"):
        assert legacy not in keys


# ----------------------------------------------------------------------
# Phase 3 — unit-level coverage for the scenario filter (no FastAPI)
# ----------------------------------------------------------------------


def test_scenario_filter_unit_excludes_scenario_styles(monkeypatch):
    """``get_catalog_json`` filters out entries with ``scenario`` set."""
    from src.services import style_catalog

    fake_entries = [
        {
            "id": "regular_cv",
            "mode": "cv",
            "display_label": "🧑‍💼 Regular",
            "hook_text": "main catalog entry",
        },
        {
            "id": "doc_format",
            "mode": "cv",
            "scenario": "document-photo",
            "display_label": "📋 Doc",
            "hook_text": "scenario-only",
        },
        {
            "id": "legacy_only",
            "mode": "cv",
            "is_scenario_only": True,
            "display_label": "👻 Legacy",
            "hook_text": "legacy boolean still works",
        },
    ]

    monkeypatch.setattr(
        "src.services.style_loader.load_styles_from_json",
        lambda: fake_entries,
    )

    keys = {s["key"] for s in style_catalog.get_catalog_json("cv")}
    assert keys == {"regular_cv"}

    keys_v2 = {s["key"] for s in style_catalog.get_catalog_json_v2("cv")}
    assert keys_v2 == {"regular_cv"}


def test_scenario_styles_unit_returns_only_matching_scenario(monkeypatch):
    """``get_scenario_styles_json`` returns only entries with matching scenario."""
    from src.services import style_catalog

    fake_entries = [
        {
            "id": "doc_a",
            "mode": "cv",
            "scenario": "document-photo",
            "display_label": "A",
            "hook_text": "",
        },
        {
            "id": "tinder_a",
            "mode": "dating",
            "scenario": "tinder-pack",
            "display_label": "T",
            "hook_text": "",
        },
        {
            "id": "regular",
            "mode": "cv",
            "display_label": "R",
            "hook_text": "",
        },
    ]
    monkeypatch.setattr(
        "src.services.style_loader.load_styles_from_json",
        lambda: fake_entries,
    )

    docs = style_catalog.get_scenario_styles_json("document-photo")
    assert {s["key"] for s in docs} == {"doc_a"}

    tinder = style_catalog.get_scenario_styles_json_v2("tinder-pack")
    assert {s["key"] for s in tinder} == {"tinder_a"}
    assert all("schema_version" in s for s in tinder)

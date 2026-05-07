"""Admin endpoints — lint + conflicts integration (1.29.0).

Calls the route handlers directly with the same isolated styles file
used by ``test_admin_styles.py``. The handlers shadow ``_admin``
because :func:`require_admin` is a FastAPI dependency, not invoked
when we call the function directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from src.api.v1.admin import styles as admin_styles
from src.services import style_loader, style_store


@pytest.fixture(autouse=True)
def _reset_admin_id_cache():
    # 1.55.4 — ``_parse_admin_ids`` no longer carries ``lru_cache``.
    # Fixture kept as a no-op for symmetry with ``test_admin_styles``;
    # nothing to clear on entry/exit anymore.
    yield


@pytest.fixture
def isolated_styles_file(tmp_path: Path, monkeypatch):
    fake_path = tmp_path / "styles.json"
    fake_path.write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(style_store, "STYLES_PATH", fake_path)
    monkeypatch.setattr(style_loader, "_STYLES_CACHE", [])

    real_loader = style_loader.load_styles_from_json

    def _fake_loader():
        if not style_loader._STYLES_CACHE:
            style_loader._STYLES_CACHE = json.loads(
                fake_path.read_text(encoding="utf-8")
            )
        return style_loader._STYLES_CACHE

    monkeypatch.setattr(style_loader, "load_styles_from_json", _fake_loader)
    yield fake_path
    style_loader.load_styles_from_json = real_loader

    from src.services.style_catalog import STYLE_CATALOG

    STYLE_CATALOG._invalidate()  # noqa: SLF001
    style_loader._STYLES_CACHE = []  # noqa: SLF001


def _seed(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries), encoding="utf-8")
    style_loader._STYLES_CACHE = []  # noqa: SLF001


# ---------------------------------------------------------------------------
# /admin/styles/lint — bulk
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lint_all_returns_only_dirty_styles(isolated_styles_file):
    _seed(
        isolated_styles_file,
        [
            {
                "id": "clean",
                "schema_version": 3,
                "mode": "social",
                "trigger_pool": ["round wall mirror in frame"],
                "scene_anchor": "minimalist apartment",
                "available_channels": ["lighting"],
                "location_type": "indoor",
                "ambient": {"lighting": ["warm"]},
            },
            {
                "id": "dirty",
                "schema_version": 3,
                "mode": "social",
                "trigger_pool": ["full-length mirror reflection"],
                "scene_anchor": "studio",
                "available_channels": ["season"],
                "location_type": "indoor",
                "ambient": {"season": ["spring"]},
            },
        ],
    )

    result = await admin_styles.lint_all_styles(_admin=None)
    assert "clean" not in result
    assert "dirty" in result
    codes = {i["code"] for i in result["dirty"]}
    assert "INDOOR_SEASON" in codes
    assert "TRIGGER_DIRTY" in codes


@pytest.mark.asyncio
async def test_lint_all_empty_when_catalog_clean(isolated_styles_file):
    _seed(
        isolated_styles_file,
        [
            {
                "id": "ok",
                "schema_version": 3,
                "mode": "social",
                "trigger_pool": ["calm street scene"],
                "scene_anchor": "urban street",
            }
        ],
    )
    assert await admin_styles.lint_all_styles(_admin=None) == {}


# ---------------------------------------------------------------------------
# /admin/styles/{id}/lint — single style
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lint_one_returns_issues(isolated_styles_file):
    _seed(
        isolated_styles_file,
        [
            {
                "id": "burj_partial",
                "schema_version": 3,
                "mode": "social",
                "trigger_pool": ["Burj Khalifa skyline at twilight"],
                "scene_anchor": "rooftop terrace",
                "location_type": "outdoor",
                "available_channels": ["season"],
                "ambient": {"season": ["spring", "autumn"]},
            }
        ],
    )
    issues = await admin_styles.lint_one_style("burj_partial", _admin=None)
    codes = {i["code"] for i in issues}
    assert "SEASON_INCOMPLETE" in codes


@pytest.mark.asyncio
async def test_lint_unknown_id_returns_404(isolated_styles_file):
    with pytest.raises(HTTPException) as exc:
        await admin_styles.lint_one_style("ghost", _admin=None)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# /admin/styles/conflicts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflicts_endpoint_returns_three_buckets(isolated_styles_file):
    _seed(
        isolated_styles_file,
        [
            {"id": "office_a", "mode": "cv", "display_label": "🏢 В офисе"},
            {"id": "office_b", "mode": "cv", "display_label": "В офисе"},
            {"id": "studio", "mode": "social", "display_label": "🎬 Студия"},
        ],
    )
    report = await admin_styles.list_style_conflicts(_admin=None)
    assert set(report.keys()) == {"duplicate_labels", "similar_labels", "duplicate_ids"}
    assert any(
        sorted(d["ids"]) == ["office_a", "office_b"]
        for d in report["duplicate_labels"]
    )


# ---------------------------------------------------------------------------
# /admin/styles validation — available_channels / location_type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rejects_unknown_channel(isolated_styles_file):
    payload = admin_styles.StyleCreatePayload(
        id="weird",
        mode="social",
        schema_version=1,
    )
    raw = payload.model_dump()
    raw["available_channels"] = ["lighitng"]  # typo
    payload = admin_styles.StyleCreatePayload(**raw)
    with pytest.raises(HTTPException) as exc:
        await admin_styles.create_style(payload, _admin=None)
    assert exc.value.status_code == 422
    assert "available_channels" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_create_rejects_unknown_location(isolated_styles_file):
    payload = admin_styles.StyleCreatePayload(
        id="weird",
        mode="social",
        schema_version=1,
    )
    raw = payload.model_dump()
    raw["location_type"] = "underwater"
    payload = admin_styles.StyleCreatePayload(**raw)
    with pytest.raises(HTTPException) as exc:
        await admin_styles.create_style(payload, _admin=None)
    assert exc.value.status_code == 422
    assert "location_type" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_create_accepts_valid_v1_with_v3_fields(isolated_styles_file):
    payload = admin_styles.StyleCreatePayload(
        id="ok_v1",
        mode="social",
    )
    raw = payload.model_dump()
    raw["available_channels"] = ["lighting", "time_of_day"]
    raw["location_type"] = "indoor"
    payload = admin_styles.StyleCreatePayload(**raw)
    created = await admin_styles.create_style(payload, _admin=None)
    assert created["available_channels"] == ["lighting", "time_of_day"]
    assert created["location_type"] == "indoor"

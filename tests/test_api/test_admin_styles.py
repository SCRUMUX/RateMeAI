"""Unit tests for the ``/api/v1/admin/styles`` surface.

Covers two angles that don't require a live Postgres + Redis:

1. The auth gate (``require_admin``) — purely a string-set check on
   ``settings.admin_user_ids`` once a user is resolved.
2. The CRUD payloads against an in-memory styles list. We swap
   ``style_store`` and ``style_loader`` cache pointers to an isolated
   temporary file so the production ``data/styles.json`` is never
   touched and parallel tests can't race.

The full FastAPI integration test (real DB session, real auth) lives
in ``test_catalog.py`` and is gated on docker-compose anyway.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.v1.admin import auth as admin_auth
from src.api.v1.admin import styles as admin_styles
from src.services import style_loader, style_store


@pytest.fixture(autouse=True)
def _reset_admin_id_cache():
    admin_auth._parse_admin_ids.cache_clear()
    yield
    admin_auth._parse_admin_ids.cache_clear()


@pytest.fixture
def isolated_styles_file(tmp_path: Path, monkeypatch):
    """Point ``style_store`` and ``style_loader`` at a temp JSON file."""
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
    # The bot ``STYLE_CATALOG`` proxy memoises whatever it built during
    # the test (against the temp file), so without an explicit reset
    # the next test would see e.g. a 1-entry isolated catalog instead
    # of the real ``data/styles.json``.
    from src.services.style_catalog import STYLE_CATALOG

    STYLE_CATALOG._invalidate()  # noqa: SLF001
    style_loader._STYLES_CACHE = []  # noqa: SLF001


# ---------------------------------------------------------------------------
# require_admin / get_admin_ids
# ---------------------------------------------------------------------------


def test_admin_ids_parse_handles_whitespace_and_empties(monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids",
        " uid-1 , uid-2,  ,uid-3,",
        raising=False,
    )
    admin_auth._parse_admin_ids.cache_clear()
    ids = admin_auth.get_admin_ids()
    assert ids == frozenset({"uid-1", "uid-2", "uid-3"})


def test_admin_ids_empty_locks_endpoint(monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", "", raising=False
    )
    admin_auth._parse_admin_ids.cache_clear()
    assert admin_auth.get_admin_ids() == frozenset()


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin(monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", "admin-1,admin-2", raising=False
    )
    admin_auth._parse_admin_ids.cache_clear()
    user = SimpleNamespace(id="random-user")
    with pytest.raises(HTTPException) as exc:
        await admin_auth.require_admin(user=user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_accepts_listed_user(monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", "admin-1,admin-2", raising=False
    )
    admin_auth._parse_admin_ids.cache_clear()
    user = SimpleNamespace(id="admin-2")
    result = await admin_auth.require_admin(user=user)
    assert result is user


# ---------------------------------------------------------------------------
# style_store atomic write + invalidate_caches
# ---------------------------------------------------------------------------


def test_save_styles_writes_atomically(isolated_styles_file):
    payload = [{"id": "alpha", "mode": "cv"}]
    style_store.save_styles(payload)
    on_disk = json.loads(isolated_styles_file.read_text(encoding="utf-8"))
    assert on_disk == payload
    # Tmp swap-file must be gone after a successful write.
    assert not isolated_styles_file.with_suffix(".json.tmp").exists()


def test_invalidate_caches_picks_up_disk_changes(isolated_styles_file):
    """After invalidation the loader returns whatever is on disk now,
    not the previously cached snapshot.

    ``invalidate_caches`` may eagerly re-prime the v1 cache via the v2
    loader (which calls ``load_styles_from_json`` itself); we don't
    care whether the cache is empty or already-warm — only that the
    next read reflects the new file contents.
    """
    isolated_styles_file.write_text(
        json.dumps([{"id": "x", "mode": "cv"}]), encoding="utf-8"
    )
    style_loader._STYLES_CACHE = [{"id": "stale", "mode": "social"}]

    style_store.invalidate_caches()

    fresh = style_loader.load_styles_from_json()
    assert fresh == [{"id": "x", "mode": "cv"}]


# ---------------------------------------------------------------------------
# CRUD route bodies — call the handlers directly, skipping FastAPI deps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_then_get_then_update_then_delete(isolated_styles_file):
    new_entry = admin_styles.StyleCreatePayload(
        id="creative_director_new",
        mode="cv",
        display_label="🎨 Creative",
        hook_text="hook",
    )
    created = await admin_styles.create_style(new_entry, _admin=None)
    assert created["id"] == "creative_director_new"

    fetched = await admin_styles.get_style(
        "creative_director_new", _admin=None
    )
    assert fetched["display_label"] == "🎨 Creative"

    patch = admin_styles.StyleUpdatePayload(
        unlock_after_generations=5, hook_text="updated"
    )
    updated = await admin_styles.update_style(
        "creative_director_new", patch, _admin=None
    )
    assert updated["unlock_after_generations"] == 5
    assert updated["hook_text"] == "updated"
    assert updated["display_label"] == "🎨 Creative"  # untouched fields kept

    await admin_styles.delete_style("creative_director_new", _admin=None)
    on_disk = json.loads(isolated_styles_file.read_text(encoding="utf-8"))
    assert on_disk == []


@pytest.mark.asyncio
async def test_create_rejects_duplicate_id(isolated_styles_file):
    payload = admin_styles.StyleCreatePayload(id="dupe", mode="cv")
    await admin_styles.create_style(payload, _admin=None)
    with pytest.raises(HTTPException) as exc:
        await admin_styles.create_style(payload, _admin=None)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_unknown_returns_404(isolated_styles_file):
    patch = admin_styles.StyleUpdatePayload(hook_text="x")
    with pytest.raises(HTTPException) as exc:
        await admin_styles.update_style("ghost", patch, _admin=None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_unknown_returns_404(isolated_styles_file):
    with pytest.raises(HTTPException) as exc:
        await admin_styles.delete_style("ghost", _admin=None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reload_returns_count(isolated_styles_file):
    isolated_styles_file.write_text(
        json.dumps([{"id": "a", "mode": "cv"}, {"id": "b", "mode": "cv"}]),
        encoding="utf-8",
    )
    res = await admin_styles.reload_styles(_admin=None)
    assert res == {"status": "ok", "count": 2}


@pytest.mark.asyncio
async def test_create_v2_validates_slot_block(isolated_styles_file):
    bad = admin_styles.StyleCreatePayload(
        id="bad_v2",
        mode="cv",
        schema_version=2,
    )
    with pytest.raises(HTTPException) as exc:
        await admin_styles.create_style(bad, _admin=None)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_create_v2_requires_clothing_default(isolated_styles_file):
    """v2 styles without ``clothing.default`` ship an unrenderable prompt."""
    bad = admin_styles.StyleCreatePayload(
        id="missing_clothing",
        mode="social",
        schema_version=2,
    )
    bad_dump = bad.model_dump()
    bad_dump["background"] = {"base": "neon street at night"}
    bad_dump["clothing"] = {"default": ""}
    bad_dump["quality_identity"] = {"base": "8k portrait, soft skin"}

    # Bypass pydantic to inject the raw dict shape the route receives.
    payload = admin_styles.StyleCreatePayload(**bad_dump)
    with pytest.raises(HTTPException) as exc:
        await admin_styles.create_style(payload, _admin=None)
    assert exc.value.status_code == 422
    assert "clothing.default" in exc.value.detail


@pytest.mark.asyncio
async def test_create_v2_requires_quality_identity_base(isolated_styles_file):
    """v2 styles without ``quality_identity.base`` lose the identity anchor."""
    payload = admin_styles.StyleCreatePayload(
        id="missing_quality",
        mode="social",
        schema_version=2,
    )
    raw = payload.model_dump()
    raw["background"] = {"base": "rooftop at golden hour"}
    raw["clothing"] = {"default": "smart casual fitted shirt"}
    raw["quality_identity"] = {"base": "   "}
    payload = admin_styles.StyleCreatePayload(**raw)
    with pytest.raises(HTTPException) as exc:
        await admin_styles.create_style(payload, _admin=None)
    assert exc.value.status_code == 422
    assert "quality_identity.base" in exc.value.detail


@pytest.mark.asyncio
async def test_create_v2_accepts_complete_slot_block(isolated_styles_file):
    """A v2 entry with all required slots must be accepted."""
    payload = admin_styles.StyleCreatePayload(
        id="ok_v2",
        mode="social",
        display_label="OK",
        schema_version=2,
    )
    raw = payload.model_dump()
    raw["background"] = {
        "base": "rooftop at golden hour, city skyline behind",
        "lock": "flexible",
        "overrides_allowed": [],
    }
    raw["clothing"] = {
        "default": "smart casual fitted dark shirt",
        "allowed": [],
        "gender_neutral": True,
    }
    raw["quality_identity"] = {
        "base": "8k portrait, sharp facial detail, natural skin texture"
    }
    payload = admin_styles.StyleCreatePayload(**raw)
    created = await admin_styles.create_style(payload, _admin=None)
    assert created["id"] == "ok_v2"


# ---------------------------------------------------------------------------
# bot STYLE_CATALOG proxy hot-reload
# ---------------------------------------------------------------------------


def test_bot_catalog_invalidates_after_admin_save(isolated_styles_file):
    """Editing styles via the admin path must be visible to the bot
    on the next keyboard render — without a process restart.

    Regression guard for the migration of ``STYLE_CATALOG`` from a
    hardcoded dict to a ``_BotCatalogProxy`` view over ``data/styles.json``.
    """
    from src.services.style_catalog import STYLE_CATALOG

    STYLE_CATALOG._invalidate()  # noqa: SLF001

    isolated_styles_file.write_text(
        json.dumps(
            [
                {
                    "id": "alpha",
                    "mode": "cv",
                    "display_label": "Alpha",
                    "hook_text": "hookA",
                }
            ]
        ),
        encoding="utf-8",
    )
    style_loader._STYLES_CACHE = []
    STYLE_CATALOG._invalidate()  # noqa: SLF001

    initial = STYLE_CATALOG.get("cv", [])
    assert [k for k, *_ in initial] == ["alpha"]

    style_store.save_styles(
        [
            {
                "id": "alpha",
                "mode": "cv",
                "display_label": "Alpha",
                "hook_text": "hookA",
            },
            {
                "id": "beta",
                "mode": "cv",
                "display_label": "Beta",
                "hook_text": "hookB",
            },
        ]
    )

    after = STYLE_CATALOG.get("cv", [])
    assert sorted(k for k, *_ in after) == ["alpha", "beta"]


def test_bot_catalog_skips_scenario_only_entries(isolated_styles_file):
    from src.services.style_catalog import STYLE_CATALOG

    isolated_styles_file.write_text(
        json.dumps(
            [
                {
                    "id": "regular",
                    "mode": "cv",
                    "display_label": "Reg",
                    "hook_text": "h",
                },
                {
                    "id": "doc_only",
                    "mode": "cv",
                    "display_label": "Doc",
                    "hook_text": "h",
                    "scenario": "documents",
                },
            ]
        ),
        encoding="utf-8",
    )
    style_loader._STYLES_CACHE = []
    STYLE_CATALOG._invalidate()  # noqa: SLF001

    items = STYLE_CATALOG.get("cv", [])
    assert [k for k, *_ in items] == ["regular"]


def test_bot_catalog_supports_dict_protocol(isolated_styles_file):
    from src.services.style_catalog import STYLE_CATALOG

    isolated_styles_file.write_text(
        json.dumps(
            [
                {"id": "a", "mode": "cv", "display_label": "A", "hook_text": ""},
                {"id": "b", "mode": "social", "display_label": "B", "hook_text": ""},
            ]
        ),
        encoding="utf-8",
    )
    style_loader._STYLES_CACHE = []
    STYLE_CATALOG._invalidate()  # noqa: SLF001

    assert "cv" in STYLE_CATALOG
    assert "social" in STYLE_CATALOG
    assert "missing" not in STYLE_CATALOG
    assert sorted(STYLE_CATALOG.keys()) == ["cv", "social"]
    items_per_mode = dict(STYLE_CATALOG.items())
    assert set(items_per_mode) == {"cv", "social"}
    assert STYLE_CATALOG["cv"][0][0] == "a"

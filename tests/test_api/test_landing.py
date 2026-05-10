"""Unit tests for the landing CMS surface (``/api/v1/landing/*`` and
``/api/v1/admin/landing/*``).

We point ``landing_store.LANDING_PATH`` at a tmp file and call the handler
functions directly — no FastAPI app boot, no DB.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException, Response

from src.api.v1 import landing as public_landing
from src.api.v1.admin import landing as admin_landing
from src.config import settings
from src.services import landing_store


@pytest.fixture
def isolated_landing_file(tmp_path: Path, monkeypatch):
    fake_path = tmp_path / "landing_content.json"
    fake_path.write_text(
        json.dumps(
            {
                "pages": {
                    "home": {
                        "blocks": [
                            {"id": "footer", "type": "footer", "enabled": True, "data": {"copyright": "© test"}},
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(landing_store, "LANDING_PATH", fake_path)
    # Variant B: pin the editor role + ``ru`` market so the test suite
    # uses the legacy filename and exercises the admin write path.
    monkeypatch.setattr(settings, "cms_role", "editor", raising=False)
    monkeypatch.setattr(settings, "market_id", "ru", raising=False)
    monkeypatch.setattr(settings, "cms_follower_urls", "", raising=False)
    landing_store.invalidate_cache()
    yield fake_path
    landing_store.invalidate_cache()


# ---------------------------------------------------------------------------
# public GET
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_get_known_slug_returns_payload(isolated_landing_file):
    response = Response()
    res = await public_landing.get_landing_page("home", response, market=None)
    assert res["slug"] == "home"
    assert isinstance(res["page"], dict)
    blocks = res["page"].get("blocks")
    assert isinstance(blocks, list) and blocks[0]["type"] == "footer"


@pytest.mark.asyncio
async def test_public_get_unknown_slug_returns_404(isolated_landing_file):
    response = Response()
    with pytest.raises(HTTPException) as exc:
        await public_landing.get_landing_page("does-not-exist", response, market=None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_public_get_sets_cache_control(isolated_landing_file):
    """CDN should be allowed to cache the public landing payload."""
    response = Response()
    await public_landing.get_landing_page("home", response, market=None)
    cache_control = response.headers.get("Cache-Control", "")
    assert "s-maxage=60" in cache_control
    assert "stale-while-revalidate=600" in cache_control
    assert "public" in cache_control


# ---------------------------------------------------------------------------
# admin CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_list_returns_sorted_slugs(isolated_landing_file):
    res = await admin_landing.list_pages(market="ru", _admin=None)
    assert res == {"market": "ru", "slugs": ["home"]}


@pytest.mark.asyncio
async def test_admin_get_known_slug(isolated_landing_file):
    res = await admin_landing.get_page("home", market="ru", _admin=None)
    assert res["slug"] == "home"
    assert res["market"] == "ru"
    assert res["page"]["blocks"][0]["data"]["copyright"] == "© test"


@pytest.mark.asyncio
async def test_admin_get_unknown_slug(isolated_landing_file):
    with pytest.raises(HTTPException) as exc:
        await admin_landing.get_page("ghost", market="ru", _admin=None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_put_persists_and_invalidates_cache(isolated_landing_file):
    new_page = {"blocks": [{"id": "footer", "type": "footer", "enabled": True, "data": {"copyright": "© updated"}}]}
    payload = admin_landing.AdminLandingPagePayload(page=new_page)
    res = await admin_landing.put_page("home", payload, market="ru", _admin=None)
    assert res == {"status": "ok", "market": "ru", "slug": "home"}

    public = await public_landing.get_landing_page("home", Response(), market="ru")
    assert public["page"]["blocks"][0]["data"]["copyright"] == "© updated"

    on_disk = json.loads(isolated_landing_file.read_text(encoding="utf-8"))
    assert on_disk["pages"]["home"] == new_page


@pytest.mark.asyncio
async def test_admin_put_creates_new_slug(isolated_landing_file):
    payload = admin_landing.AdminLandingPagePayload(page={"blocks": []})
    await admin_landing.put_page("dokumenty", payload, market="ru", _admin=None)
    listed = await admin_landing.list_pages(market="ru", _admin=None)
    assert listed == {"market": "ru", "slugs": ["dokumenty", "home"]}


@pytest.mark.asyncio
async def test_admin_put_blocked_on_follower(isolated_landing_file, monkeypatch):
    """Variant B guard: writes must 403 when running on a follower."""
    monkeypatch.setattr(settings, "cms_role", "follower", raising=False)
    payload = admin_landing.AdminLandingPagePayload(page={"blocks": []})
    with pytest.raises(HTTPException) as exc:
        await admin_landing.put_page("home", payload, market="ru", _admin=None)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_markets(isolated_landing_file):
    res = await admin_landing.list_markets(_admin=None)
    assert "ru" in res["markets"]
    assert "global" in res["markets"]
    assert res["cms_role"] == "editor"

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
    landing_store.invalidate_cache()
    yield fake_path
    landing_store.invalidate_cache()


# ---------------------------------------------------------------------------
# public GET
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_get_known_slug_returns_payload(isolated_landing_file):
    response = Response()
    res = await public_landing.get_landing_page("home", response)
    assert res["slug"] == "home"
    assert isinstance(res["page"], dict)
    blocks = res["page"].get("blocks")
    assert isinstance(blocks, list) and blocks[0]["type"] == "footer"


@pytest.mark.asyncio
async def test_public_get_unknown_slug_returns_404(isolated_landing_file):
    response = Response()
    with pytest.raises(HTTPException) as exc:
        await public_landing.get_landing_page("does-not-exist", response)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_public_get_sets_cache_control(isolated_landing_file):
    """CDN should be allowed to cache the public landing payload."""
    response = Response()
    await public_landing.get_landing_page("home", response)
    cache_control = response.headers.get("Cache-Control", "")
    assert "s-maxage=60" in cache_control
    assert "stale-while-revalidate=600" in cache_control
    assert "public" in cache_control


# ---------------------------------------------------------------------------
# admin CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_list_returns_sorted_slugs(isolated_landing_file):
    res = await admin_landing.list_pages(_admin=None)
    assert res == {"slugs": ["home"]}


@pytest.mark.asyncio
async def test_admin_get_known_slug(isolated_landing_file):
    res = await admin_landing.get_page("home", _admin=None)
    assert res["slug"] == "home"
    assert res["page"]["blocks"][0]["data"]["copyright"] == "© test"


@pytest.mark.asyncio
async def test_admin_get_unknown_slug(isolated_landing_file):
    with pytest.raises(HTTPException) as exc:
        await admin_landing.get_page("ghost", _admin=None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_put_persists_and_invalidates_cache(isolated_landing_file):
    new_page = {"blocks": [{"id": "footer", "type": "footer", "enabled": True, "data": {"copyright": "© updated"}}]}
    payload = admin_landing.AdminLandingPagePayload(page=new_page)
    res = await admin_landing.put_page("home", payload, _admin=None)
    assert res == {"status": "ok", "slug": "home"}

    # Public GET must observe the updated content (cache was invalidated).
    public = await public_landing.get_landing_page("home", Response())
    assert public["page"]["blocks"][0]["data"]["copyright"] == "© updated"

    # And the on-disk file must reflect it (atomic write).
    on_disk = json.loads(isolated_landing_file.read_text(encoding="utf-8"))
    assert on_disk["pages"]["home"] == new_page


@pytest.mark.asyncio
async def test_admin_put_creates_new_slug(isolated_landing_file):
    payload = admin_landing.AdminLandingPagePayload(page={"blocks": []})
    await admin_landing.put_page("dokumenty", payload, _admin=None)
    listed = await admin_landing.list_pages(_admin=None)
    assert listed == {"slugs": ["dokumenty", "home"]}

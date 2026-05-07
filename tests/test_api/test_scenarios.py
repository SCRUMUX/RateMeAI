"""Integration-style tests for ``/api/v1/scenarios``.

We point the loader at a temp JSON file and call the endpoint
handlers directly (no app.boot, no DB) — same approach as
``tests/test_api/test_landing.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException, Response

from src.api.v1 import scenarios as scenarios_api
from src.scenarios import loader as scenarios_loader


@pytest.fixture
def isolated_scenarios_file(tmp_path: Path, monkeypatch):
    fake_path = tmp_path / "scenarios.json"
    fake_path.write_text(
        json.dumps(
            {
                "scenarios": {
                    "visa-test": {
                        "kind": "visa",
                        "api_mode": "cv",
                        "pipeline_profile": "simple",
                        "step3_mode": "document_formats",
                        "output_spec": {
                            "size_mm": [35, 45],
                            "dpi": 300,
                            "background_color": "#FFFFFF",
                            "head_height_mm": [32, 36],
                            "aspect_key": "visa_test",
                        },
                        "prompt_overrides": {
                            "analysis_checklist": ["a", "b"],
                            "image_instructions": "x",
                        },
                        "paywall": {"pack_qty": 5, "show_paywall": True},
                        "landing_slug": "visa-test",
                        "enabled": True,
                    },
                    "visa-dark": {
                        "kind": "visa",
                        "api_mode": "cv",
                        "enabled": False,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scenarios_loader, "SCENARIOS_PATH", fake_path)
    scenarios_loader.invalidate_cache()
    yield fake_path
    scenarios_loader.invalidate_cache()


@pytest.mark.asyncio
async def test_list_returns_only_enabled(isolated_scenarios_file):
    response = Response()
    res = await scenarios_api.list_public_scenarios(response)
    slugs = {s["slug"] for s in res["scenarios"]}
    assert "visa-test" in slugs
    assert "visa-dark" not in slugs
    assert res["count"] == len(res["scenarios"])


@pytest.mark.asyncio
async def test_list_sets_cache_control(isolated_scenarios_file):
    response = Response()
    await scenarios_api.list_public_scenarios(response)
    cc = response.headers.get("Cache-Control", "")
    assert "s-maxage=60" in cc
    assert "stale-while-revalidate=600" in cc


@pytest.mark.asyncio
async def test_get_known_returns_payload(isolated_scenarios_file):
    response = Response()
    res = await scenarios_api.get_public_scenario("visa-test", response)
    s = res["scenario"]
    assert s["slug"] == "visa-test"
    assert s["kind"] == "visa"
    assert s["output_spec"]["aspect_key"] == "visa_test"
    # Sensitive prompt overrides must NOT leak through the public API.
    assert "prompt_overrides" not in s
    assert "requirements" not in s


@pytest.mark.asyncio
async def test_get_disabled_returns_404(isolated_scenarios_file):
    response = Response()
    with pytest.raises(HTTPException) as exc:
        await scenarios_api.get_public_scenario("visa-dark", response)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_unknown_returns_404(isolated_scenarios_file):
    response = Response()
    with pytest.raises(HTTPException) as exc:
        await scenarios_api.get_public_scenario("ghost", response)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_compliance_endpoint_returns_checklist(isolated_scenarios_file):
    response = Response()
    res = await scenarios_api.get_scenario_compliance("visa-test", response)
    assert res["slug"] == "visa-test"
    assert res["kind"] == "visa"
    assert res["checklist"] == [
        {"rule": "a", "status": "pending"},
        {"rule": "b", "status": "pending"},
    ]
    assert res["output_spec"]["aspect_key"] == "visa_test"


@pytest.mark.asyncio
async def test_compliance_endpoint_404_for_disabled(isolated_scenarios_file):
    response = Response()
    with pytest.raises(HTTPException) as exc:
        await scenarios_api.get_scenario_compliance("visa-dark", response)
    assert exc.value.status_code == 404

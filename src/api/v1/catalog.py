"""Style catalog API — serves catalog data to web / mini-app clients.

The ``?schema=v2`` query parameter opts-in to the slot-based view of a
style (see :mod:`src.prompts.style_schema_v2`). Without the parameter
the endpoints keep returning the legacy payload so existing clients
stay untouched — this is the contract for PR4 of the
style-schema-v2 migration.

v1.76 — the ``/styles`` endpoint now applies a per-caller deterministic
shuffle so different users see different orderings (avoiding the
"every new visitor sees the same top-2 styles" UX problem). The
shuffle seed is derived from the authenticated user's UUID when a
session / API-key is presented, and from ``client_ip + UTC date``
otherwise — giving anonymous visitors a stable order for a day plus
a different order each day, and distinct orderings between concurrent
anonymous visitors on different IPs. The scenario-styles endpoint
keeps its canonical order — scenarios are curated as ordered packs.
"""

from __future__ import annotations

import datetime as _dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.api.deps import get_optional_auth_user
from src.models.db import User
from src.services.style_catalog import (
    get_available_modes,
    get_catalog_json,
    get_catalog_json_v2,
    get_scenario_styles_json,
    get_scenario_styles_json_v2,
    get_style_options,
    get_style_options_v2,
    get_style_options_v3,
)

router = APIRouter()


def _derive_shuffle_seed(
    request: Request,
    user: User | None,
) -> str:
    """Compute a deterministic per-caller seed for the catalog shuffle.

    * Authenticated user → ``user:<uuid>`` (stable for the entire
      lifetime of the account, so the catalog ordering does not jump
      on page refresh; different users always see different
      permutations because UUIDs are unique).
    * Anonymous request → ``anon:<client_ip>:<utc_date>`` (stable
      within a single UTC day so styles don't flicker as the user
      scrolls; rotates daily so the order doesn't go stale forever
      for an anonymous visitor on a fixed IP).

    The ``:`` separator is intentional — it keeps the namespaces
    disjoint so the (extremely unlikely) case of a UUID that
    collides with an IP+date string does not produce the same seed.
    """
    if user is not None and getattr(user, "id", None) is not None:
        return f"user:{user.id}"

    client_ip = ""
    try:
        client_ip = (request.client.host if request.client else "") or ""
    except Exception:
        client_ip = ""
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    return f"anon:{client_ip}:{today}"


# v3 was added in Stage 3 of the prompt-pipeline-overhaul (2026-05).
# v1 / v2 / v3 are accepted; the options endpoint downgrades gracefully
# when the requested schema is not yet authored for a given style.
SchemaParam = Literal["v1", "v2", "v3"]


@router.get("/modes")
async def list_modes():
    """Return available analysis modes."""
    return {"modes": get_available_modes()}


@router.get("/styles")
async def list_styles(
    request: Request,
    mode: str = Query(..., description="Analysis mode: dating, cv, social"),
    schema: SchemaParam = Query(
        "v1",
        description=(
            "Catalog payload schema. ``v1`` (default) keeps the legacy "
            "shape; ``v2`` adds a per-entry ``schema_version`` field so "
            "clients know which styles expose slot-based options."
        ),
    ),
    user: User | None = Depends(get_optional_auth_user),
):
    """Return all styles for the given mode.

    The returned order is deterministic but **per-caller**: two
    different users see two different permutations, the same user
    always sees the same permutation (so styles do not jump on
    refresh). Anonymous callers get a per-IP / per-UTC-day seed.
    See :func:`_derive_shuffle_seed`.
    """
    shuffle_seed = _derive_shuffle_seed(request, user)
    if schema == "v2":
        items = get_catalog_json_v2(mode, shuffle_seed=shuffle_seed)
    else:
        items = get_catalog_json(mode, shuffle_seed=shuffle_seed)
    if not items:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {mode}")
    return {"mode": mode, "count": len(items), "styles": items, "schema": schema}


@router.get("/scenario-styles")
async def list_scenario_styles(
    scenario: str = Query(
        ...,
        description=(
            "Scenario slug. Returns styles whose ``scenario`` field "
            "matches this value (e.g. ``document-photo`` or "
            "``tinder-pack``). These styles are intentionally hidden "
            "from the main ``/styles?mode=...`` catalog."
        ),
    ),
    schema: SchemaParam = Query(
        "v1",
        description=(
            "Catalog payload schema. ``v2`` adds a per-entry "
            "``schema_version`` field, otherwise identical to v1."
        ),
    ),
):
    """Return styles bound to a specific scenario page."""
    if schema == "v2":
        items = get_scenario_styles_json_v2(scenario)
    else:
        items = get_scenario_styles_json(scenario)
    if not items:
        raise HTTPException(
            status_code=404, detail=f"Unknown scenario: {scenario}"
        )
    return {
        "scenario": scenario,
        "count": len(items),
        "styles": items,
        "schema": schema,
    }


@router.get("/styles/{style_id}/options")
async def get_options(
    style_id: str,
    schema: SchemaParam = Query(
        "v1",
        description=(
            "Options payload schema. ``v1`` returns the legacy "
            "``allowed_variations`` dict; ``v2`` returns the slot-based "
            "structure (context_slots / weather / clothing / background); "
            "``v3`` returns the v3 schema (trigger_pool, scene_anchor, "
            "scene_overrides, ambient pools per channel, clothing). When "
            "the requested schema is not yet authored for a given style "
            "the endpoint downgrades gracefully (v3 → v2 → v1)."
        ),
    ),
):
    """Return allowed variations (or v2 / v3 slots) for a specific style."""
    if schema == "v3":
        v3_payload = get_style_options_v3(style_id)
        if v3_payload is not None:
            return {
                "style_id": style_id,
                "schema_version": 3,
                "options": v3_payload,
            }
        # No v3 row yet — fall through to v2 + v1 like the v2 branch.
        schema = "v2"

    if schema == "v2":
        v2_payload = get_style_options_v2(style_id)
        if v2_payload is not None:
            return {
                "style_id": style_id,
                "schema_version": 2,
                "options": v2_payload,
            }
        legacy = get_style_options(style_id)
        if legacy is None:
            raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")
        return {
            "style_id": style_id,
            "schema_version": 1,
            "options": legacy,
        }

    options = get_style_options(style_id)
    if options is None:
        raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")
    return {"style_id": style_id, "options": options}

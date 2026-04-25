"""Admin CRUD for ``data/styles.json``.

Phase 5.3 of the catalog cleanup. Every endpoint here is gated by
:func:`src.api.v1.admin.auth.require_admin`, so unauthorised callers
get 403 before they touch the file.

Storage model: the JSON file remains the source of truth (PostgreSQL
migration is out of scope, see plan §"Что точно НЕ делаем"). Writes
go through :func:`src.services.style_store.save_styles`, which writes
atomically and refreshes the in-memory caches so subsequent
``/catalog/*`` and prompt builds see the change without a worker
restart.

Validation: payloads accept both v1 (flat scene fields) and v2 (slot
blocks) entries. When ``schema_version == 2`` the slot blocks are
re-shaped through the same loader used at startup
(:mod:`src.services.style_loader_v2`) so we fail-fast on malformed
slot data.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.v1.admin.auth import require_admin
from src.models.db import User
from src.services import style_store
from src.services.style_loader import load_styles_from_json

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic shapes — permissive on purpose
#
# The JSON catalog has accumulated a mix of v1 and v2 entries plus a
# few legacy fields (``is_scenario_only``, ``base_scene``, etc.). The
# admin schema mirrors that reality: only ``id`` + ``mode`` are
# required; everything else is optional and we round-trip unknown
# fields verbatim so legacy entries survive an edit unchanged.
# ---------------------------------------------------------------------------


class StyleCreatePayload(BaseModel):
    """Body for ``POST /admin/styles``.

    ``model_config(extra="allow")`` so callers can submit slot blocks
    (``background``, ``clothing``, ``weather``, ``context_slots``,
    ``quality_identity``) and any future fields without us having to
    redefine the schema for each migration.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1, max_length=120)
    mode: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    display_label: str = ""
    hook_text: str = ""
    scenario: str | None = None
    unlock_after_generations: int = 0
    is_scenario_only: bool = False
    schema_version: int = 1
    meta: dict[str, Any] = Field(default_factory=dict)


class StyleUpdatePayload(BaseModel):
    """Body for ``PUT /admin/styles/{id}``.

    Every field is optional — only the keys the caller sends are
    overwritten on the stored entry. ``id`` cannot be changed (rename
    = delete + create) so it is intentionally absent.
    """

    model_config = ConfigDict(extra="allow")

    mode: str | None = Field(None, pattern=r"^[a-z][a-z0-9_]*$")
    display_label: str | None = None
    hook_text: str | None = None
    scenario: str | None = None
    unlock_after_generations: int | None = None
    is_scenario_only: bool | None = None
    schema_version: int | None = None
    meta: dict[str, Any] | None = None


class StyleSummary(BaseModel):
    """Compact list-view row for the admin table."""

    id: str
    mode: str
    display_label: str
    hook_text: str
    scenario: str | None
    unlock_after_generations: int
    is_scenario_only: bool
    schema_version: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarise(entry: dict[str, Any]) -> StyleSummary:
    return StyleSummary(
        id=entry["id"],
        mode=entry.get("mode", ""),
        display_label=entry.get("display_label", ""),
        hook_text=entry.get("hook_text", ""),
        scenario=entry.get("scenario"),
        unlock_after_generations=int(entry.get("unlock_after_generations", 0) or 0),
        is_scenario_only=bool(entry.get("is_scenario_only", False)),
        schema_version=int(entry.get("schema_version") or 1),
    )


def _load_all() -> list[dict[str, Any]]:
    """Always read fresh from disk — admin views must not race the cache."""
    return list(style_store.load_styles_fresh())


def _validate_v2_shape(entry: dict[str, Any]) -> None:
    """Round-trip the entry through the v2 loader and enforce slot data.

    Only runs when ``schema_version == 2``. The startup loader is
    deliberately lenient (it would rather skip a broken style than
    crash the worker), but the admin path is the *write* side, so we
    surface any structural issue back to the caller as a 422 before
    the file is touched.

    On top of the loader round-trip we require:

    * the slot blocks (``background``, ``clothing``,
      ``quality_identity``) must be JSON objects, not bare strings
      or lists;
    * ``background.base`` must be a non-empty string — an empty scene
      description ships an unrenderable prompt;
    * ``clothing.default`` must be a non-empty string — without it the
      generator falls back to the wrong wardrobe and breaks the style;
    * ``quality_identity.base`` must be a non-empty string — this is
      the identity-anchor block that stops face drift across variants.
    """
    if int(entry.get("schema_version") or 0) != 2:
        return

    for key in ("background", "clothing", "quality_identity"):
        block = entry.get(key)
        if block is not None and not isinstance(block, dict):
            raise HTTPException(
                status_code=422,
                detail=f"v2 field {key!r} must be a JSON object",
            )

    bg = entry.get("background") or {}
    if not str(bg.get("base") or "").strip():
        raise HTTPException(
            status_code=422,
            detail="v2 styles require a non-empty background.base description",
        )

    clothing = entry.get("clothing") or {}
    if not str(clothing.get("default") or "").strip():
        raise HTTPException(
            status_code=422,
            detail="v2 styles require a non-empty clothing.default description",
        )

    quality = entry.get("quality_identity") or {}
    if not str(quality.get("base") or "").strip():
        raise HTTPException(
            status_code=422,
            detail="v2 styles require a non-empty quality_identity.base description",
        )

    from src.services.style_loader_v2 import _to_v2

    try:
        spec = _to_v2(entry)
    except Exception as exc:  # noqa: BLE001 — surface details to the caller
        raise HTTPException(
            status_code=422,
            detail=f"Invalid v2 slot data: {exc}",
        ) from exc
    if spec is None:
        raise HTTPException(
            status_code=422,
            detail="Failed to parse entry as a valid v2 style spec",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/styles", response_model=list[StyleSummary])
async def list_styles(_admin: User = Depends(require_admin)):
    """Return every style with the fields needed by the admin table."""
    return [_summarise(s) for s in _load_all()]


@router.get("/styles/{style_id}")
async def get_style(style_id: str, _admin: User = Depends(require_admin)):
    """Return the full raw entry — admin needs every field for the editor."""
    for s in _load_all():
        if s.get("id") == style_id:
            return s
    raise HTTPException(status_code=404, detail=f"Unknown style: {style_id}")


@router.post("/styles", status_code=201)
async def create_style(
    payload: StyleCreatePayload,
    _admin: User = Depends(require_admin),
):
    """Append a new style. Fails 409 if ``id`` already exists."""
    entry = payload.model_dump(exclude_none=False)
    styles = _load_all()
    if any(s.get("id") == entry["id"] for s in styles):
        raise HTTPException(
            status_code=409, detail=f"Style {entry['id']!r} already exists"
        )

    _validate_v2_shape(entry)

    styles.append(entry)
    style_store.save_styles(styles)
    logger.info("admin: created style %s", entry["id"])
    return entry


@router.put("/styles/{style_id}")
async def update_style(
    style_id: str,
    payload: StyleUpdatePayload,
    _admin: User = Depends(require_admin),
):
    """Partial update. Only keys present in the body are overwritten."""
    styles = _load_all()
    for i, entry in enumerate(styles):
        if entry.get("id") != style_id:
            continue
        patch = payload.model_dump(exclude_unset=True)
        merged = {**entry, **patch}
        # ``id`` is immutable — silently drop any attempt to change it
        # (the route param is the source of truth).
        merged["id"] = style_id
        _validate_v2_shape(merged)
        styles[i] = merged
        style_store.save_styles(styles)
        logger.info("admin: updated style %s (%d fields)", style_id, len(patch))
        return merged
    raise HTTPException(status_code=404, detail=f"Unknown style: {style_id}")


@router.delete("/styles/{style_id}", status_code=204)
async def delete_style(style_id: str, _admin: User = Depends(require_admin)):
    styles = _load_all()
    keep = [s for s in styles if s.get("id") != style_id]
    if len(keep) == len(styles):
        raise HTTPException(status_code=404, detail=f"Unknown style: {style_id}")
    style_store.save_styles(keep)
    logger.info("admin: deleted style %s", style_id)
    return None


@router.post("/styles/reload", status_code=200)
async def reload_styles(_admin: User = Depends(require_admin)):
    """Force a cache refresh after an out-of-band edit of the JSON file."""
    style_store.invalidate_caches()
    fresh = load_styles_from_json()
    return {"status": "ok", "count": len(fresh)}

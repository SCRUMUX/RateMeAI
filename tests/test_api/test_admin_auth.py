"""1.55.4 — coverage for the upgraded admin gate.

Adds tests for:

1. ``ADMIN_EMAILS`` parsing (lower-case + whitespace normalisation),
   confirming changes are picked up without the old ``lru_cache``
   that pinned the first parsed value for the lifetime of the process.
2. ``require_admin`` accepting/rejecting based on either whitelist.
3. The new ``GET /api/v1/admin/_whoami`` diagnostic endpoint —
   verifies that ``matched_via`` correctly distinguishes UUID match,
   email match, and the no-match case (which is why the operator
   was getting silent 403s before this work).

These tests intentionally avoid a real Postgres: the gate is purely
a string-set lookup on ``settings.admin_*`` plus a mocked DB query
for the user's identities.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from src.api.v1.admin import auth as admin_auth


def _mock_identity_rows(emails: list[str | None]) -> MagicMock:
    """Build a MagicMock that mimics ``db.execute().scalars().all()``
    returning identity rows whose ``profile_data['email']`` is the
    sequence supplied."""
    identities = [
        SimpleNamespace(profile_data={"email": e} if e else {})
        for e in emails
    ]
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = identities
    return rows


# ---------------------------------------------------------------------------
# ADMIN_EMAILS parser
# ---------------------------------------------------------------------------


def test_admin_emails_parser_normalises_case_and_whitespace(monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.admin_emails",
        " Alice@Example.COM ,  bob@x.io,, ",
        raising=False,
    )
    emails = admin_auth.get_admin_emails()
    assert emails == frozenset({"alice@example.com", "bob@x.io"})


def test_admin_emails_parser_returns_empty_for_blank(monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.admin_emails", "", raising=False
    )
    assert admin_auth.get_admin_emails() == frozenset()


def test_admin_emails_picks_up_settings_change_without_restart(monkeypatch):
    """The 1.55.4 reason for dropping ``lru_cache``: a deploy that
    writes ``ADMIN_EMAILS`` AFTER the FastAPI app started used to be
    invisible until process restart, because the cache pinned the
    first (empty) parsed value."""
    monkeypatch.setattr(
        "src.config.settings.admin_emails", "", raising=False
    )
    assert admin_auth.get_admin_emails() == frozenset()

    monkeypatch.setattr(
        "src.config.settings.admin_emails",
        "ops@x.io",
        raising=False,
    )
    assert admin_auth.get_admin_emails() == frozenset({"ops@x.io"})


# ---------------------------------------------------------------------------
# require_admin — email path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_admin_accepts_email_match(monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", "", raising=False
    )
    monkeypatch.setattr(
        "src.config.settings.admin_emails",
        "ops@x.io,boss@y.org",
        raising=False,
    )
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    db.execute = AsyncMock(return_value=_mock_identity_rows(["ops@x.io"]))

    result = await admin_auth.require_admin(user=user, db=db)
    assert result is user


@pytest.mark.asyncio
async def test_require_admin_rejects_when_email_not_in_whitelist(monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", "", raising=False
    )
    monkeypatch.setattr(
        "src.config.settings.admin_emails", "boss@y.org", raising=False
    )
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    db.execute = AsyncMock(return_value=_mock_identity_rows(["random@x.io"]))

    with pytest.raises(HTTPException) as exc:
        await admin_auth.require_admin(user=user, db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_email_check_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", "", raising=False
    )
    monkeypatch.setattr(
        "src.config.settings.admin_emails", "Ops@x.IO", raising=False
    )
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    db.execute = AsyncMock(return_value=_mock_identity_rows(["ops@x.io"]))

    result = await admin_auth.require_admin(user=user, db=db)
    assert result is user


@pytest.mark.asyncio
async def test_require_admin_email_path_skipped_when_whitelist_empty(monkeypatch):
    """Empty ``ADMIN_EMAILS`` must NOT issue a DB lookup — saves a
    round-trip per request when only the UUID whitelist is in use."""
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", "uid-1", raising=False
    )
    monkeypatch.setattr(
        "src.config.settings.admin_emails", "", raising=False
    )
    user = SimpleNamespace(id="uid-1")
    db = MagicMock()
    db.execute = AsyncMock()  # would blow up if called

    result = await admin_auth.require_admin(user=user, db=db)
    assert result is user
    db.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# /admin/_whoami diagnostic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whoami_reports_email_match(monkeypatch):
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", "", raising=False
    )
    monkeypatch.setattr(
        "src.config.settings.admin_emails",
        "ops@x.io",
        raising=False,
    )
    uid = uuid4()
    user = SimpleNamespace(id=uid)
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_mock_identity_rows(["ops@x.io", "personal@gmail.com"])
    )

    res = await admin_auth.admin_whoami(user=user, db=db)

    assert res["user_id"] == str(uid)
    assert res["is_admin"] is True
    assert res["matched_via"] == "email"
    assert "ops@x.io" in res["identity_emails"]
    assert res["whitelist_size"] == {"user_ids": 0, "emails": 1}


@pytest.mark.asyncio
async def test_whoami_reports_user_id_match(monkeypatch):
    """UUID match short-circuits — DB still returns identities for
    informational purposes, but ``matched_via`` reports the UUID
    path."""
    uid_obj: UUID = uuid4()
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", str(uid_obj), raising=False
    )
    monkeypatch.setattr(
        "src.config.settings.admin_emails", "", raising=False
    )
    user = SimpleNamespace(id=uid_obj)
    db = MagicMock()
    db.execute = AsyncMock(return_value=_mock_identity_rows([]))

    res = await admin_auth.admin_whoami(user=user, db=db)
    assert res["is_admin"] is True
    assert res["matched_via"] == "user_id"
    assert res["whitelist_size"] == {"user_ids": 1, "emails": 0}


@pytest.mark.asyncio
async def test_whoami_reports_no_match_with_empty_whitelists(monkeypatch):
    """The exact case that broke the RU admin: both whitelists empty
    on the running container. ``_whoami`` must surface this clearly
    so the operator knows the env vars never made it in, instead of
    hunting through 403 responses."""
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", "", raising=False
    )
    monkeypatch.setattr(
        "src.config.settings.admin_emails", "", raising=False
    )
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_mock_identity_rows(["legitimate@admin.com"])
    )

    res = await admin_auth.admin_whoami(user=user, db=db)
    assert res["is_admin"] is False
    assert res["matched_via"] is None
    assert res["whitelist_size"] == {"user_ids": 0, "emails": 0}
    # Identity emails surfaced even with empty whitelist — that's how
    # the SPA banner shows "your email is X but the whitelist is empty"
    assert "legitimate@admin.com" in res["identity_emails"]


@pytest.mark.asyncio
async def test_whoami_reports_user_with_no_email_identity(monkeypatch):
    """The 'Yandex without login:email scope' / phone-login case.
    Whitelist non-empty, but the user has no email-bearing identity,
    so they can never pass the gate. ``_whoami`` must say so plainly."""
    monkeypatch.setattr(
        "src.config.settings.admin_user_ids", "", raising=False
    )
    monkeypatch.setattr(
        "src.config.settings.admin_emails",
        "ops@x.io",
        raising=False,
    )
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    db.execute = AsyncMock(return_value=_mock_identity_rows([None, None]))

    res = await admin_auth.admin_whoami(user=user, db=db)
    assert res["is_admin"] is False
    assert res["matched_via"] is None
    assert res["identity_emails"] == []
    assert res["whitelist_size"]["emails"] == 1

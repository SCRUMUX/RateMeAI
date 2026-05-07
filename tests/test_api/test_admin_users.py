"""Unit tests for the session-admin Users tab.

These exercise the route handlers in ``src.api.v1.admin.users``
directly, mocking the ``AsyncSession`` rather than bringing up a
real Postgres. The goal is to lock in:

1. Pydantic-level validation (zero amount, |amount| > MAX, missing
   reason, refund credits ≤ 0).
2. The ``insufficient_credits`` 400 path for both ``adjust_credits``
   (negative debit) and ``refund_credits``.
3. The 404 path when the user UUID is unknown.
4. The strict no-photo-paths invariant on ``GET /users/{id}`` —
   ``input_image_path``/``share_card_path`` must not appear in the
   response, even when the underlying ``Task`` row has them set.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.api.v1.admin import users as admin_users


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


def test_adjust_request_rejects_missing_reason():
    with pytest.raises(ValidationError):
        admin_users.AdjustCreditsRequest(amount=10)


def test_adjust_request_accepts_negative_amount():
    payload = admin_users.AdjustCreditsRequest(amount=-5, reason="chargeback")
    assert payload.amount == -5
    assert payload.reason == "chargeback"


def test_refund_request_rejects_zero_or_negative_credits():
    with pytest.raises(ValidationError):
        admin_users.RefundRequest(credits=0, note="bad")
    with pytest.raises(ValidationError):
        admin_users.RefundRequest(credits=-1, note="bad")


def test_refund_request_caps_at_max_amount():
    with pytest.raises(ValidationError):
        admin_users.RefundRequest(
            credits=admin_users.MAX_AMOUNT + 1, note="too much"
        )


def test_refund_request_requires_note_min_length():
    with pytest.raises(ValidationError):
        admin_users.RefundRequest(credits=5, note="ok")


# ---------------------------------------------------------------------------
# Helper: build a mock AsyncSession that returns canned ``execute`` results
# ---------------------------------------------------------------------------


def _scalar_one_or_none_result(value):
    res = MagicMock()
    res.scalar_one_or_none.return_value = value
    return res


def _make_db(*, user, transactions=None, tasks_rows=None, identities=None):
    """Sequence of ``execute`` call results matching ``get_user`` flow."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()

    # ``get_user`` calls db.execute in this order:
    # 1) load user
    # 2) _aggregate_for_users → identities
    # 3) _aggregate_for_users → counts
    # 4) _aggregate_for_users → last_seen
    # 5) credit_transactions
    # 6) tasks columns
    user_res = _scalar_one_or_none_result(user)

    idents_res = MagicMock()
    idents_res.scalars.return_value.all.return_value = identities or []

    counts_res = MagicMock()
    counts_res.all.return_value = []

    seen_res = MagicMock()
    seen_res.all.return_value = []

    tx_res = MagicMock()
    tx_res.scalars.return_value.all.return_value = transactions or []

    tasks_res = MagicMock()
    tasks_res.all.return_value = tasks_rows or []

    db.execute.side_effect = [
        user_res,
        idents_res,
        counts_res,
        seen_res,
        tx_res,
        tasks_res,
    ]
    return db


# ---------------------------------------------------------------------------
# adjust_credits — handler-level coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adjust_credits_rejects_zero_amount():
    payload = admin_users.AdjustCreditsRequest.model_construct(
        amount=0, reason="zero"
    )
    user_id = str(uuid4())
    with pytest.raises(HTTPException) as exc:
        await admin_users.adjust_credits(
            user_id=user_id,
            payload=payload,
            admin=SimpleNamespace(id=uuid4()),
            db=MagicMock(),
        )
    assert exc.value.status_code == 400
    assert "non-zero" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_adjust_credits_rejects_overflow():
    payload = admin_users.AdjustCreditsRequest.model_construct(
        amount=admin_users.MAX_AMOUNT + 1, reason="too big"
    )
    with pytest.raises(HTTPException) as exc:
        await admin_users.adjust_credits(
            user_id=str(uuid4()),
            payload=payload,
            admin=SimpleNamespace(id=uuid4()),
            db=MagicMock(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_adjust_credits_404_when_user_missing():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_one_or_none_result(None))
    payload = admin_users.AdjustCreditsRequest(amount=5, reason="manual")
    with pytest.raises(HTTPException) as exc:
        await admin_users.adjust_credits(
            user_id=str(uuid4()),
            payload=payload,
            admin=SimpleNamespace(id=uuid4()),
            db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_adjust_credits_400_insufficient_for_negative_below_balance():
    user = SimpleNamespace(
        id=uuid4(), image_credits=3, telegram_id=None, username=None
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_one_or_none_result(user))
    payload = admin_users.AdjustCreditsRequest(amount=-5, reason="charge")
    with pytest.raises(HTTPException) as exc:
        await admin_users.adjust_credits(
            user_id=str(user.id),
            payload=payload,
            admin=SimpleNamespace(id=uuid4()),
            db=db,
        )
    assert exc.value.status_code == 400
    detail = exc.value.detail
    assert isinstance(detail, dict) and detail.get("code") == "insufficient_credits"
    assert detail.get("balance") == 3


@pytest.mark.asyncio
async def test_adjust_credits_grants_and_records_transaction():
    user = SimpleNamespace(
        id=uuid4(),
        image_credits=10,
        telegram_id=None,
        username=None,
        first_name=None,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_one_or_none_result(user))
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    payload = admin_users.AdjustCreditsRequest(
        amount=7, reason="manual top-up"
    )

    result = await admin_users.adjust_credits(
        user_id=str(user.id),
        payload=payload,
        admin=SimpleNamespace(id=uuid4()),
        db=db,
    )

    assert result["status"] == "ok"
    assert result["tx_type"] == "admin_grant"
    assert result["before"] == 10
    assert result["after"] == 17
    assert result["amount"] == 7
    assert user.image_credits == 17

    db.add.assert_called_once()
    tx = db.add.call_args[0][0]
    assert tx.amount == 7
    assert tx.balance_after == 17
    assert tx.tx_type == "admin_grant"
    assert tx.payment_id == "manual top-up"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_adjust_credits_debits_with_admin_debit_tx_type():
    user = SimpleNamespace(
        id=uuid4(),
        image_credits=20,
        telegram_id=None,
        username=None,
        first_name=None,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_one_or_none_result(user))
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    payload = admin_users.AdjustCreditsRequest(amount=-5, reason="cleanup")

    result = await admin_users.adjust_credits(
        user_id=str(user.id),
        payload=payload,
        admin=SimpleNamespace(id=uuid4()),
        db=db,
    )

    assert result["tx_type"] == "admin_debit"
    assert result["after"] == 15
    tx = db.add.call_args[0][0]
    assert tx.amount == -5
    assert tx.tx_type == "admin_debit"


# ---------------------------------------------------------------------------
# refund_credits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refund_credits_404_when_user_missing():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_one_or_none_result(None))
    payload = admin_users.RefundRequest(credits=5, note="customer asked")
    with pytest.raises(HTTPException) as exc:
        await admin_users.refund_credits(
            user_id=str(uuid4()),
            payload=payload,
            admin=SimpleNamespace(id=uuid4()),
            db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_refund_credits_400_insufficient_balance():
    user = SimpleNamespace(
        id=uuid4(),
        image_credits=2,
        telegram_id=None,
        username=None,
        first_name=None,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_one_or_none_result(user))
    payload = admin_users.RefundRequest(credits=10, note="customer asked")
    with pytest.raises(HTTPException) as exc:
        await admin_users.refund_credits(
            user_id=str(user.id),
            payload=payload,
            admin=SimpleNamespace(id=uuid4()),
            db=db,
        )
    assert exc.value.status_code == 400
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == "insufficient_credits"


@pytest.mark.asyncio
async def test_refund_credits_records_admin_refund_tx():
    user = SimpleNamespace(
        id=uuid4(),
        image_credits=20,
        telegram_id=None,
        username=None,
        first_name=None,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_one_or_none_result(user))
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    payload = admin_users.RefundRequest(
        credits=3, payment_id="pay_abc", note="duplicate purchase"
    )

    result = await admin_users.refund_credits(
        user_id=str(user.id),
        payload=payload,
        admin=SimpleNamespace(id=uuid4()),
        db=db,
    )

    assert result["status"] == "ok"
    assert result["tx_type"] == "admin_refund"
    assert result["before"] == 20
    assert result["after"] == 17
    assert result["credits"] == 3

    tx = db.add.call_args[0][0]
    assert tx.tx_type == "admin_refund"
    assert tx.amount == -3
    assert tx.balance_after == 17
    assert "pay_abc" in tx.payment_id
    assert "duplicate purchase" in tx.payment_id


# ---------------------------------------------------------------------------
# get_user — invariants on photo paths and shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_404_for_unknown_id():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_one_or_none_result(None))
    with pytest.raises(HTTPException) as exc:
        await admin_users.get_user(
            user_id=str(uuid4()),
            _admin=SimpleNamespace(id=uuid4()),
            db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_user_400_for_invalid_uuid():
    with pytest.raises(HTTPException) as exc:
        await admin_users.get_user(
            user_id="not-a-uuid",
            _admin=SimpleNamespace(id=uuid4()),
            db=MagicMock(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_user_response_omits_image_paths():
    user = SimpleNamespace(
        id=uuid4(),
        telegram_id=None,
        username="joe",
        first_name=None,
        is_premium=False,
        image_credits=5,
        created_at=datetime.now(timezone.utc),
    )
    # tasks_q returns column-tuples — note the absence of image-path
    # columns. The handler MUST mirror that: response['tasks'][i]
    # should never contain ``input_image_path`` / ``share_card_path``.
    task_id = uuid4()
    tasks_rows = [
        (task_id, "social", "completed",
         datetime.now(timezone.utc), datetime.now(timezone.utc), None)
    ]
    db = _make_db(user=user, tasks_rows=tasks_rows)

    response = await admin_users.get_user(
        user_id=str(user.id),
        _admin=SimpleNamespace(id=uuid4()),
        db=db,
    )

    assert response["user"]["id"] == str(user.id)
    assert response["tasks"][0]["id"] == str(task_id)
    assert "input_image_path" not in response["tasks"][0]
    assert "share_card_path" not in response["tasks"][0]


# ---------------------------------------------------------------------------
# admin_lookup.search_users_by_query — at least smoke-test the empty path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_users_empty_query_returns_recent_users():
    from src.services import admin_lookup

    db = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = ["user-A", "user-B"]
    res = MagicMock()
    res.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=res)

    rows = await admin_lookup.search_users_by_query(db, q="", limit=10)
    assert rows == ["user-A", "user-B"]
    db.execute.assert_awaited_once()

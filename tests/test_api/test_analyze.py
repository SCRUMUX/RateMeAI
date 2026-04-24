from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

_CONSENT_HEADERS = {
    "X-Consent-Data-Processing": "1",
    "X-Consent-AI-Transfer": "1",
    "X-Consent-Age-16": "1",
}


def _valid_jpeg(size: tuple[int, int] = (1024, 1024)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(128, 128, 128)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


_VALID_JPEG = _valid_jpeg()


def _register_user(client, telegram_id: int = 999001) -> str:
    """Register user and return Bearer token."""
    r = client.post(
        "/api/v1/auth/telegram",
        json={"telegram_id": telegram_id, "username": "tester", "first_name": "Test"},
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **_CONSENT_HEADERS}


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_create_analysis_returns_202(mock_get_storage, mock_get_arq, client):
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage

    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999002)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "rating"},
        headers=_auth(token),
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert "task_id" in body
    pool.enqueue_job.assert_awaited()


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_get_task_after_create(mock_get_storage, mock_get_arq, client):
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    tid = 999003
    token = _register_user(client, telegram_id=tid)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "dating"},
        headers=_auth(token),
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]

    r2 = client.get(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["task_id"] == task_id
    assert data["status"] == "pending"
    assert data["mode"] == "dating"


def test_analyze_without_consent_returns_451(client):
    token = _register_user(client, telegram_id=999004)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "rating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 451, r.text
    detail = r.json().get("detail", {})
    assert detail.get("code") == "consent_required"
    missing = detail.get("missing") or []
    assert "data_processing" in missing
    assert "ai_transfer" in missing


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_primary_ui_flow_does_not_mark_delete_after_process(
    mock_get_storage, mock_get_arq, client
):
    """Regression (v1.26.2): primary UI-запрос к ``/api/v1/analyze`` НЕ должен
    помечать созданный ``Task`` флагом ``delete_after_process=True``.

    Раньше флаг стоял и вызывал в ``_cleanup_ephemeral_artifacts`` мгновенное
    удаление Redis-ключа + файла сразу после ``COMPLETED`` (на Railway это
    означало потерю картинки, так как ``app`` и ``worker`` — разные
    контейнеры без общего volume: Redis был единственным каналом выдачи
    файла в UI). См. баг-репорт «хранилище всегда 0, фото пропадает
    после перезагрузки».
    """
    import asyncio

    from sqlalchemy import select

    from src.models.db import Task
    from src.services.task_contract import should_delete_after_process

    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage

    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999005)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "rating"},
        headers=_auth(token),
    )
    assert r.status_code == 202, r.text
    task_id = r.json()["task_id"]

    sessionmaker = client.app.state.db_sessionmaker

    async def _fetch_task_context() -> dict:
        async with sessionmaker() as db:
            row = await db.execute(select(Task).where(Task.id == task_id))
            tsk = row.scalar_one()
            return tsk.context or {}

    ctx = asyncio.get_event_loop().run_until_complete(_fetch_task_context())
    flags = ctx.get("policy_flags") or {}
    assert flags.get("delete_after_process") is False, (
        "primary UI-поток обязан создавать задачу без delete_after_process "
        "(иначе worker мгновенно чистит Redis+диск и картинка теряется)"
    )
    assert should_delete_after_process(ctx) is False


@patch("src.api.v1.analyze._get_arq", new_callable=AsyncMock)
@patch("src.api.v1.analyze.get_storage")
def test_get_task_strips_generated_image_b64_from_response(
    mock_get_storage, mock_get_arq, client
):
    """``GET /api/v1/tasks/{id}`` не должен возвращать сырые байты
    ``generated_image_b64`` в JSON — фронт тянет картинку через
    ``/storage/...``, а полингу эти ~200 КБ b64 на каждом тике не нужны.
    С v1.26.2 b64 всегда пишется в DB как надёжный fallback, поэтому
    стрипаем его именно в API-слое.
    """
    import asyncio

    from sqlalchemy import select

    from src.models.db import Task
    from src.models.enums import TaskStatus

    storage = MagicMock()
    storage.upload = AsyncMock(return_value="inputs/u/k.jpg")
    mock_get_storage.return_value = storage
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    mock_get_arq.return_value = pool

    token = _register_user(client, telegram_id=999006)

    r = client.post(
        "/api/v1/analyze",
        files={"image": ("x.jpg", _VALID_JPEG, "image/jpeg")},
        data={"mode": "rating"},
        headers=_auth(token),
    )
    assert r.status_code == 202, r.text
    task_id = r.json()["task_id"]

    fake_b64 = "Zm9vYmFyYmF6" * 50
    sessionmaker = client.app.state.db_sessionmaker

    async def _seed_completed_result() -> None:
        async with sessionmaker() as db:
            row = await db.execute(select(Task).where(Task.id == task_id))
            tsk = row.scalar_one()
            tsk.status = TaskStatus.COMPLETED.value
            tsk.result = {
                "score": 7.1,
                "generated_image_url": f"http://test/storage/generated/u/{task_id}.jpg",
                "generated_image_b64": fake_b64,
            }
            await db.commit()

    asyncio.get_event_loop().run_until_complete(_seed_completed_result())

    r2 = client.get(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["status"] == "completed"
    result = data.get("result") or {}
    assert "generated_image_b64" not in result, (
        "API must strip the raw base64 — фронт получает картинку через "
        "/storage/, а b64 раздувает JSON и логи"
    )
    assert result.get("generated_image_url", "").endswith(f"{task_id}.jpg")

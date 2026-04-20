import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware as _BaseHTTP
from starlette.requests import Request as _Req
from starlette.responses import Response as _Resp

from prometheus_fastapi_instrumentator import Instrumentator

from src.config import settings
from src.api.router import api_router
from src.api.middleware import RequestLoggingMiddleware
from src.version import APP_VERSION


def _configure_logging() -> None:
    from src.utils.log_filters import PIIFilter

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler()

    if settings.is_production:
        from pythonjsonlogger import jsonlogger
        handler.setFormatter(jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        ))
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        ))

    pii_filter = PIIFilter()
    handler.addFilter(pii_filter)
    root.addFilter(pii_filter)
    root.addHandler(handler)


_configure_logging()

_EDGE_RECONCILE_INTERVAL = 300  # 5 minutes


async def _edge_reconciler_loop(db_sessionmaker, redis: Redis) -> None:
    """Periodically mark stuck PROCESSING tasks as FAILED on the edge server."""
    from src.services.reconciliation import reconcile_stuck_tasks

    log = logging.getLogger("edge_reconciler")
    await asyncio.sleep(60)  # initial delay
    while True:
        try:
            await reconcile_stuck_tasks(db_sessionmaker, redis, source="edge")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Edge reconciler iteration failed")

        await asyncio.sleep(_EDGE_RECONCILE_INTERVAL)


def _run_alembic_upgrade() -> None:
    from alembic.config import Config
    from alembic import command

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_production:
        await asyncio.to_thread(_run_alembic_upgrade)
        logging.getLogger(__name__).info(
            "Alembic migrations applied (mode=%s)", settings.deployment_mode,
        )

    engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=20)

    if not settings.is_production:
        from src.models.db import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logging.getLogger(__name__).info("DB tables ensured (dev create_all)")

    app.state.db_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    if settings.internal_api_key and not settings.uses_remote_ai:
        from src.models.db import User
        import uuid as _uuid
        internal_user_id = _uuid.uuid5(_uuid.NAMESPACE_DNS, "edge-proxy.internal")
        async with app.state.db_sessionmaker() as _db:
            existing = await _db.get(User, internal_user_id)
            if not existing:
                _db.add(User(
                    id=internal_user_id,
                    username="__edge_proxy__",
                    image_credits=999_999,
                ))
                await _db.commit()
                logging.getLogger(__name__).info("Created internal edge-proxy user %s", internal_user_id)

    log = logging.getLogger(__name__)
    if settings.is_production and not settings.openrouter_api_key.strip() and not settings.uses_remote_ai:
        log.error(
            "OPENROUTER_API_KEY is empty — configure env before accepting traffic",
        )
    if settings.is_production and "localhost" in settings.api_base_url:
        log.error(
            "API_BASE_URL contains 'localhost' in production (%s) — "
            "image URLs will be broken for clients",
            settings.api_base_url,
        )
    # YooKassa hard gate: на primary не должно быть ни shop_id, ни secret_key.
    # Это критично — иначе случайные/тестовые креды в env превращают боевой
    # домен в «тестовый ЮKassa», и реальные пользователи получают ссылку на
    # «Это тестовый платёж / yoomoney.ru Test», а деньги оседают в тестовом
    # кабинете. ЮKassa принимает вебхуки только с российских IP, так что
    # платёжный контур живёт исключительно на RU-edge.
    if not settings.is_edge:
        leftover_shop = settings.yookassa_shop_id.strip()
        leftover_key = settings.yookassa_secret_key.strip()
        if leftover_shop or leftover_key:
            log.error(
                "YooKassa credentials are set on a non-edge deployment "
                "(shop_id_present=%s, secret_present=%s) — nullifying in memory "
                "and refusing to create any payments here. YooKassa must run "
                "only on DEPLOYMENT_MODE=edge.",
                bool(leftover_shop), bool(leftover_key),
            )
            settings.yookassa_shop_id = ""
            settings.yookassa_secret_key = ""

    if settings.uses_remote_ai:
        if not settings.vk_id_app_id.strip():
            log.warning("VK_ID_APP_ID is empty — VK ID OAuth will not work on edge")
        if not settings.vk_app_secret.strip():
            log.warning("VK_APP_SECRET is empty — VK Mini App auth will not work on edge")
        if not settings.ok_app_secret_key.strip():
            log.warning("OK_APP_SECRET_KEY is empty — OK Mini App auth will not work on edge")
        if not settings.remote_ai_backend_url.strip():
            log.error("REMOTE_AI_BACKEND_URL is empty — edge cannot proxy AI requests to primary")
        if not settings.internal_api_key.strip():
            log.error("INTERNAL_API_KEY is empty — edge-primary communication will fail")
    sha = (settings.deploy_git_sha or "").strip()
    log.info(
        "RateMeAI API starting version=%s market=%s role=%s compute=%s mode=%s%s",
        APP_VERSION,
        settings.resolved_market_id,
        settings.resolved_service_role,
        settings.resolved_compute_mode,
        settings.deployment_mode,
        f" git={sha[:12]}" if sha else "",
    )
    if settings.uses_remote_ai:
        log.info("Edge mode: AI requests will be proxied to %s", settings.remote_ai_backend_url)

    reconciler_task = None
    if settings.uses_remote_ai:
        reconciler_task = asyncio.create_task(
            _edge_reconciler_loop(app.state.db_sessionmaker, app.state.redis)
        )

    yield

    if reconciler_task and not reconciler_task.done():
        reconciler_task.cancel()
        try:
            await reconciler_task
        except asyncio.CancelledError:
            pass

    if settings.uses_remote_ai:
        from src.services import remote_ai as _rai_mod
        if _rai_mod._instance is not None:
            await _rai_mod._instance.close()

    await app.state.redis.close()
    await engine.dispose()


app = FastAPI(
    title="RateMEAI",
    description="AI-powered perception & identity transformation platform",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
if settings.is_production:
    _origins = [
        "https://ratemeai.com",
        "https://ailookstudio.ru",
        "https://www.ailookstudio.ru",
        "https://ailookstudio.vercel.app",
        "https://ru.ailookstudio.ru",
    ]
    if settings.cors_extra_origins:
        _origins.extend(
            o.strip() for o in settings.cors_extra_origins.split(",") if o.strip()
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_origin_regex=r"https://.*\.up\.railway\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class _IframeHeadersMiddleware(_BaseHTTP):
    """Allow embedding in OK / VK mini app iframes."""
    async def dispatch(self, request: _Req, call_next) -> _Resp:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "ALLOWALL"
        response.headers.setdefault(
            "Content-Security-Policy",
            "frame-ancestors 'self' https://*.ok.ru https://*.odnoklassniki.ru https://*.vk.com",
        )
        return response


app.add_middleware(_IframeHeadersMiddleware)
app.include_router(api_router, prefix="/api/v1")

_instrumentator = Instrumentator()
_instrumentator.instrument(app)

if settings.is_production:
    from fastapi import HTTPException as _HTTPExc

    @app.get("/metrics")
    async def _protected_metrics(request: _Req):
        auth = request.headers.get("authorization", "")
        metrics_token = settings.internal_api_key
        if metrics_token and not auth.endswith(metrics_token):
            raise _HTTPExc(status_code=403, detail="Forbidden")
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        return _Resp(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
else:
    _instrumentator.expose(app, endpoint="/metrics")

storage_dir = Path(settings.storage_local_path).resolve()
storage_dir.mkdir(parents=True, exist_ok=True)


@app.get("/storage/{file_path:path}")
async def serve_storage(file_path: str, download: int = 0):
    """Serve files from local storage with Redis fallback for generated images."""
    import base64
    import re
    from fastapi.responses import Response
    from src.utils.redis_keys import gen_image_cache_keys

    _CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}
    _CACHE_IMMUTABLE = "public, max-age=86400, immutable"

    def _headers(filename: str, *, cache: bool = True) -> dict[str, str]:
        h: dict[str, str] = {**_CORS_HEADERS}
        if cache:
            h["Cache-Control"] = _CACHE_IMMUTABLE
        if download:
            h["Content-Disposition"] = f'attachment; filename="{filename}"'
        return h

    local_path = (storage_dir / file_path).resolve()
    if not str(local_path).startswith(str(storage_dir)):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Invalid path"}, status_code=400, headers=_CORS_HEADERS)
    if local_path.exists() and local_path.is_file():
        import mimetypes
        ct = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
        return Response(
            content=local_path.read_bytes(),
            media_type=ct,
            headers=_headers(local_path.name),
        )

    m = re.search(r"generated/[^/]+/([0-9a-f\-]{36})\.jpg", file_path)
    if m:
        task_id = m.group(1)

        redis: Redis = app.state.redis
        # Writers scope the key by market_id after the geo-split refactor;
        # probe both the scoped and legacy keys so the route keeps serving
        # cached bytes regardless of which writer produced them.
        for cache_key in gen_image_cache_keys(task_id, settings.resolved_market_id):
            b64 = await redis.get(cache_key)
            if b64:
                data = base64.b64decode(b64)
                return Response(
                    content=data,
                    media_type="image/jpeg",
                    headers=_headers(f"{task_id}.jpg"),
                )

        try:
            from sqlalchemy import select as sa_select
            from src.models.db import Task
            async with app.state.db_sessionmaker() as db:
                row = await db.execute(
                    sa_select(Task).where(Task.id == task_id)
                )
                task_obj = row.scalar_one_or_none()
                if task_obj and task_obj.result:
                    b64_fb = task_obj.result.get("generated_image_b64")
                    if b64_fb:
                        data = base64.b64decode(b64_fb)
                        return Response(
                            content=data,
                            media_type="image/jpeg",
                            headers=_headers(f"{task_id}.jpg"),
                        )
        except Exception:
            logging.getLogger(__name__).exception("DB fallback failed for %s", task_id)

    from fastapi.responses import JSONResponse
    return JSONResponse(
        {"detail": "Not found"},
        status_code=404,
        headers=_CORS_HEADERS,
    )


@app.get("/health")
async def health():
    body: dict = {
        "status": "ok",
        "version": APP_VERSION,
        "mode": settings.deployment_mode,
        "market_id": settings.resolved_market_id,
        "service_role": settings.resolved_service_role,
        "compute_mode": settings.resolved_compute_mode,
    }
    sha = (settings.deploy_git_sha or "").strip()
    if sha:
        body["git"] = sha[:12]
    return body


@app.get("/readiness")
async def readiness():
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    checks: dict[str, str] = {}
    checks["market_id"] = settings.resolved_market_id
    checks["service_role"] = settings.resolved_service_role
    checks["compute_mode"] = settings.resolved_compute_mode

    try:
        async with app.state.db_sessionmaker() as db:
            await db.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        checks["db"] = "fail"

    try:
        await app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "fail"

    if settings.uses_remote_ai:
        checks["mode"] = "edge"
        checks["remote_ai"] = "configured" if settings.remote_ai_backend_url else "missing"
        try:
            from src.services.remote_ai import get_remote_ai
            remote = get_remote_ai()
            resp = await remote._client.get(
                f"{remote._base.rsplit('/api/', 1)[0]}/health",
                timeout=10.0,
            )
            primary_data = resp.json()
            checks["primary_health"] = primary_data.get("status", "unknown")
            checks["primary_git"] = primary_data.get("git", "?")
        except Exception as exc:
            checks["primary_health"] = f"unreachable: {exc}"
        try:
            from src.services.remote_ai import get_remote_ai
            remote = get_remote_ai()
            ping_resp = await remote._client.get(
                f"{remote._base}/ping",
                headers={"X-Internal-Key": settings.internal_api_key},
                timeout=10.0,
            )
            ping_resp.raise_for_status()
            checks["primary_reachable"] = True
        except Exception as exc:
            checks["primary_reachable"] = False
            checks["primary_auth_error"] = str(exc)
    else:
        checks["openrouter_key"] = "ok" if settings.openrouter_api_key.strip() else "missing"
        try:
            from src.providers.factory import get_image_gen
            ig = get_image_gen()
            provider_name = type(ig).__name__
            checks["image_gen"] = provider_name
        except Exception as exc:
            checks["image_gen"] = f"fail: {exc}"

    ok = all(v not in ("fail", "missing") for v in checks.values())
    return JSONResponse(checks, status_code=200 if ok else 503)

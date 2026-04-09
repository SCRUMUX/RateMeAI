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

    root.addHandler(handler)


_configure_logging()


def _run_alembic_upgrade() -> None:
    from alembic.config import Config
    from alembic import command

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_production:
        await asyncio.to_thread(_run_alembic_upgrade)
        logging.getLogger(__name__).info("Alembic migrations applied")

    engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=20)

    if not settings.is_production:
        from src.models.db import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logging.getLogger(__name__).info("DB tables ensured (dev create_all)")

    app.state.db_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    log = logging.getLogger(__name__)
    if settings.is_production and not settings.openrouter_api_key.strip():
        log.error(
            "OPENROUTER_API_KEY is empty — configure env before accepting traffic",
        )
    sha = (settings.deploy_git_sha or "").strip()
    log.info(
        "RateMeAI API starting version=%s%s",
        APP_VERSION,
        f" git={sha[:12]}" if sha else "",
    )

    yield

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

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

storage_dir = Path(settings.storage_local_path).resolve()
storage_dir.mkdir(parents=True, exist_ok=True)


@app.get("/storage/{file_path:path}")
async def serve_storage(file_path: str, download: int = 0):
    """Serve files from local storage with Redis fallback for generated images."""
    import base64
    import re
    from fastapi.responses import Response
    from src.utils.redis_keys import gen_image_cache_key

    def _headers(filename: str) -> dict[str, str]:
        if download:
            return {"Content-Disposition": f'attachment; filename="{filename}"'}
        return {}

    local_path = storage_dir / file_path
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
        b64 = await redis.get(gen_image_cache_key(task_id))
        if b64:
            data = base64.b64decode(b64)
            return Response(
                content=data,
                media_type="image/jpeg",
                headers=_headers(f"{task_id}.jpg"),
            )

    if m:
        task_id = m.group(1)
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
    return JSONResponse({"detail": "Not found"}, status_code=404)


@app.get("/health")
async def health():
    body: dict = {"status": "ok", "version": APP_VERSION}
    sha = (settings.deploy_git_sha or "").strip()
    if sha:
        body["git"] = sha[:12]
    return body


@app.get("/readiness")
async def readiness():
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    checks: dict[str, str] = {}

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

    checks["openrouter_key"] = "ok" if settings.openrouter_api_key.strip() else "missing"

    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(checks, status_code=200 if ok else 503)

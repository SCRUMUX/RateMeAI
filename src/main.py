import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.config import settings
from src.api.router import api_router
from src.api.middleware import RequestLoggingMiddleware
from src.version import APP_VERSION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [
        "https://ratemeai.com",
        "https://*.up.railway.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")

storage_dir = Path(settings.storage_local_path).resolve()
storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_dir)), name="storage")


@app.get("/health")
async def health():
    body: dict = {"status": "ok", "version": APP_VERSION}
    sha = (settings.deploy_git_sha or "").strip()
    if sha:
        body["git"] = sha[:12]
    return body

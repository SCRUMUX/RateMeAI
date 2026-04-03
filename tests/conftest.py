import os

import pytest


def pytest_configure():
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://ratemeai:ratemeai@127.0.0.1:5432/ratemeai",
    )
    os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    os.environ.setdefault("APP_ENV", "dev")
    os.environ.setdefault("API_BASE_URL", "http://127.0.0.1:8000")
    os.environ.setdefault("STORAGE_LOCAL_PATH", "./storage")


@pytest.fixture
def anyio_backend():
    return "asyncio"

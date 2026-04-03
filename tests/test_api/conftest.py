"""Shared API TestClient fixture."""

from __future__ import annotations

import socket

import pytest


def _tcp_open(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _integration_services_alive() -> bool:
    """Match docker-compose defaults; API tests need both."""
    return _tcp_open("127.0.0.1", 5432) and _tcp_open("127.0.0.1", 6379)


@pytest.fixture
def client():
    if not _integration_services_alive():
        pytest.skip(
            "Postgres (127.0.0.1:5432) and Redis (127.0.0.1:6379) required — "
            "e.g. docker compose up -d postgres redis",
        )
    from fastapi.testclient import TestClient
    from src.main import app

    with TestClient(app) as c:
        yield c

"""RateMeAI SDK client — synchronous and async wrappers for the REST API."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import httpx


@dataclass
class AnalysisResult:
    task_id: str
    status: str
    mode: str
    result: dict = field(default_factory=dict)
    error_message: str | None = None

    @property
    def score(self) -> float | None:
        return self.result.get("score") or self.result.get("dating_score")

    @property
    def image_url(self) -> str | None:
        return self.result.get("generated_image_url") or self.result.get("image_url")

    @property
    def credits_remaining(self) -> int | None:
        return self.result.get("credits_remaining")


class RateMeAI:
    """Synchronous Python client for the RateMeAI REST API.

    Usage:
        client = RateMeAI(api_key="rmai_...")
        result = client.analyze(open("photo.jpg", "rb"), mode="dating", style="warm_outdoor")
        print(result.score, result.image_url)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://app-production-6986.up.railway.app",
        timeout: float = 120.0,
    ):
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def analyze(
        self,
        image: BinaryIO | bytes | str | Path,
        *,
        mode: str = "rating",
        style: str = "",
        profession: str = "",
        poll: bool = True,
        poll_interval: float = 3.0,
        poll_timeout: float = 120.0,
    ) -> AnalysisResult:
        if isinstance(image, (str, Path)):
            image = open(image, "rb")

        img_bytes = image.read() if hasattr(image, "read") else image

        data: dict[str, str] = {"mode": mode}
        if style:
            data["style"] = style
        if profession:
            data["profession"] = profession

        resp = self._client.post(
            "/api/v1/analyze",
            files={"image": ("photo.jpg", img_bytes, "image/jpeg")},
            data=data,
        )
        resp.raise_for_status()
        task_id = resp.json()["task_id"]

        if not poll:
            return AnalysisResult(task_id=task_id, status="pending", mode=mode)

        return self._poll(task_id, mode, poll_interval, poll_timeout)

    def get_task(self, task_id: str) -> AnalysisResult:
        resp = self._client.get(f"/api/v1/tasks/{task_id}")
        resp.raise_for_status()
        d = resp.json()
        return AnalysisResult(
            task_id=d["task_id"],
            status=d["status"],
            mode=d.get("mode", ""),
            result=d.get("result") or {},
            error_message=d.get("error_message"),
        )

    def get_balance(self) -> int:
        resp = self._client.get("/api/v1/payments/balance")
        resp.raise_for_status()
        return resp.json().get("image_credits", 0)

    def _poll(
        self,
        task_id: str,
        mode: str,
        interval: float,
        timeout: float,
    ) -> AnalysisResult:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.get_task(task_id)
            if result.status in ("completed", "failed"):
                return result
            time.sleep(interval)
        return AnalysisResult(task_id=task_id, status="timeout", mode=mode)


class AsyncRateMeAI:
    """Async Python client for the RateMeAI REST API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://app-production-6986.up.railway.app",
        timeout: float = 120.0,
    ):
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def analyze(
        self,
        image: BinaryIO | bytes | str | Path,
        *,
        mode: str = "rating",
        style: str = "",
        profession: str = "",
        poll: bool = True,
        poll_interval: float = 3.0,
        poll_timeout: float = 120.0,
    ) -> AnalysisResult:
        if isinstance(image, (str, Path)):
            image = open(image, "rb")

        img_bytes = image.read() if hasattr(image, "read") else image

        data: dict[str, str] = {"mode": mode}
        if style:
            data["style"] = style
        if profession:
            data["profession"] = profession

        resp = await self._client.post(
            "/api/v1/analyze",
            files={"image": ("photo.jpg", img_bytes, "image/jpeg")},
            data=data,
        )
        resp.raise_for_status()
        task_id = resp.json()["task_id"]

        if not poll:
            return AnalysisResult(task_id=task_id, status="pending", mode=mode)

        return await self._poll(task_id, mode, poll_interval, poll_timeout)

    async def get_task(self, task_id: str) -> AnalysisResult:
        resp = await self._client.get(f"/api/v1/tasks/{task_id}")
        resp.raise_for_status()
        d = resp.json()
        return AnalysisResult(
            task_id=d["task_id"],
            status=d["status"],
            mode=d.get("mode", ""),
            result=d.get("result") or {},
            error_message=d.get("error_message"),
        )

    async def get_balance(self) -> int:
        resp = await self._client.get("/api/v1/payments/balance")
        resp.raise_for_status()
        return resp.json().get("image_credits", 0)

    async def _poll(
        self,
        task_id: str,
        mode: str,
        interval: float,
        timeout: float,
    ) -> AnalysisResult:
        import asyncio

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = await self.get_task(task_id)
            if result.status in ("completed", "failed"):
                return result
            await asyncio.sleep(interval)
        return AnalysisResult(task_id=task_id, status="timeout", mode=mode)

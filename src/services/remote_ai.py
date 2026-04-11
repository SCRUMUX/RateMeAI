"""Proxy AI analysis tasks to the primary Railway backend (used in edge mode)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 2.0
_POLL_MAX_SECONDS = 180.0


class RemoteAIError(Exception):
    pass


class RemoteAIService:
    """Delegates AI processing from the RU edge server to the primary Railway backend."""

    def __init__(self) -> None:
        base = settings.remote_ai_backend_url.rstrip("/")
        if not base:
            raise RuntimeError("REMOTE_AI_BACKEND_URL must be set in edge mode")
        self._base = f"{base}/api/v1/internal"
        self._key = settings.internal_api_key
        if not self._key:
            raise RuntimeError("INTERNAL_API_KEY must be set in edge mode")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Key": self._key}

    async def submit_task(
        self,
        image_b64: str,
        mode: str,
        style: str = "",
        profession: str = "",
        enhancement_level: int = 0,
        pre_analysis_id: str = "",
        edge_task_id: str = "",
    ) -> str:
        """Submit an analysis task to the primary backend. Returns remote task ID."""
        payload = {
            "image_b64": image_b64,
            "mode": mode,
            "style": style,
            "profession": profession,
            "enhancement_level": enhancement_level,
            "pre_analysis_id": pre_analysis_id,
            "edge_task_id": edge_task_id,
        }
        try:
            resp = await self._client.post(
                f"{self._base}/process-analysis",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Remote AI submit failed: %s %s", exc.response.status_code, exc.response.text)
            raise RemoteAIError(f"Primary backend returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.error("Remote AI submit connection error: %s", exc)
            raise RemoteAIError(f"Cannot reach primary backend: {exc}") from exc

        data = resp.json()
        remote_task_id = data["remote_task_id"]
        logger.info("Submitted remote task %s (edge=%s)", remote_task_id, edge_task_id)
        return remote_task_id

    async def poll_result(self, remote_task_id: str) -> dict[str, Any]:
        """Poll until the remote task completes or fails. Returns the full result dict."""
        elapsed = 0.0
        while elapsed < _POLL_MAX_SECONDS:
            try:
                resp = await self._client.get(
                    f"{self._base}/task/{remote_task_id}/status",
                    headers=self._headers(),
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Poll error for %s: %s", remote_task_id, exc)
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                elapsed += _POLL_INTERVAL_SECONDS
                continue

            data = resp.json()
            status = data["status"]

            if status == "completed":
                logger.info("Remote task %s completed", remote_task_id)
                return data
            if status == "failed":
                err = data.get("error_message", "Unknown remote error")
                logger.error("Remote task %s failed: %s", remote_task_id, err)
                raise RemoteAIError(f"Remote AI processing failed: {err}")

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

        raise RemoteAIError(f"Remote task {remote_task_id} timed out after {_POLL_MAX_SECONDS}s")

    async def submit_and_wait(
        self,
        image_b64: str,
        mode: str,
        style: str = "",
        profession: str = "",
        enhancement_level: int = 0,
        pre_analysis_id: str = "",
        edge_task_id: str = "",
    ) -> dict[str, Any]:
        """Submit a task and wait for it to complete. Returns full result."""
        remote_id = await self.submit_task(
            image_b64=image_b64,
            mode=mode,
            style=style,
            profession=profession,
            enhancement_level=enhancement_level,
            pre_analysis_id=pre_analysis_id,
            edge_task_id=edge_task_id,
        )
        return await self.poll_result(remote_id)


_instance: RemoteAIService | None = None


def get_remote_ai() -> RemoteAIService:
    global _instance
    if _instance is None:
        _instance = RemoteAIService()
    return _instance

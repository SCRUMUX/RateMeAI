"""Proxy AI analysis tasks to the primary Railway backend (used in edge mode)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from src.config import settings
from src.services.task_contract import build_policy_flags

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 2.0
# v1.23: raised from 180s to 300s. Nano Banana 2 on ``thinking_level=
# "high"`` plus GPT Image 2 at ``quality="high"`` can legitimately spend
# 180-240 s on the primary (generation + VLM gate). The old 180s ceiling
# caused the edge to mark the request failed while the primary was still
# producing the image, which is exactly the regression reported after
# the v1.22.1 hotfix. Frontend already polls up to 300s.
_POLL_MAX_SECONDS = 300.0


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
        # v1.23: read timeout bumped from 120s to 240s to cover slow
        # ``submit``/``status`` hops when the primary is busy running a
        # ``quality=high`` GPT Image 2 edit — a single GET used to time
        # out at 120s and trigger a spurious RemoteAIError on the edge.
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=240.0, write=30.0, pool=10.0),
        )

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
        variant_id: str = "",
        edge_task_id: str = "",
        market_id: str = "global",
        scenario_slug: str = "",
        scenario_type: str = "",
        entry_mode: str = "",
        trace_id: str = "",
        policy_flags: dict[str, Any] | None = None,
        artifact_refs: dict[str, str] | None = None,
        image_model: str = "",
        image_quality: str = "",
    ) -> str:
        """Submit an analysis task to the primary backend. Returns remote task ID."""
        payload = {
            "image_b64": image_b64,
            "mode": mode,
            "style": style,
            "profession": profession,
            "enhancement_level": enhancement_level,
            "pre_analysis_id": pre_analysis_id,
            "variant_id": variant_id,
            "edge_task_id": edge_task_id,
            "market_id": market_id,
            "scenario_slug": scenario_slug,
            "scenario_type": scenario_type,
            "entry_mode": entry_mode,
            "trace_id": trace_id,
            "policy_flags": build_policy_flags(
                policy_flags,
                cache_allowed=False,
                delete_after_process=True,
                retention_policy="ephemeral",
                data_class="regional_photo",
            ),
            "artifact_refs": artifact_refs or {},
            # v1.22: forward A/B image-gen selection so the primary
            # routes through Nano Banana 2 / GPT Image 2 instead of
            # silently falling through to the legacy StyleRouter.
            # Older primaries simply ignore the extra fields.
            "image_model": image_model or "",
            "image_quality": image_quality or "",
        }
        try:
            resp = await self._client.post(
                f"{self._base}/process-analysis",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Remote AI submit failed: %s %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise RemoteAIError(
                f"Primary backend returned {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("Remote AI submit connection error: %s", exc)
            raise RemoteAIError(f"Cannot reach primary backend: {exc}") from exc

        try:
            data = resp.json()
            remote_task_id = data["remote_task_id"]
        except (KeyError, ValueError) as exc:
            logger.error(
                "Unexpected response from primary on submit: %s", resp.text[:300]
            )
            raise RemoteAIError(
                f"Invalid response from primary backend: {exc}"
            ) from exc
        logger.info(
            "Submitted remote task %s (edge=%s, market=%s, scenario=%s)",
            remote_task_id,
            edge_task_id,
            market_id,
            scenario_type or "n/a",
        )
        return remote_task_id

    async def poll_result(
        self,
        remote_task_id: str,
        on_poll: Any | None = None,
    ) -> dict[str, Any]:
        """Poll until the remote task completes or fails. Returns the full result dict.

        ``on_poll`` is an optional async callback(status: str, elapsed: float)
        called after each successful poll to relay progress to the caller.
        """
        elapsed = 0.0
        poll_count = 0
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

            try:
                data = resp.json()
                status = data["status"]
            except (KeyError, ValueError) as exc:
                logger.warning("Invalid poll response for %s: %s", remote_task_id, exc)
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                elapsed += _POLL_INTERVAL_SECONDS
                continue

            poll_count += 1
            if on_poll is not None:
                try:
                    await on_poll(status, poll_count)
                except Exception:
                    pass

            if status == "completed":
                has_b64 = bool(data.get("generated_image_b64"))
                has_img = bool((data.get("result") or {}).get("generated_image_url"))
                no_reason = (data.get("result") or {}).get("no_image_reason", "")
                logger.info(
                    "Remote task %s completed (has_b64=%s, has_img_url=%s, no_image_reason=%s)",
                    remote_task_id,
                    has_b64,
                    has_img,
                    no_reason or "none",
                )
                return data
            if status == "failed":
                err = data.get("error_message", "Unknown remote error")
                result_snippet = str(data.get("result", {}))[:200]
                logger.error(
                    "Remote task %s failed: %s (result snippet: %s)",
                    remote_task_id,
                    err,
                    result_snippet,
                )
                raise RemoteAIError(f"Remote AI processing failed: {err}")

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

        raise RemoteAIError(
            f"Remote task {remote_task_id} timed out after {_POLL_MAX_SECONDS}s"
        )

    async def pre_analyze(
        self,
        image_b64: str,
        mode: str,
        profession: str = "",
        market_id: str = "global",
        trace_id: str = "",
        policy_flags: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Proxy pre-analysis to the primary backend. Returns the response dict."""
        payload = {
            "image_b64": image_b64,
            "mode": mode,
            "profession": profession,
            "skip_validation": True,
            "market_id": market_id,
            "trace_id": trace_id,
            "policy_flags": build_policy_flags(policy_flags),
        }
        try:
            resp = await self._client.post(
                f"{self._base}/pre-analyze",
                json=payload,
                headers=self._headers(),
                timeout=httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=10.0),
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            logger.error(
                "Remote pre-analyze failed: %s %s", exc.response.status_code, body
            )
            raise RemoteAIError(
                f"Primary pre-analyze returned {exc.response.status_code}: {body}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("Remote pre-analyze connection error: %s", exc)
            raise RemoteAIError(f"Cannot reach primary for pre-analyze: {exc}") from exc
        return resp.json()

    async def submit_and_wait(
        self,
        image_b64: str,
        mode: str,
        style: str = "",
        profession: str = "",
        enhancement_level: int = 0,
        pre_analysis_id: str = "",
        variant_id: str = "",
        edge_task_id: str = "",
        market_id: str = "global",
        scenario_slug: str = "",
        scenario_type: str = "",
        entry_mode: str = "",
        trace_id: str = "",
        policy_flags: dict[str, Any] | None = None,
        artifact_refs: dict[str, str] | None = None,
        image_model: str = "",
        image_quality: str = "",
        on_poll: Any | None = None,
    ) -> dict[str, Any]:
        """Submit a task and wait for it to complete. Returns full result."""
        remote_id = await self.submit_task(
            image_b64=image_b64,
            mode=mode,
            style=style,
            profession=profession,
            enhancement_level=enhancement_level,
            pre_analysis_id=pre_analysis_id,
            variant_id=variant_id,
            edge_task_id=edge_task_id,
            market_id=market_id,
            scenario_slug=scenario_slug,
            scenario_type=scenario_type,
            entry_mode=entry_mode,
            trace_id=trace_id,
            policy_flags=policy_flags,
            artifact_refs=artifact_refs,
            image_model=image_model,
            image_quality=image_quality,
        )
        return await self.poll_result(remote_id, on_poll=on_poll)


_instance: RemoteAIService | None = None


def get_remote_ai() -> RemoteAIService:
    global _instance
    if _instance is None:
        _instance = RemoteAIService()
    return _instance

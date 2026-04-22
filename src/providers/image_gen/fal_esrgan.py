"""FAL.ai Real-ESRGAN upscaler client (v1.17).

Thin httpx-based client for ``fal-ai/real-esrgan``, used as the
*final* upscale step instead of PIL LANCZOS when the feature flag
``settings.real_esrgan_enabled`` is on and the generated photo has a
large-enough face to benefit from a diffusion-aware upscale.

Same queue submit / poll / fetch / decode wire protocol as the
FLUX.2 Pro Edit client (see ``fal_flux2.py``). The body shape is
simpler (one image URL + scale factor), so we only keep the bits
that actually matter for Real-ESRGAN.

Pricing
-------
Real-ESRGAN on FAL bills ~$0.001–$0.002 per image. We estimate
$0.002 for budget math (see ``settings.model_cost_fal_real_esrgan``).
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from typing import Any

import httpx
from PIL import Image

from src.providers.image_gen.fal_flux import (
    FalAPIError,
    FalContentViolationError,
    FalRateLimitError,
)
from src.services.ai_transfer_guard import assert_external_transfer_allowed

logger = logging.getLogger(__name__)

# Real-ESRGAN on FAL accepts ``model`` among a few named upscaler
# weights. ``RealESRGAN_x4plus`` is the default on the docs page; we
# expose it here for completeness even though current callers always
# use the default.
_SUPPORTED_SCALES = frozenset({2, 3, 4})


class FalRealEsrganUpscaler:
    """FAL.ai Real-ESRGAN upscaler client."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/real-esrgan",
        api_host: str = "https://queue.fal.run",
        max_retries: int = 2,
        request_timeout: float = 90.0,
        poll_interval: float = 1.0,
    ):
        self._key = (api_key or "").strip()
        if not self._key:
            raise ValueError(
                "FAL_API_KEY is required for FalRealEsrganUpscaler",
            )
        self._model = model.strip().strip("/")
        self._host = (api_host or "https://queue.fal.run").rstrip("/")
        self._max_retries = max(1, int(max_retries))
        self._timeout = float(request_timeout)
        self._poll_interval = max(0.25, float(poll_interval))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def _sniff_mime(data: bytes) -> str:
        if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        return "image/jpeg"

    def _data_url(self, image_bytes: bytes) -> str:
        mime = self._sniff_mime(image_bytes)
        return f"data:{mime};base64,{self._b64(image_bytes)}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Key {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _submit_url(self) -> str:
        return f"{self._host}/{self._model}"

    def _fallback_status_url(self, request_id: str) -> str:
        parts = self._model.split("/")
        app_root = "/".join(parts[:2]) if len(parts) >= 2 else self._model
        return f"{self._host}/{app_root}/requests/{request_id}/status"

    def _fallback_result_url(self, request_id: str) -> str:
        parts = self._model.split("/")
        app_root = "/".join(parts[:2]) if len(parts) >= 2 else self._model
        return f"{self._host}/{app_root}/requests/{request_id}"

    def _build_body(self, image_bytes: bytes, scale: int) -> dict[str, Any]:
        if not image_bytes:
            raise ValueError("FalRealEsrganUpscaler requires image_bytes")
        scale_clamped = scale if scale in _SUPPORTED_SCALES else 2
        return {
            "image_url": self._data_url(image_bytes),
            "scale": scale_clamped,
            "sync_mode": True,
        }

    # ------------------------------------------------------------------
    # Error parsing (identical shape to fal_flux2)
    # ------------------------------------------------------------------

    def _parse_error(
        self, resp: httpx.Response, phase: str, request_id: str | None = None,
    ) -> FalAPIError:
        status = resp.status_code
        request_id = (
            request_id
            or resp.headers.get("x-fal-request-id")
            or resp.headers.get("x-request-id")
        )
        message = ""
        parsed: dict[str, Any] = {}
        raw_text = ""
        try:
            raw_text = resp.text or ""
        except Exception:
            raw_text = ""
        try:
            parsed = resp.json() if resp.content else {}
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            message = (
                parsed.get("detail")
                or parsed.get("error")
                or parsed.get("message")
                or ""
            )
            if isinstance(message, (list, dict)):
                message = str(message)
        if not message:
            message = raw_text[:400] if raw_text else ""
        full_msg = f"http={status} phase={phase} {message or 'FAL error'}"

        if status == 429:
            retry_after: float | None = None
            ra = resp.headers.get("retry-after")
            if ra:
                try:
                    retry_after = float(ra)
                except ValueError:
                    retry_after = None
            return FalRateLimitError(
                full_msg, retry_after=retry_after, request_id=request_id,
            )
        return FalAPIError(
            full_msg,
            status_code=status,
            error_code=str(parsed.get("error_code") or "") or None,
            request_id=request_id,
        )

    # ------------------------------------------------------------------
    # Queue flow
    # ------------------------------------------------------------------

    def _submit(
        self, client: httpx.Client, body: dict[str, Any],
    ) -> tuple[str, str, str]:
        resp = client.post(
            self._submit_url(), json=body, headers=self._headers(),
        )
        if resp.status_code >= 400:
            raise self._parse_error(resp, phase="submit")
        try:
            data = resp.json()
        except Exception as exc:
            raise FalAPIError(
                f"FAL Real-ESRGAN submit: cannot parse response ({exc})",
                status_code=resp.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise FalAPIError(
                "FAL Real-ESRGAN submit: response is not a JSON object",
                status_code=resp.status_code,
            )
        request_id = (
            data.get("request_id")
            or resp.headers.get("x-fal-request-id")
        )
        if not request_id:
            raise FalAPIError(
                "FAL Real-ESRGAN submit: response missing request_id",
                status_code=resp.status_code,
            )
        request_id = str(request_id)
        status_url = str(
            data.get("status_url") or self._fallback_status_url(request_id)
        )
        response_url = str(
            data.get("response_url") or self._fallback_result_url(request_id)
        )
        return request_id, status_url, response_url

    def _poll_until_done(
        self,
        client: httpx.Client,
        request_id: str,
        status_url: str,
        deadline: float,
    ) -> None:
        while True:
            if time.monotonic() >= deadline:
                raise FalAPIError(
                    f"FAL Real-ESRGAN timeout after {self._timeout}s "
                    f"(req={request_id})",
                    status_code=None, request_id=request_id,
                )
            resp = client.get(status_url, headers=self._headers())
            if resp.status_code >= 400:
                raise self._parse_error(
                    resp, phase="status", request_id=request_id,
                )
            try:
                data = resp.json()
            except Exception:
                data = {}
            status = ""
            if isinstance(data, dict):
                status = str(data.get("status") or "").upper()
            if status in ("COMPLETED", "OK", "SUCCESS"):
                return
            if status in ("FAILED", "ERROR", "CANCELLED"):
                reason = ""
                if isinstance(data, dict):
                    reason = str(
                        data.get("error") or data.get("detail") or "",
                    )
                raise FalAPIError(
                    f"FAL Real-ESRGAN queue status={status} "
                    f"req={request_id} {reason}".strip(),
                    status_code=None, request_id=request_id,
                )
            time.sleep(self._poll_interval)

    def _fetch_result(
        self, client: httpx.Client, request_id: str, response_url: str,
    ) -> dict[str, Any]:
        resp = client.get(response_url, headers=self._headers())
        if resp.status_code >= 400:
            raise self._parse_error(
                resp, phase="result", request_id=request_id,
            )
        try:
            return resp.json()
        except Exception as exc:
            raise FalAPIError(
                f"FAL Real-ESRGAN result: cannot parse response ({exc})",
                status_code=resp.status_code, request_id=request_id,
            ) from exc

    def _decode_image(
        self,
        client: httpx.Client,
        data: dict[str, Any],
        request_id: str | None,
    ) -> bytes:
        if not isinstance(data, dict):
            raise FalAPIError(
                "FAL Real-ESRGAN result: payload is not a JSON object",
                request_id=request_id,
            )
        if data.get("has_nsfw_concepts"):
            flags = data.get("has_nsfw_concepts")
            if isinstance(flags, list) and any(bool(x) for x in flags):
                raise FalContentViolationError(
                    "FAL Real-ESRGAN: NSFW content detected",
                    status_code=200,
                    error_code="NSFW",
                    request_id=request_id,
                )
        image_entry: dict[str, Any] | None = None
        image = data.get("image")
        if isinstance(image, dict):
            image_entry = image
        if image_entry is None:
            images = data.get("images")
            if isinstance(images, list) and images:
                first = images[0]
                if isinstance(first, dict):
                    image_entry = first
        if image_entry is None:
            raise FalAPIError(
                "FAL Real-ESRGAN result: no image in response",
                request_id=request_id,
            )
        url = str(image_entry.get("url") or "")
        if not url:
            raise FalAPIError(
                "FAL Real-ESRGAN result: image entry missing 'url'",
                request_id=request_id,
            )
        if url.startswith("data:"):
            try:
                _, payload = url.split(",", 1)
            except ValueError as exc:
                raise FalAPIError(
                    f"FAL Real-ESRGAN result: malformed data URI ({exc})",
                    request_id=request_id,
                ) from exc
            try:
                return base64.b64decode(payload)
            except Exception as exc:
                raise FalAPIError(
                    f"FAL Real-ESRGAN result: malformed base64 ({exc})",
                    request_id=request_id,
                ) from exc
        img_resp = client.get(url)
        if img_resp.status_code >= 400:
            raise FalAPIError(
                "FAL Real-ESRGAN image download failed "
                f"http={img_resp.status_code}",
                status_code=img_resp.status_code, request_id=request_id,
            )
        return img_resp.content

    def _upscale_sync(self, image_bytes: bytes, scale: int) -> bytes:
        body = self._build_body(image_bytes, scale)
        logger.info(
            "FAL Real-ESRGAN request model=%s scale=x%d input_bytes=%d",
            self._model, scale, len(image_bytes or b""),
        )

        last_err: Exception | None = None
        deadline = time.monotonic() + self._timeout
        for attempt in range(self._max_retries):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    request_id, status_url, response_url = self._submit(
                        client, body,
                    )
                    self._poll_until_done(
                        client, request_id, status_url, deadline,
                    )
                    data = self._fetch_result(
                        client, request_id, response_url,
                    )
                    return self._decode_image(client, data, request_id)
            except FalContentViolationError:
                raise
            except FalRateLimitError as e:
                last_err = e
                if attempt + 1 >= self._max_retries:
                    break
                wait = e.retry_after or (5 * (attempt + 1))
                time.sleep(float(wait))
            except FalAPIError as e:
                last_err = e
                retryable = (
                    e.status_code is None
                    or (isinstance(e.status_code, int) and e.status_code >= 500)
                )
                if not retryable:
                    raise RuntimeError(
                        f"FAL Real-ESRGAN error: {e.message}",
                    ) from e
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(2.0 * (attempt + 1))
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = e
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(2.0 * (attempt + 1))

        msg = getattr(last_err, "message", None) or str(last_err)
        raise RuntimeError(
            f"FAL Real-ESRGAN failed after {self._max_retries} "
            f"attempt(s): {msg}"
        ) from last_err

    async def upscale(self, image_bytes: bytes, factor: int = 2) -> bytes:
        """Run Real-ESRGAN upscaling on ``image_bytes``.

        Returns the upscaled JPEG/PNG bytes. Raises ``RuntimeError`` on
        any terminal FAL error; the caller is expected to fall back to
        :func:`src.services.postprocess.upscale_lanczos` for continuity.
        """
        assert_external_transfer_allowed("fal_real_esrgan")
        raw = await asyncio.to_thread(
            self._upscale_sync, image_bytes, int(factor),
        )
        if raw and len(raw) > 100:
            return raw
        try:
            img = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92)
            return buf.getvalue()
        except Exception as exc:
            raise RuntimeError(
                f"FAL Real-ESRGAN: empty/invalid image ({exc})",
            ) from exc


__all__ = ["FalRealEsrganUpscaler"]

"""FAL.ai GFPGAN face-restoration client (v1.17).

Thin httpx-based client for `fal-ai/gfpgan`, used as a *pre-clean* step
before the main FLUX.2 Pro Edit generation when the input photo has a
blurry or low-quality face (see `src/services/face_prerestore.py` for
activation rules). Unlike the FLUX.2 provider this is NOT an
``ImageGenProvider`` — GFPGAN does not accept a prompt; it just takes
one input image and returns a restored version.

Wire protocol mirrors the queue submit / poll / fetch / decode flow of
``fal_flux2.py`` — the FAL queue contract is uniform across models.
We intentionally duplicate the boilerplate instead of extracting a
shared base: the body shape, knob set, and error semantics differ per
model, and a shallow copy keeps each provider readable on its own.

Pricing
-------
fal-ai/gfpgan bills ~$0.001–$0.002 per image (flat). We treat it as
$0.002 for budget math (`settings.model_cost_fal_gfpgan`).
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


class FalGfpganRestorer:
    """FAL.ai GFPGAN face-restoration client.

    Single-method surface: ``restore(image_bytes) -> bytes``. Any error
    (transport, HTTP 4xx/5xx, NSFW, parse) bubbles up so the caller can
    fall back to the original image — pre-restoration is always
    optional, never load-bearing.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/gfpgan",
        api_host: str = "https://queue.fal.run",
        max_retries: int = 2,
        request_timeout: float = 90.0,
        poll_interval: float = 1.0,
    ):
        self._key = (api_key or "").strip()
        if not self._key:
            raise ValueError("FAL_API_KEY is required for FalGfpganRestorer")
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

    def _build_body(self, image_bytes: bytes) -> dict[str, Any]:
        if not image_bytes:
            raise ValueError("FalGfpganRestorer requires image_bytes")
        return {
            "image_url": self._data_url(image_bytes),
            "sync_mode": True,
        }

    # ------------------------------------------------------------------
    # Error parsing (same shape as fal_flux2)
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
                f"FAL GFPGAN submit: cannot parse response ({exc})",
                status_code=resp.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise FalAPIError(
                "FAL GFPGAN submit: response is not a JSON object",
                status_code=resp.status_code,
            )
        request_id = (
            data.get("request_id")
            or resp.headers.get("x-fal-request-id")
        )
        if not request_id:
            raise FalAPIError(
                "FAL GFPGAN submit: response missing request_id",
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
                    f"FAL GFPGAN timeout after {self._timeout}s "
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
                    f"FAL GFPGAN queue status={status} req={request_id} "
                    f"{reason}".strip(),
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
                f"FAL GFPGAN result: cannot parse response ({exc})",
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
                "FAL GFPGAN result: payload is not a JSON object",
                request_id=request_id,
            )
        if data.get("has_nsfw_concepts"):
            flags = data.get("has_nsfw_concepts")
            if isinstance(flags, list) and any(bool(x) for x in flags):
                raise FalContentViolationError(
                    "FAL GFPGAN: NSFW content detected",
                    status_code=200,
                    error_code="NSFW",
                    request_id=request_id,
                )
        # GFPGAN returns either ``image: {url}`` or ``images: [{url}]``.
        # We accept both and prefer the plural form used by newer schemas.
        image_entry: dict[str, Any] | None = None
        images = data.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                image_entry = first
        if image_entry is None:
            image = data.get("image")
            if isinstance(image, dict):
                image_entry = image
        if image_entry is None:
            raise FalAPIError(
                "FAL GFPGAN result: no image in response",
                request_id=request_id,
            )
        url = str(image_entry.get("url") or "")
        if not url:
            raise FalAPIError(
                "FAL GFPGAN result: image entry missing 'url'",
                request_id=request_id,
            )
        if url.startswith("data:"):
            try:
                _, payload = url.split(",", 1)
            except ValueError as exc:
                raise FalAPIError(
                    f"FAL GFPGAN result: malformed data URI ({exc})",
                    request_id=request_id,
                ) from exc
            try:
                return base64.b64decode(payload)
            except Exception as exc:
                raise FalAPIError(
                    f"FAL GFPGAN result: malformed base64 ({exc})",
                    request_id=request_id,
                ) from exc
        img_resp = client.get(url)
        if img_resp.status_code >= 400:
            raise FalAPIError(
                f"FAL GFPGAN image download failed http={img_resp.status_code}",
                status_code=img_resp.status_code, request_id=request_id,
            )
        return img_resp.content

    def _restore_sync(self, image_bytes: bytes) -> bytes:
        body = self._build_body(image_bytes)
        logger.info(
            "FAL GFPGAN request model=%s input_bytes=%d",
            self._model, len(image_bytes or b""),
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
                        f"FAL GFPGAN error: {e.message}",
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
            f"FAL GFPGAN failed after {self._max_retries} attempt(s): {msg}"
        ) from last_err

    async def restore(self, image_bytes: bytes) -> bytes:
        """Run GFPGAN face-restoration on ``image_bytes``.

        Returns the restored JPEG/PNG bytes. Raises :class:`RuntimeError`
        on any terminal FAL error. The caller is expected to fall back
        to the original bytes on failure — pre-restoration is a
        nice-to-have, never a load-bearing stage.
        """
        assert_external_transfer_allowed("fal_gfpgan")
        raw = await asyncio.to_thread(self._restore_sync, image_bytes)
        if raw and len(raw) > 100:
            return raw
        # Unusually small payload — try to salvage via PIL round-trip
        # (mirrors fal_flux2 behaviour).
        try:
            img = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92)
            return buf.getvalue()
        except Exception as exc:
            raise RuntimeError(
                f"FAL GFPGAN: empty/invalid image ({exc})",
            ) from exc


__all__ = ["FalGfpganRestorer"]

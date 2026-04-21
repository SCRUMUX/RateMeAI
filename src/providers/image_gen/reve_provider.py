from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from typing import Any

import httpx
from PIL import Image

from src.providers.base import ImageGenProvider
from src.services.ai_transfer_guard import assert_external_transfer_allowed

logger = logging.getLogger(__name__)


class ReveAPIError(Exception):
    """Reve REST error (HTTP 4xx/5xx other than 429)."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 error_code: str | None = None, request_id: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.request_id = request_id


class ReveRateLimitError(ReveAPIError):
    """HTTP 429 — not billed, safe to retry within max_retries."""

    def __init__(self, message: str, *, retry_after: float | None = None,
                 request_id: str | None = None):
        super().__init__(message, status_code=429,
                         error_code="RATE_LIMIT", request_id=request_id)
        self.retry_after = retry_after


class ReveContentViolationError(ReveAPIError):
    """Response flagged as content-policy violation (no retry)."""


class ReveImageGen(ImageGenProvider):
    """Reve Partner API client using direct httpx calls.

    We deliberately bypass the bundled ``reve`` SDK because its 0.1.2
    release surfaces 429 ``PARTNER_API_TOKEN_RATE_LIMIT_EXCEEDED`` even
    on the very first request with a fresh token, while an identical
    raw HTTP call from the same container returns 200 in ~6 s. Full
    reproduction: see ``/api/v1/internal/diagnostics/reve-raw``.

    Billing / retry policy:
      * 429 is not billed → retry within ``max_retries``.
      * 5xx / transport errors → retry within ``max_retries``.
      * 4xx (other than 429) → no retry: response was served, a repeat
        won't change the outcome.
      * Content-policy violation → no retry (cost may or may not apply).
    """

    # NOTE: trailing slash is required by the Reve gateway. Without it the
    # server replies with INVALID_PARAMETER_VALUE (observed 2026-04-21).
    # Mirrors the official SDK at reve/v1/image.py which also uses "/".
    API_CREATE = "/v1/image/create/"
    API_EDIT = "/v1/image/edit/"
    API_REMIX = "/v1/image/remix/"
    REQUEST_TIMEOUT = 120.0

    def __init__(
        self,
        api_token: str,
        api_host: str,
        aspect_ratio: str = "1:1",
        version: str = "latest",
        test_time_scaling: int = 3,
        max_retries: int | None = None,
    ):
        self._token = (api_token or "").strip()
        self._host = (api_host or "https://api.reve.com").rstrip("/")
        if not self._token:
            raise ValueError("REVE_API_TOKEN is required for ReveImageGen")
        self._aspect_ratio = aspect_ratio
        self._version = version
        self._test_time_scaling = test_time_scaling
        if max_retries is None:
            try:
                from src.config import settings
                max_retries = int(getattr(settings, "reve_max_retries", 1))
            except Exception:
                max_retries = 1
        self._max_retries = max(1, int(max_retries))

    async def close(self) -> None:
        pass

    def _build_options(
        self,
        params: dict | None,
        endpoint: str,
    ) -> dict[str, Any]:
        """Build per-endpoint options.

        Reve's three endpoints do **not** share the same parameter surface:
        only ``/v1/image/create`` accepts the full generation config
        (``aspect_ratio`` / ``version`` / ``test_time_scaling``). Sending
        those keys to ``/v1/image/edit`` or ``/v1/image/remix`` produces
        ``INVALID_PARAMETER_VALUE`` with credits_used=0 (observed in Reve
        dashboard logs on 2026-04-21 at 16:07), which then cascades into
        worker retries and hits the token rate limit. Keep edit/remix
        payloads minimal.
        """
        opts: dict[str, Any] = {}
        if endpoint == self.API_CREATE:
            opts["aspect_ratio"] = self._aspect_ratio
            opts["version"] = self._version
            opts["test_time_scaling"] = self._test_time_scaling
            if params:
                for k in ("aspect_ratio", "version", "test_time_scaling"):
                    if k in params and params[k] is not None:
                        opts[k] = params[k]
        return opts

    @staticmethod
    def _mask_to_instruction_hint(params: dict | None) -> str:
        if not params:
            return ""
        region = params.get("mask_region", "")
        hints = {
            "background": "Change ONLY the background, keep the person untouched.",
            "clothing": "Change ONLY the clothing/outfit, keep face and background untouched.",
            "face": "Make subtle adjustments to lighting/expression on the face ONLY.",
        }
        return hints.get(region, "")

    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")

    def _headers(self) -> dict[str, str]:
        # Accept image/png first (Reve native), then fall back to JSON
        # (base64-wrapped). Mirrors the official SDK which uses image/png.
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "image/png, application/json;q=0.5",
        }

    def _parse_error(self, resp: httpx.Response) -> ReveAPIError:
        status = resp.status_code
        request_id = resp.headers.get("x-reve-request-id")
        error_code_hdr = resp.headers.get("x-reve-error-code")
        message = ""
        parsed: dict[str, Any] = {}
        raw_text = ""
        try:
            raw_text = resp.text or ""
        except Exception:
            raw_text = ""
        try:
            parsed = resp.json() if resp.content else {}
            message = (
                parsed.get("message")
                or parsed.get("error")
                or (parsed.get("error_code") or "")
            )
        except Exception:
            message = raw_text[:400] if raw_text else ""
        error_code = error_code_hdr or parsed.get("error_code")

        # For non-429 4xx log the raw body at WARN level — this is the
        # only place we see which request field Reve rejected
        # (``INVALID_PARAMETER_VALUE`` errors carry the culprit in the
        # JSON body, not in the error_code). Also inline a short body
        # snippet into the exception message so _format_task_error
        # surfaces it in task.error_message for web/bot UI without a
        # Railway log dive.
        body_snippet = ""
        if raw_text and status != 429 and status >= 400:
            snippet = raw_text.strip().replace("\n", " ")
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            body_snippet = snippet
            logger.warning(
                "Reve %d error (code=%s req=%s): %s",
                status, error_code, request_id, raw_text[:500],
            )

        full_msg = f"http={status} {message or error_code or 'Reve error'}"
        if body_snippet and body_snippet not in full_msg:
            full_msg = f"{full_msg} body={body_snippet!r}"
        if status == 429:
            retry_after: float | None = None
            ra = resp.headers.get("retry-after")
            if ra:
                try:
                    retry_after = float(ra)
                except ValueError:
                    retry_after = None
            return ReveRateLimitError(
                full_msg,
                retry_after=retry_after,
                request_id=request_id,
            )
        return ReveAPIError(
            full_msg,
            status_code=status,
            error_code=error_code,
            request_id=request_id,
        )

    @staticmethod
    def _extract_image_bytes(resp: httpx.Response) -> bytes:
        """Turn a successful Reve response into JPEG/PNG bytes."""
        if resp.headers.get("x-reve-content-violation", "").lower() == "true":
            raise ReveContentViolationError(
                "Reve: content policy violation",
                status_code=resp.status_code,
                error_code="CONTENT_VIOLATION",
                request_id=resp.headers.get("x-reve-request-id"),
            )
        ctype = (resp.headers.get("content-type") or "").lower()
        if ctype.startswith("image/"):
            return resp.content
        data: dict[str, Any] = {}
        try:
            data = resp.json()
        except Exception as exc:
            raise ReveAPIError(
                f"Reve: cannot parse response ({exc})",
                status_code=resp.status_code,
                request_id=resp.headers.get("x-reve-request-id"),
            ) from exc
        if data.get("content_violation") is True:
            raise ReveContentViolationError(
                "Reve: content policy violation",
                status_code=resp.status_code,
                error_code="CONTENT_VIOLATION",
                request_id=resp.headers.get("x-reve-request-id"),
            )
        b64 = data.get("image") or data.get("image_base64")
        if isinstance(b64, str) and b64:
            try:
                raw = base64.b64decode(b64)
            except Exception as exc:
                raise ReveAPIError(
                    f"Reve: malformed base64 image ({exc})",
                    status_code=resp.status_code,
                    request_id=resp.headers.get("x-reve-request-id"),
                ) from exc
            if raw:
                return raw
        raise ReveAPIError(
            "Reve: response did not contain an image",
            status_code=resp.status_code,
            request_id=resp.headers.get("x-reve-request-id"),
        )

    def _do_request_sync(
        self,
        endpoint: str,
        body: dict[str, Any],
    ) -> bytes:
        url = f"{self._host}{endpoint}"
        with httpx.Client(timeout=self.REQUEST_TIMEOUT) as client:
            resp = client.post(url, json=body, headers=self._headers())
        if resp.status_code >= 400:
            raise self._parse_error(resp)
        return self._extract_image_bytes(resp)

    def _build_body(
        self,
        endpoint: str,
        prompt: str,
        reference_image: bytes | None,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        if endpoint == self.API_CREATE:
            return {"prompt": prompt, **options}
        if endpoint == self.API_EDIT:
            if not reference_image:
                raise ValueError("edit requires reference_image")
            return {
                "edit_instruction": prompt,
                "reference_image": self._b64(reference_image),
                **options,
            }
        if endpoint == self.API_REMIX:
            if not reference_image:
                raise ValueError("remix requires reference_image")
            return {
                "prompt": prompt,
                "reference_images": [self._b64(reference_image)],
                **options,
            }
        raise ValueError(f"unknown endpoint {endpoint}")

    def _generate_sync(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> bytes:
        mask_region = params.get("mask_region") if params else None
        use_edit = bool(params and params.get("use_edit")) or bool(mask_region)
        if mask_region:
            hint = self._mask_to_instruction_hint(params)
            if hint:
                prompt = f"{hint} {prompt}"

        if reference_image and use_edit:
            endpoint = self.API_EDIT
        elif reference_image:
            endpoint = self.API_REMIX
        else:
            endpoint = self.API_CREATE

        options = self._build_options(params, endpoint)
        body = self._build_body(endpoint, prompt, reference_image, options)

        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return self._do_request_sync(endpoint, body)
            except ReveContentViolationError:
                raise
            except ReveRateLimitError as e:
                last_err = e
                if attempt + 1 >= self._max_retries:
                    logger.warning(
                        "Reve rate-limited, no retries left (attempt %d/%d, req=%s)",
                        attempt + 1, self._max_retries, e.request_id,
                    )
                    break
                wait = e.retry_after or (10 * (attempt + 1))
                logger.warning(
                    "Reve rate-limited, waiting %ss (attempt %d/%d, req=%s)",
                    wait, attempt + 1, self._max_retries, e.request_id,
                )
                time.sleep(float(wait))
            except ReveAPIError as e:
                last_err = e
                retryable = (
                    e.status_code is None
                    or (isinstance(e.status_code, int) and e.status_code >= 500)
                )
                if not retryable:
                    logger.exception(
                        "Reve API error (no retry, status=%s, code=%s, req=%s): %s",
                        e.status_code, e.error_code, e.request_id, e.message,
                    )
                    raise RuntimeError(f"Reve API error: {e.message}") from e
                if attempt + 1 >= self._max_retries:
                    logger.warning(
                        "Reve transient error, no retries left (attempt %d/%d, status=%s): %s",
                        attempt + 1, self._max_retries, e.status_code, e.message,
                    )
                    break
                wait = 2 * (attempt + 1)
                logger.warning(
                    "Reve transient error (status=%s), retrying in %ss (attempt %d/%d): %s",
                    e.status_code, wait, attempt + 1, self._max_retries, e.message,
                )
                time.sleep(float(wait))
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = e
                if attempt + 1 >= self._max_retries:
                    logger.warning(
                        "Reve transport error, no retries left (attempt %d/%d): %s",
                        attempt + 1, self._max_retries, e,
                    )
                    break
                wait = 2 * (attempt + 1)
                logger.warning(
                    "Reve transport error, retrying in %ss (attempt %d/%d): %s",
                    wait, attempt + 1, self._max_retries, e,
                )
                time.sleep(float(wait))

        msg = getattr(last_err, "message", None) or str(last_err)
        raise RuntimeError(
            f"Reve failed after {self._max_retries} attempt(s): {msg}"
        ) from last_err

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        assert_external_transfer_allowed("reve")
        raw = await asyncio.to_thread(
            self._generate_sync, prompt, reference_image, params,
        )
        if raw and len(raw) > 100:
            return raw
        try:
            img = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92)
            return buf.getvalue()
        except Exception as exc:
            raise RuntimeError(f"Reve: empty/invalid image ({exc})") from exc


__all__ = [
    "ReveImageGen",
    "ReveAPIError",
    "ReveRateLimitError",
    "ReveContentViolationError",
]

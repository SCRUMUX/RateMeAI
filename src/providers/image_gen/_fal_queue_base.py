"""Shared queue-submit/poll/fetch/decode logic for FAL.ai providers.

Every FAL model we use (PuLID, Seedream v4 Edit, CodeFormer, FLUX.2 Pro Edit,
FLUX.1 Kontext Pro, GFPGAN, Real-ESRGAN) exposes the same 3-step queue
protocol::

    POST   {host}/{model}                  → {request_id, status_url, response_url}
    GET    {status_url}                    → poll until status == COMPLETED
    GET    {response_url}                  → {images: [{url}]} or {image: {url}}

As of v1.20.0 every provider in ``src/providers/image_gen/fal_*.py`` is a
:class:`FalQueueClient` subclass — the queue protocol lives here, and each
provider only implements the model-specific ``_build_body`` + a short log
label. Prior to v1.20.0 the older providers (``fal_flux.py``, ``fal_flux2.py``,
``fal_gfpgan.py``, ``fal_esrgan.py``) each carried their own ~200-line copy
of this file; we consolidated them once the v1.18 hybrid pipeline (PuLID /
Seedream / CodeFormer, which already used this base) had proven stable in
production.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Error hierarchy (single source of truth — re-exported by fal_flux.py
# for existing ``from src.providers.image_gen.fal_flux import FalAPIError``
# call sites).
# ----------------------------------------------------------------------


class FalAPIError(Exception):
    """FAL REST error (HTTP 4xx/5xx other than 429)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        request_id: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.request_id = request_id


class FalRateLimitError(FalAPIError):
    """HTTP 429 — safe to retry within max_retries."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        request_id: str | None = None,
    ):
        super().__init__(
            message,
            status_code=429,
            error_code="RATE_LIMIT",
            request_id=request_id,
        )
        self.retry_after = retry_after


class FalContentViolationError(FalAPIError):
    """Response flagged as NSFW / safety violation (no retry)."""


class FalQueueClient:
    """Base class for FAL queue-style providers.

    Subclasses must implement :meth:`_build_body` and should set ``self._label``
    (a short identifier like ``"PuLID"`` / ``"Seedream"`` used in log and
    error messages). Everything else — auth, retries, polling, data URI
    encoding, result decoding — is provided here.
    """

    # Override if a subclass returns images under a different key order.
    # Default tries ``images[0]`` first, then ``image``.
    _image_response_keys: tuple[str, ...] = ("images", "image")

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        api_host: str = "https://queue.fal.run",
        max_retries: int = 2,
        request_timeout: float = 120.0,
        poll_interval: float = 1.0,
        label: str = "FAL",
    ):
        self._key = (api_key or "").strip()
        if not self._key:
            raise ValueError(f"FAL_API_KEY is required for {label}")
        self._model = model.strip().strip("/")
        self._host = (api_host or "https://queue.fal.run").rstrip("/")
        self._max_retries = max(1, int(max_retries))
        self._timeout = float(request_timeout)
        self._poll_interval = max(0.25, float(poll_interval))
        self._label = label

    # ------------------------------------------------------------------
    # Helpers (data URIs + auth headers)
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

    # ------------------------------------------------------------------
    # Body — subclasses implement this
    # ------------------------------------------------------------------

    def _build_body(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Error parsing (uniform across all FAL models)
    # ------------------------------------------------------------------

    def _parse_error(
        self,
        resp: httpx.Response,
        phase: str,
        request_id: str | None = None,
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

        body_snippet = ""
        if raw_text and status != 429 and status >= 400:
            snippet = raw_text.strip().replace("\n", " ")
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            body_snippet = snippet
            logger.warning(
                "FAL %s %s %d error (req=%s): %s",
                self._label, phase, status, request_id, raw_text[:500],
            )

        full_msg = (
            f"http={status} phase={phase} "
            f"{message or f'{self._label} error'}"
        )
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
    # Queue flow (submit → poll → fetch → decode)
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
                f"FAL {self._label} submit: cannot parse response ({exc})",
                status_code=resp.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise FalAPIError(
                f"FAL {self._label} submit: response is not a JSON object",
                status_code=resp.status_code,
            )
        request_id = (
            data.get("request_id") or resp.headers.get("x-fal-request-id")
        )
        if not request_id:
            raise FalAPIError(
                f"FAL {self._label} submit: response missing request_id",
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
                    f"FAL {self._label} timeout after {self._timeout}s "
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
                    f"FAL {self._label} queue status={status} "
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
                f"FAL {self._label} result: cannot parse response ({exc})",
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
                f"FAL {self._label} result: payload is not a JSON object",
                request_id=request_id,
            )
        flags = data.get("has_nsfw_concepts")
        if isinstance(flags, list) and any(bool(x) for x in flags):
            raise FalContentViolationError(
                f"FAL {self._label}: NSFW content detected",
                status_code=200,
                error_code="NSFW",
                request_id=request_id,
            )

        image_entry: dict[str, Any] | None = None
        for key in self._image_response_keys:
            value = data.get(key)
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict):
                    image_entry = first
                    break
            elif isinstance(value, dict):
                image_entry = value
                break
        if image_entry is None:
            raise FalAPIError(
                f"FAL {self._label} result: no images in response",
                request_id=request_id,
            )
        url = str(image_entry.get("url") or "")
        if not url:
            raise FalAPIError(
                f"FAL {self._label} result: image entry missing 'url'",
                request_id=request_id,
            )
        if url.startswith("data:"):
            try:
                _, payload = url.split(",", 1)
            except ValueError as exc:
                raise FalAPIError(
                    f"FAL {self._label} result: malformed data URI ({exc})",
                    request_id=request_id,
                ) from exc
            try:
                return base64.b64decode(payload)
            except Exception as exc:
                raise FalAPIError(
                    f"FAL {self._label} result: malformed base64 ({exc})",
                    request_id=request_id,
                ) from exc
        img_resp = client.get(url)
        if img_resp.status_code >= 400:
            raise FalAPIError(
                f"FAL {self._label} image download "
                f"http={img_resp.status_code}",
                status_code=img_resp.status_code, request_id=request_id,
            )
        return img_resp.content

    # ------------------------------------------------------------------
    # Orchestration — submit+poll+fetch+decode with retry
    # ------------------------------------------------------------------

    def _run_queue_sync(
        self,
        body: dict[str, Any],
    ) -> bytes:
        """Run the 3-step queue flow with bounded retries.

        Retries transient failures (5xx, timeout, transport) and rate
        limits (429). Terminal failures (4xx other than 429, content
        policy) are raised as :class:`RuntimeError` for the caller to
        handle or surface upstream.
        """
        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            deadline = time.monotonic() + self._timeout
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
                    logger.warning(
                        "FAL %s rate-limited, no retries left "
                        "(attempt %d/%d, req=%s)",
                        self._label, attempt + 1, self._max_retries,
                        e.request_id,
                    )
                    break
                wait = e.retry_after or (5 * (attempt + 1))
                logger.warning(
                    "FAL %s rate-limited, waiting %ss "
                    "(attempt %d/%d, req=%s)",
                    self._label, wait, attempt + 1, self._max_retries,
                    e.request_id,
                )
                time.sleep(float(wait))
            except FalAPIError as e:
                last_err = e
                retryable = (
                    e.status_code is None
                    or (
                        isinstance(e.status_code, int)
                        and e.status_code >= 500
                    )
                )
                if not retryable:
                    logger.warning(
                        "FAL %s API error (no retry, status=%s, "
                        "code=%s, req=%s): %s",
                        self._label, e.status_code, e.error_code,
                        e.request_id, e.message,
                    )
                    raise RuntimeError(
                        f"FAL {self._label} API error: {e.message}",
                    ) from e
                if attempt + 1 >= self._max_retries:
                    logger.warning(
                        "FAL %s transient error, no retries left "
                        "(attempt %d/%d, status=%s): %s",
                        self._label, attempt + 1, self._max_retries,
                        e.status_code, e.message,
                    )
                    break
                wait = 2 * (attempt + 1)
                logger.warning(
                    "FAL %s transient error (status=%s), retrying in %ss "
                    "(attempt %d/%d): %s",
                    self._label, e.status_code, wait,
                    attempt + 1, self._max_retries, e.message,
                )
                time.sleep(float(wait))
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = e
                if attempt + 1 >= self._max_retries:
                    logger.warning(
                        "FAL %s transport error, no retries left "
                        "(attempt %d/%d): %s",
                        self._label, attempt + 1, self._max_retries, e,
                    )
                    break
                wait = 2 * (attempt + 1)
                logger.warning(
                    "FAL %s transport error, retrying in %ss "
                    "(attempt %d/%d): %s",
                    self._label, wait, attempt + 1, self._max_retries, e,
                )
                time.sleep(float(wait))

        msg = getattr(last_err, "message", None) or str(last_err)
        raise RuntimeError(
            f"FAL {self._label} failed after {self._max_retries} "
            f"attempt(s): {msg}"
        ) from last_err


__all__ = [
    "FalQueueClient",
    "FalAPIError",
    "FalRateLimitError",
    "FalContentViolationError",
]

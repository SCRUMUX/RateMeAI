"""FAL.ai FLUX.1 Kontext [pro] image-gen provider.

Active runtime provider for all face-preserving edit scenarios
(dating / cv / social / emoji). Mirrors ``ReveImageGen`` interface —
takes a prompt + reference image, returns JPEG bytes — so the
factory can swap providers transparently via ``IMAGE_GEN_PROVIDER``.

Why direct httpx and not ``fal-client``
---------------------------------------
We bypass the official Python SDK for the same reasons we bypass the
Reve SDK (see ``ReveImageGen`` docstring): fewer dependencies, simpler
test doubles (``httpx.MockTransport``), and full control over retry /
timeout / content-policy handling.

Endpoint contract
-----------------
Queue submit:  ``POST  {host}/{model}`` body + Auth header

The submit response contains two fully-qualified URLs::

    {"request_id": "...", "status_url": "...", "response_url": "..."}

which we **must** reuse verbatim for status polling and result fetch.
Constructing ``{host}/{model}/requests/{id}/status`` manually breaks
for apps whose model path has sub-paths (e.g. ``fal-ai/flux-pro/kontext``)
— FAL returns HTTP 405 Method Not Allowed on such synthetic URLs while
the ``status_url`` from the response resolves correctly.

With ``sync_mode=True`` in the submit body the final image is returned
as a data URI inside ``response.images[0].url``, so we never need a
second HTTP fetch against ``fal.media``. This keeps every generation
at exactly 3 HTTP calls in the happy path (submit → status → result)
and avoids egress routing quirks on edge networks.

Pricing
-------
$0.04 per image for ``fal-ai/flux-pro/kontext``, independent of output
megapixels. Tracked in ``settings.model_cost_fal_flux`` and by the
``ratemeai_fal_calls_total`` Prometheus counter.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import random
import time
from typing import Any

import httpx
from PIL import Image

from src.providers.base import ImageGenProvider
from src.services.ai_transfer_guard import assert_external_transfer_allowed

_SEED_MAX = 2**31 - 1
_SEED_RNG = random.SystemRandom()

logger = logging.getLogger(__name__)


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


class FalFluxImageGen(ImageGenProvider):
    """FAL.ai FLUX.1 Kontext [pro] client (image-to-image edit)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/flux-pro/kontext",
        api_host: str = "https://queue.fal.run",
        guidance_scale: float = 3.5,
        safety_tolerance: str = "2",
        output_format: str = "jpeg",
        max_retries: int = 2,
        request_timeout: float = 180.0,
        poll_interval: float = 1.5,
    ):
        self._key = (api_key or "").strip()
        if not self._key:
            raise ValueError("FAL_API_KEY is required for FalFluxImageGen")
        self._model = model.strip().strip("/")
        self._host = (api_host or "https://queue.fal.run").rstrip("/")
        self._guidance_scale = float(guidance_scale)
        self._safety_tolerance = str(safety_tolerance)
        self._output_format = output_format.lower()
        if self._output_format not in ("jpeg", "png"):
            self._output_format = "jpeg"
        self._max_retries = max(1, int(max_retries))
        self._timeout = float(request_timeout)
        self._poll_interval = max(0.25, float(poll_interval))

    async def close(self) -> None:
        pass

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

    def _data_url(self, reference_image: bytes) -> str:
        mime = self._sniff_mime(reference_image)
        return f"data:{mime};base64,{self._b64(reference_image)}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Key {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _submit_url(self) -> str:
        return f"{self._host}/{self._model}"

    def _fallback_status_url(self, request_id: str) -> str:
        """Only used when the submit response forgot to include ``status_url``.

        FAL has been observed to omit it for very old app-ids. For the
        Kontext family the real ``status_url`` is always returned by the
        submit endpoint, so this fallback is a last-resort safety net.
        """
        # Strip the sub-path from the model: ``fal-ai/flux-pro/kontext``
        # routes status to ``fal-ai/flux-pro`` on the queue host.
        parts = self._model.split("/")
        app_root = "/".join(parts[:2]) if len(parts) >= 2 else self._model
        return f"{self._host}/{app_root}/requests/{request_id}/status"

    def _fallback_result_url(self, request_id: str) -> str:
        parts = self._model.split("/")
        app_root = "/".join(parts[:2]) if len(parts) >= 2 else self._model
        return f"{self._host}/{app_root}/requests/{request_id}"

    def _build_body(
        self,
        prompt: str,
        reference_image: bytes,
        params: dict | None,
    ) -> dict[str, Any]:
        """Strict whitelist body for FLUX Kontext Pro.

        ``sync_mode=True`` instructs FAL to inline the result as a data
        URI so we can decode it directly after the result GET without a
        second fetch.
        """
        if not reference_image:
            raise ValueError("FAL FLUX Kontext requires reference_image")

        body: dict[str, Any] = {
            "prompt": prompt,
            "image_url": self._data_url(reference_image),
            "guidance_scale": self._guidance_scale,
            "num_images": 1,
            "output_format": self._output_format,
            "safety_tolerance": self._safety_tolerance,
            "sync_mode": True,
        }

        extras = params or {}
        seed = extras.get("seed")
        if isinstance(seed, int):
            body["seed"] = seed
        else:
            # Default to a fresh random seed on every call. FLUX Kontext is
            # composition-conservative with the reference image — rotating
            # the seed gives a small but consistent diversity boost without
            # costing anything extra (one generation per request).
            body["seed"] = _SEED_RNG.randrange(1, _SEED_MAX)
        aspect_ratio = extras.get("aspect_ratio")
        if isinstance(aspect_ratio, str) and aspect_ratio:
            body["aspect_ratio"] = aspect_ratio
        if extras.get("enhance_prompt") is True:
            body["enhance_prompt"] = True
        return body

    # ------------------------------------------------------------------
    # Error parsing
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

        body_snippet = ""
        if raw_text and status != 429 and status >= 400:
            snippet = raw_text.strip().replace("\n", " ")
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            body_snippet = snippet
            logger.warning(
                "FAL %s %d error (req=%s): %s",
                phase, status, request_id, raw_text[:500],
            )

        full_msg = f"http={status} phase={phase} {message or 'FAL error'}"
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
    # Sync HTTP flow (run inside asyncio.to_thread)
    # ------------------------------------------------------------------

    def _submit(
        self, client: httpx.Client, body: dict[str, Any],
    ) -> tuple[str, str, str]:
        """Return ``(request_id, status_url, response_url)``.

        We always prefer the URLs returned by FAL itself — they are the
        only shape guaranteed to resolve for every model, including
        multi-segment apps like ``fal-ai/flux-pro/kontext``.
        """
        resp = client.post(
            self._submit_url(), json=body, headers=self._headers(),
        )
        if resp.status_code >= 400:
            raise self._parse_error(resp, phase="submit")
        try:
            data = resp.json()
        except Exception as exc:
            raise FalAPIError(
                f"FAL submit: cannot parse response ({exc})",
                status_code=resp.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise FalAPIError(
                "FAL submit: response is not a JSON object",
                status_code=resp.status_code,
            )
        request_id = (
            data.get("request_id")
            or resp.headers.get("x-fal-request-id")
        )
        if not request_id:
            raise FalAPIError(
                "FAL submit: response missing request_id",
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
        url = status_url
        while True:
            if time.monotonic() >= deadline:
                raise FalAPIError(
                    f"FAL timeout after {self._timeout}s (req={request_id})",
                    status_code=None, request_id=request_id,
                )
            resp = client.get(url, headers=self._headers())
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
                    reason = str(data.get("error") or data.get("detail") or "")
                raise FalAPIError(
                    f"FAL queue status={status} req={request_id} {reason}".strip(),
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
                f"FAL result: cannot parse response ({exc})",
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
                "FAL result: payload is not a JSON object",
                request_id=request_id,
            )
        if data.get("has_nsfw_concepts"):
            flags = data.get("has_nsfw_concepts")
            if isinstance(flags, list) and any(bool(x) for x in flags):
                raise FalContentViolationError(
                    "FAL: NSFW content detected",
                    status_code=200,
                    error_code="NSFW",
                    request_id=request_id,
                )
        images = data.get("images") or []
        if not isinstance(images, list) or not images:
            raise FalAPIError(
                "FAL result: no images in response",
                request_id=request_id,
            )
        first = images[0] if isinstance(images[0], dict) else {}
        url = str(first.get("url") or "")
        if not url:
            raise FalAPIError(
                "FAL result: image entry missing 'url'",
                request_id=request_id,
            )
        if url.startswith("data:"):
            try:
                _, payload = url.split(",", 1)
            except ValueError as exc:
                raise FalAPIError(
                    f"FAL result: malformed data URI ({exc})",
                    request_id=request_id,
                ) from exc
            try:
                return base64.b64decode(payload)
            except Exception as exc:
                raise FalAPIError(
                    f"FAL result: malformed base64 ({exc})",
                    request_id=request_id,
                ) from exc
        img_resp = client.get(url)
        if img_resp.status_code >= 400:
            raise FalAPIError(
                f"FAL image download failed http={img_resp.status_code}",
                status_code=img_resp.status_code, request_id=request_id,
            )
        return img_resp.content

    def _generate_sync(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> bytes:
        if not reference_image:
            raise ValueError(
                "FalFluxImageGen requires reference_image "
                "(FLUX Kontext Pro is an image-to-image model)"
            )
        body = self._build_body(prompt, reference_image, params)
        logger.info(
            "FAL request model=%s prompt_len=%d keys=%s",
            self._model, len(prompt or ""), sorted(body.keys()),
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
                    logger.warning(
                        "FAL rate-limited, no retries left "
                        "(attempt %d/%d, req=%s)",
                        attempt + 1, self._max_retries, e.request_id,
                    )
                    break
                wait = e.retry_after or (5 * (attempt + 1))
                logger.warning(
                    "FAL rate-limited, waiting %ss "
                    "(attempt %d/%d, req=%s)",
                    wait, attempt + 1, self._max_retries, e.request_id,
                )
                time.sleep(float(wait))
            except FalAPIError as e:
                last_err = e
                retryable = (
                    e.status_code is None
                    or (isinstance(e.status_code, int) and e.status_code >= 500)
                )
                if not retryable:
                    logger.exception(
                        "FAL API error (no retry, status=%s, code=%s, req=%s): %s",
                        e.status_code, e.error_code, e.request_id, e.message,
                    )
                    raise RuntimeError(f"FAL API error: {e.message}") from e
                if attempt + 1 >= self._max_retries:
                    logger.warning(
                        "FAL transient error, no retries left "
                        "(attempt %d/%d, status=%s): %s",
                        attempt + 1, self._max_retries, e.status_code, e.message,
                    )
                    break
                wait = 2 * (attempt + 1)
                logger.warning(
                    "FAL transient error (status=%s), retrying in %ss "
                    "(attempt %d/%d): %s",
                    e.status_code, wait, attempt + 1, self._max_retries, e.message,
                )
                time.sleep(float(wait))
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = e
                if attempt + 1 >= self._max_retries:
                    logger.warning(
                        "FAL transport error, no retries left "
                        "(attempt %d/%d): %s",
                        attempt + 1, self._max_retries, e,
                    )
                    break
                wait = 2 * (attempt + 1)
                logger.warning(
                    "FAL transport error, retrying in %ss "
                    "(attempt %d/%d): %s",
                    wait, attempt + 1, self._max_retries, e,
                )
                time.sleep(float(wait))

        msg = getattr(last_err, "message", None) or str(last_err)
        raise RuntimeError(
            f"FAL failed after {self._max_retries} attempt(s): {msg}"
        ) from last_err

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        assert_external_transfer_allowed("fal_flux")
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
            raise RuntimeError(f"FAL: empty/invalid image ({exc})") from exc


__all__ = [
    "FalFluxImageGen",
    "FalAPIError",
    "FalRateLimitError",
    "FalContentViolationError",
]

"""FAL.ai FLUX.2 [pro] image-gen provider (edit endpoint).

Active runtime provider for all face-preserving edit scenarios
(dating / cv / social / emoji). Succeeds the older Kontext-based
``FalFluxImageGen`` — the two classes share the same queue-submit /
poll / fetch / decode wire protocol, but FLUX.2 Pro Edit has a
materially different input shape:

- ``image_urls`` is a list of references (supports multi-reference
  out of the box) — we always send ``[reference_image]`` today, but
  the list signature unlocks style-reference photos later without a
  schema change.
- ``image_size`` replaces Kontext's ``aspect_ratio``. It accepts both
  a preset enum (``square_hd``, ``portrait_4_3`` …) and a custom
  ``{"width": W, "height": H}`` dict. This is the main reason we
  migrated: FLUX.2 Pro can actually produce 2 MP / 4 MP portraits,
  Kontext Pro was hard-capped at ~1 MP with no size control.
- No ``guidance_scale`` / ``enhance_prompt`` knobs (the model auto-
  tunes both). Prompt adherence is driven by the prompt itself.

See ``src/providers/image_gen/fal_flux.py`` for the wire-level design
notes (why direct httpx, why queue submit/poll, why data URIs). The
invariants below are identical to the Kontext provider; only the
body differs.

Pricing
-------
``fal-ai/flux-2-pro/edit`` bills $0.03 for the first output megapixel
plus $0.015 per additional megapixel, rounded up, capped at 4 MP.
We run at 2 MP by default (portrait 4:3 → ≈1280×1600). The cost
observer in ``src/metrics.py`` computes the per-call dollar amount
from ``image_size`` to keep Prometheus accurate.
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
from src.providers.image_gen.fal_flux import (
    FalAPIError,
    FalContentViolationError,
    FalRateLimitError,
)
from src.services.ai_transfer_guard import assert_external_transfer_allowed

_SEED_MAX = 2**31 - 1
_SEED_RNG = random.SystemRandom()

logger = logging.getLogger(__name__)

# FLUX.2 Pro Edit preset sizes accepted verbatim by the API.
_PRESET_IMAGE_SIZES = frozenset({
    "auto",
    "square_hd",
    "square",
    "portrait_4_3",
    "portrait_16_9",
    "landscape_4_3",
    "landscape_16_9",
})


class FalFlux2ImageGen(ImageGenProvider):
    """FAL.ai FLUX.2 [pro] edit client (image-to-image edit, up to 4 MP)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/flux-2-pro/edit",
        api_host: str = "https://queue.fal.run",
        safety_tolerance: str = "2",
        output_format: str = "jpeg",
        default_image_size: Any = "portrait_4_3",
        max_retries: int = 2,
        request_timeout: float = 180.0,
        poll_interval: float = 1.5,
    ):
        self._key = (api_key or "").strip()
        if not self._key:
            raise ValueError("FAL_API_KEY is required for FalFlux2ImageGen")
        self._model = model.strip().strip("/")
        self._host = (api_host or "https://queue.fal.run").rstrip("/")
        tol = str(safety_tolerance or "2").strip()
        if tol not in {"1", "2", "3", "4", "5"}:
            tol = "2"
        self._safety_tolerance = tol
        self._output_format = output_format.lower()
        if self._output_format not in ("jpeg", "png"):
            self._output_format = "jpeg"
        self._default_image_size = default_image_size
        self._max_retries = max(1, int(max_retries))
        self._timeout = float(request_timeout)
        self._poll_interval = max(0.25, float(poll_interval))

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Helpers (mirrors FalFluxImageGen — same wire contract)
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
        parts = self._model.split("/")
        # Strip trailing ``/edit`` sub-path for status host parity with
        # the Kontext provider's fallback logic.
        app_root = "/".join(parts[:2]) if len(parts) >= 2 else self._model
        return f"{self._host}/{app_root}/requests/{request_id}/status"

    def _fallback_result_url(self, request_id: str) -> str:
        parts = self._model.split("/")
        app_root = "/".join(parts[:2]) if len(parts) >= 2 else self._model
        return f"{self._host}/{app_root}/requests/{request_id}"

    # ------------------------------------------------------------------
    # Body builder — FLUX.2 Pro Edit specific
    # ------------------------------------------------------------------

    @classmethod
    def _normalize_image_size(cls, value: Any) -> Any | None:
        """Return a value safe to put on the wire as ``image_size``.

        Accepts either a preset enum string (``portrait_4_3`` …) or a
        ``{"width": int, "height": int}`` dict. Unknown strings and
        malformed dicts fall back to ``None`` so the provider can
        substitute the configured default.
        """
        if isinstance(value, str):
            v = value.strip()
            if v in _PRESET_IMAGE_SIZES:
                return v
            return None
        if isinstance(value, dict):
            w = value.get("width")
            h = value.get("height")
            try:
                wi, hi = int(w), int(h)
            except (TypeError, ValueError):
                return None
            if wi < 64 or hi < 64 or wi > 4096 or hi > 4096:
                return None
            return {"width": wi, "height": hi}
        return None

    def _build_body(
        self,
        prompt: str,
        reference_image: bytes,
        params: dict | None,
    ) -> dict[str, Any]:
        """Strict whitelist body for FLUX.2 Pro Edit.

        ``sync_mode=True`` inlines the result as a data URI so we can
        decode it directly from the result GET, same as Kontext.
        ``image_urls`` is a **list** even for the single-reference
        case — the FLUX.2 schema requires it.
        """
        if not reference_image:
            raise ValueError("FAL FLUX.2 Pro Edit requires reference_image")

        body: dict[str, Any] = {
            "prompt": prompt,
            "image_urls": [self._data_url(reference_image)],
            "num_images": 1,
            "output_format": self._output_format,
            "safety_tolerance": self._safety_tolerance,
            "enable_safety_checker": True,
            "sync_mode": True,
        }

        extras = params or {}
        seed = extras.get("seed")
        if isinstance(seed, int):
            body["seed"] = seed
        else:
            # Default to a fresh random seed per call. Diversity service
            # relies on this for variant rotation without paying for a
            # second generation (see src/services/variation.py).
            body["seed"] = _SEED_RNG.randrange(1, _SEED_MAX)

        size = self._normalize_image_size(extras.get("image_size"))
        if size is None:
            size = self._normalize_image_size(self._default_image_size)
        if size is not None:
            body["image_size"] = size
        return body

    # ------------------------------------------------------------------
    # Error parsing — identical shape to FalFluxImageGen
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
    # Sync HTTP flow — same 3-step protocol as the Kontext provider
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
                "FalFlux2ImageGen requires reference_image "
                "(FLUX.2 Pro Edit is an image-to-image model)"
            )
        body = self._build_body(prompt, reference_image, params)
        size_log = body.get("image_size", "default")
        logger.info(
            "FAL request model=%s prompt_len=%d size=%s keys=%s",
            self._model, len(prompt or ""), size_log, sorted(body.keys()),
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
        assert_external_transfer_allowed("fal_flux2")
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


__all__ = ["FalFlux2ImageGen"]

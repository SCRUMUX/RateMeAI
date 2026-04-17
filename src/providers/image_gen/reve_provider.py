from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Any

from src.providers.base import ImageGenProvider

logger = logging.getLogger(__name__)


class ReveImageGen(ImageGenProvider):
    """Reve API via official sync SDK; runs blocking calls in a thread pool.

    Политика вызовов: один биллящийся HTTP-запрос на generate().
    Ретрай только на 429 (rate-limit) — до `max_retries` попыток. На 5xx/network/прочие
    ошибки — моментальный fail, чтобы не дублировать оплату у провайдера.
    """

    def __init__(
        self,
        api_token: str,
        api_host: str,
        aspect_ratio: str = "1:1",
        version: str = "latest",
        test_time_scaling: int = 3,
        max_retries: int | None = None,
    ):
        self._token = api_token.strip()
        self._host = api_host.rstrip("/") if api_host else ""
        if not self._token:
            raise ValueError("REVE_API_TOKEN is required for ReveImageGen")
        self._aspect_ratio = aspect_ratio
        self._version = version
        self._test_time_scaling = test_time_scaling
        self._effects_logged = False
        if max_retries is None:
            try:
                from src.config import settings
                max_retries = int(getattr(settings, "reve_max_retries", 1))
            except Exception:
                max_retries = 1
        self._max_retries = max(1, int(max_retries))

    async def close(self) -> None:
        pass

    def _build_options(self, params: dict | None) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "aspect_ratio": self._aspect_ratio,
            "version": self._version,
            "test_time_scaling": self._test_time_scaling,
        }
        if params:
            for k in ("aspect_ratio", "version", "test_time_scaling", "postprocessing"):
                if k in params and params[k] is not None:
                    opts[k] = params[k]
        return opts

    @staticmethod
    def _mask_to_instruction_hint(params: dict | None) -> str:
        """Translate a mask region name into a textual hint for edit mode."""
        if not params:
            return ""
        region = params.get("mask_region", "")
        hints = {
            "background": "Change ONLY the background, keep the person untouched.",
            "clothing": "Change ONLY the clothing/outfit, keep face and background untouched.",
            "face": "Make subtle adjustments to lighting/expression on the face ONLY.",
        }
        return hints.get(region, "")

    def _log_available_effects(self, client: Any) -> None:
        """Log available Reve effects once for debugging."""
        if self._effects_logged:
            return
        self._effects_logged = True
        try:
            from reve.v1.image import list_effects
            effects = list_effects(client=client)
            if effects:
                names = [e.get("name", "?") for e in effects]
                logger.info("Reve available effects: %s", ", ".join(names))
            else:
                logger.info("Reve: no effects available")
        except Exception:
            logger.debug("Failed to list Reve effects", exc_info=True)

    def _generate_sync(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> bytes:
        from reve._client import ReveClient
        from reve.v1.image import create, edit, remix
        from reve.exceptions import ReveAPIError, ReveRateLimitError

        client = ReveClient(
            api_token=self._token,
            api_url=self._host or None,
        )
        self._log_available_effects(client)
        options = self._build_options(params)

        mask_image_bytes = params.get("mask_image") if params else None
        has_mask = bool(mask_image_bytes)
        use_edit = bool(params and params.get("use_edit")) or has_mask

        if has_mask:
            region_hint = self._mask_to_instruction_hint(params)
            if region_hint:
                prompt = f"{region_hint} {prompt}"

        for k in ("mask_image", "mask_region", "use_edit"):
            options.pop(k, None)

        last_err: Exception | None = None
        max_attempts = self._max_retries
        resp = None
        for attempt in range(max_attempts):
            try:
                if reference_image and use_edit:
                    edit_kwargs: dict[str, Any] = {
                        "edit_instruction": prompt,
                        "reference_image": reference_image,
                        "client": client,
                        **options,
                    }
                    if mask_image_bytes:
                        edit_kwargs["mask_image"] = mask_image_bytes
                    resp = edit(**edit_kwargs)
                elif reference_image:
                    resp = remix(
                        prompt,
                        [reference_image],
                        client=client,
                        **options,
                    )
                else:
                    resp = create(prompt, client=client, **options)
                break
            except ReveRateLimitError as e:
                last_err = e
                # 429 не биллится — можем ретраить, но только в пределах max_attempts.
                if attempt + 1 >= max_attempts:
                    logger.warning(
                        "Reve rate-limited, no retries left (attempt %d/%d)",
                        attempt + 1, max_attempts,
                    )
                    break
                wait = getattr(e, "retry_after", None) or (10 * (attempt + 1))
                logger.warning(
                    "Reve rate-limited, waiting %ss (attempt %d/%d)",
                    wait, attempt + 1, max_attempts,
                )
                time.sleep(float(wait))
            except ReveAPIError as e:
                # 5xx / прочие ошибки: НЕ ретраим (чтобы не получить двойной биллинг).
                msg = getattr(e, "message", None) or str(e)
                logger.exception("Reve API error (no retry): %s", msg)
                raise RuntimeError(f"Reve API error: {msg}") from e
        if resp is None:
            if last_err is not None:
                msg = getattr(last_err, "message", None) or str(last_err)
                raise RuntimeError(
                    f"Reve rate limit after {max_attempts} attempt(s): {msg}"
                ) from last_err
            raise RuntimeError("Reve: no response")

        if getattr(resp, "content_violation", False):
            raise RuntimeError("Reve: content policy violation")

        raw = getattr(resp, "image_bytes", None)
        if raw and len(raw) > 100:
            return raw

        buf = io.BytesIO()
        resp.image.save(buf, format="JPEG", quality=92)
        return buf.getvalue()

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        return await asyncio.to_thread(self._generate_sync, prompt, reference_image, params)

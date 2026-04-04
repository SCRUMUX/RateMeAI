from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from src.providers.base import ImageGenProvider

logger = logging.getLogger(__name__)


class ReveImageGen(ImageGenProvider):
    """Reve API via official sync SDK; runs blocking calls in a thread pool."""

    def __init__(
        self,
        api_token: str,
        api_host: str,
        aspect_ratio: str = "1:1",
        version: str = "latest",
        test_time_scaling: int = 3,
    ):
        self._token = api_token.strip()
        self._host = api_host.rstrip("/") if api_host else ""
        if not self._token:
            raise ValueError("REVE_API_TOKEN is required for ReveImageGen")
        self._aspect_ratio = aspect_ratio
        self._version = version
        self._test_time_scaling = test_time_scaling

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

    def _generate_sync(
        self,
        prompt: str,
        reference_image: bytes | None,
        params: dict | None,
    ) -> bytes:
        from reve._client import ReveClient
        from reve.v1.image import create, edit, remix
        from reve.exceptions import ReveAPIError

        client = ReveClient(
            api_token=self._token,
            api_url=self._host or None,
        )
        options = self._build_options(params)
        use_edit = bool(params and params.get("use_edit"))

        try:
            if reference_image and use_edit:
                resp = edit(
                    edit_instruction=prompt,
                    reference_image=reference_image,
                    client=client,
                    **options,
                )
            elif reference_image:
                resp = remix(
                    prompt,
                    [reference_image],
                    client=client,
                    **options,
                )
            else:
                resp = create(prompt, client=client, **options)
        except ReveAPIError as e:
            msg = getattr(e, "message", None) or str(e)
            logger.exception("Reve API error: %s", msg)
            raise RuntimeError(f"Reve API error: {msg}") from e

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

from __future__ import annotations

import base64
import json
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from src.providers.base import LLMProvider
from src.services.ai_transfer_guard import assert_external_transfer_allowed

logger = logging.getLogger(__name__)


# HTTP statuses worth a retry: 408 (request timeout), 429 (rate limit),
# 5xx (server/proxy errors). 4xx other than 408/429 (401/403/404/422) are
# terminal — retry would only waste time and our ARQ job_timeout budget.
_RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _is_retryable_openrouter(exc: BaseException) -> bool:
    # Network-level timeouts / connection issues → always retry.
    if isinstance(exc, (
        httpx.TimeoutException,       # covers ReadTimeout, WriteTimeout, ConnectTimeout, PoolTimeout
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        httpx.NetworkError,
    )):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            return exc.response.status_code in _RETRYABLE_STATUSES
        except Exception:
            return False
    return False


class OpenRouterLLM(LLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        # Split timeout: quick connect (10s), moderate read/write (30s).
        # Budget: worst case 3 tenacity attempts × 30s read + 2+4 backoff
        # ≈ 96s, which fits into the ARQ job_timeout (300s after B5).
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable_openrouter),
    )
    async def analyze_image(
        self, image_bytes: bytes, prompt: str, *, temperature: float = 0.7,
    ) -> dict:
        assert_external_transfer_allowed("openrouter")
        b64 = base64.b64encode(image_bytes).decode()
        data_url = f"data:image/jpeg;base64,{b64}"

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": 2000,
        }

        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        return self._parse_json(content)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable_openrouter),
    )
    async def compare_images(
        self,
        image_a_bytes: bytes,
        image_b_bytes: bytes,
        prompt: str,
        *,
        temperature: float = 0.0,
    ) -> dict:
        """Send two images + prompt to the VLM in a single call.

        Used by the quality-gate runner for stateless identity-preservation
        checking (see QualityGateRunner._get_quality_metrics). No face
        geometry is extracted, the VLM performs a holistic visual
        comparison and returns a scalar ``identity_match`` score.
        """
        assert_external_transfer_allowed("openrouter")
        b64_a = base64.b64encode(image_a_bytes).decode()
        b64_b = base64.b64encode(image_b_bytes).decode()

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_a}"}},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_b}"}},
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": 2000,
        }

        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return self._parse_json(content)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable_openrouter),
    )
    async def generate_text(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 2000,
        }

        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse LLM JSON output into a dict.

        Gemini (via OpenRouter) occasionally wraps its ``json_object`` response
        in a single-item array despite the explicit ``response_format`` hint —
        e.g. ``[{"identity_match": 7.5, ...}]`` instead of ``{...}``. We
        transparently unwrap that case. Any other non-object payload is a
        real protocol violation and raises ``ValueError`` so that callers
        (quality_gates._get_quality_metrics) can surface it as a check
        failure instead of crashing with ``AttributeError: 'list' object
        has no attribute 'get'``.
        """
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # remove ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
            return parsed[0]
        raise ValueError(
            f"LLM returned non-object JSON (type={type(parsed).__name__}); expected a JSON object"
        )

    async def close(self):
        await self._client.aclose()

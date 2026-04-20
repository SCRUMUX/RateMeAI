from __future__ import annotations

import base64
import json
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.providers.base import LLMProvider
from src.services.ai_transfer_guard import assert_external_transfer_allowed

logger = logging.getLogger(__name__)


class OpenRouterLLM(LLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=60.0)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
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
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
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
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
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
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # remove ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)

    async def close(self):
        await self._client.aclose()

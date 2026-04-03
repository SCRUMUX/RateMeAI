from __future__ import annotations

from src.providers.base import LLMProvider


class MockLLM(LLMProvider):
    """Deterministic mock for testing."""

    async def analyze_image(self, image_bytes: bytes, prompt: str) -> dict:
        return {
            "score": 7.5,
            "perception": {
                "trust": 8.0,
                "attractiveness": 7.0,
                "emotional_expression": "уверенность",
            },
            "insights": [
                "Прямой взгляд в камеру создаёт ощущение уверенности",
                "Естественная улыбка добавляет располагающий эффект",
            ],
            "recommendations": [
                "Попробуй фронтальное освещение для более мягких теней",
                "Лёгкий наклон головы добавит динамики",
            ],
        }

    async def generate_text(self, prompt: str) -> str:
        return "Mock text response"

    async def close(self):
        pass

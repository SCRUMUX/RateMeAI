"""Test/dev-only providers.

This package is deliberately prefixed with an underscore so it reads as
internal: ``MockImageGen`` and ``MockLLM`` are *not* production code and
must only be instantiated by the factory when no real credentials are
available (dev-loopback) or by unit tests that want a deterministic
provider response.
"""
from src.providers._testing.mock_image_gen import MockImageGen
from src.providers._testing.mock_llm import MockLLM

__all__ = ["MockImageGen", "MockLLM"]

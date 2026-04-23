"""Deprecated shim. Moved to :mod:`src.providers._testing.mock_image_gen`.

Kept so existing imports (tests, third-party scripts) keep working while
we migrate. New code must import from ``src.providers._testing``.
"""

from src.providers._testing.mock_image_gen import MockImageGen

__all__ = ["MockImageGen"]

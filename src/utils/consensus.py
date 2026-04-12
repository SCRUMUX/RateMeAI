"""Consensus scoring: average multiple LLM calls for reproducible results."""
from __future__ import annotations

import asyncio
import logging
from statistics import median

from src.providers.base import LLMProvider

logger = logging.getLogger(__name__)


async def consensus_analyze(
    llm: LLMProvider,
    image_bytes: bytes,
    prompt: str,
    *,
    temperature: float = 0.0,
    n: int = 1,
) -> dict:
    """Run ``n`` LLM analyses and return a median-merged result.

    When *n* <= 1 this is equivalent to a single ``llm.analyze_image`` call.
    """
    if n <= 1:
        return await llm.analyze_image(image_bytes, prompt, temperature=temperature)

    results = await asyncio.gather(
        *[llm.analyze_image(image_bytes, prompt, temperature=temperature) for _ in range(n)],
        return_exceptions=True,
    )
    valid = [r for r in results if isinstance(r, dict)]
    if not valid:
        raise RuntimeError("All consensus calls failed")

    if len(valid) == 1:
        return valid[0]

    return _median_dict(valid)


def _median_dict(dicts: list[dict]) -> dict:
    """Merge a list of dicts by taking median for numeric values, recursing into nested dicts."""
    merged: dict = {}
    keys = {k for d in dicts for k in d}

    for key in keys:
        vals = [d[key] for d in dicts if key in d]
        if not vals:
            continue

        if all(isinstance(v, (int, float)) for v in vals):
            merged[key] = round(float(median(vals)), 2)
        elif all(isinstance(v, dict) for v in vals):
            merged[key] = _median_dict(vals)
        elif all(isinstance(v, list) for v in vals):
            longest = max(vals, key=len)
            merged[key] = longest
        else:
            merged[key] = vals[0]

    return merged

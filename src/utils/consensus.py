"""Consensus scoring: average multiple LLM calls for reproducible results."""

from __future__ import annotations

import asyncio
import logging
from statistics import median

from src.providers.base import LLMProvider

logger = logging.getLogger(__name__)


# Hard wall-clock cap on the whole consensus fan-out. Individual
# ``analyze_image`` calls already have their own httpx timeout + tenacity
# retries (~96s worst case), so the gather *can* in theory run that long
# per worker, but we don't want to eat the entire ARQ job_timeout budget
# on scoring alone. 60s is enough for 2-3 parallel successful calls and
# forces us to fail fast if the provider is visibly overloaded.
_CONSENSUS_WALL_TIMEOUT_S = 60.0


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
    The whole fan-out is capped at :data:`_CONSENSUS_WALL_TIMEOUT_S` — if
    the provider is slow enough that the gather cannot finish in time,
    we surface a ``TimeoutError`` to the caller (worker classifies it as
    transient; the rest of the pipeline won't start with partial data).
    """
    if n <= 1:
        # Apply the same wall-clock cap to the n=1 case. Previously a hung
        # provider could hold the worker slot for the full tenacity budget
        # (~96s) blocking the ARQ job_timeout. Now a slow provider fails
        # fast and the worker can accept the next job.
        try:
            return await asyncio.wait_for(
                llm.analyze_image(image_bytes, prompt, temperature=temperature),
                timeout=_CONSENSUS_WALL_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "consensus_analyze: n=1 wall-clock timeout after %.0fs",
                _CONSENSUS_WALL_TIMEOUT_S,
            )
            raise TimeoutError(
                f"analyze_image exceeded {_CONSENSUS_WALL_TIMEOUT_S:.0f}s wall clock"
            )

    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                *[
                    llm.analyze_image(image_bytes, prompt, temperature=temperature)
                    for _ in range(n)
                ],
                return_exceptions=True,
            ),
            timeout=_CONSENSUS_WALL_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "consensus_analyze: wall-clock timeout after %.0fs (n=%d)",
            _CONSENSUS_WALL_TIMEOUT_S,
            n,
        )
        raise TimeoutError(
            f"consensus gather exceeded {_CONSENSUS_WALL_TIMEOUT_S:.0f}s wall clock"
        )

    valid = [r for r in results if isinstance(r, dict)]
    if not valid:
        logger.warning("All consensus calls failed to return a valid dict. Returning empty dict as fallback.")
        return {}

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

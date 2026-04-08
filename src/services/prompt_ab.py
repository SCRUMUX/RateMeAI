"""Prompt A/B testing framework.

Stores prompt variant assignments per generation, tracks quality metrics
(identity_score, NIQE, aesthetic_score), and provides automatic variant
promotion when enough data accumulates.

Storage: Redis hash per experiment; lightweight and zero-migration.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_EXPERIMENT_PREFIX = "ratemeai:ab:"
_MIN_SAMPLES_FOR_PROMOTION = 30


@dataclass
class PromptVariant:
    name: str
    anchor_overrides: dict[str, str] = field(default_factory=dict)
    weight: float = 1.0


@dataclass
class ABExperiment:
    experiment_id: str
    variants: list[PromptVariant]
    metric_key: str = "identity_score"
    active: bool = True

    def pick_variant(self, seed: str) -> PromptVariant:
        """Deterministic variant assignment based on seed (task_id)."""
        h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
        total = sum(v.weight for v in self.variants)
        threshold = (h % 10000) / 10000.0 * total
        cumulative = 0.0
        for v in self.variants:
            cumulative += v.weight
            if threshold <= cumulative:
                return v
        return self.variants[-1]


_EXPERIMENTS: dict[str, ABExperiment] = {}


def register_experiment(experiment: ABExperiment) -> None:
    _EXPERIMENTS[experiment.experiment_id] = experiment
    logger.info("Registered A/B experiment: %s (%d variants)", experiment.experiment_id, len(experiment.variants))


def get_active_experiments() -> list[ABExperiment]:
    return [e for e in _EXPERIMENTS.values() if e.active]


def assign_variant(experiment_id: str, task_id: str) -> PromptVariant | None:
    exp = _EXPERIMENTS.get(experiment_id)
    if not exp or not exp.active:
        return None
    return exp.pick_variant(task_id)


async def record_result(
    redis,
    experiment_id: str,
    variant_name: str,
    metrics: dict[str, float],
) -> None:
    """Record metrics for a single generation under a variant."""
    if redis is None:
        return
    try:
        key = f"{_EXPERIMENT_PREFIX}{experiment_id}:{variant_name}"
        entry = {
            "t": int(time.time()),
            **{k: round(v, 4) for k, v in metrics.items()},
        }
        await redis.rpush(key, json.dumps(entry))
        await redis.expire(key, 86400 * 30)
    except Exception:
        logger.debug("Failed to record A/B result for %s/%s", experiment_id, variant_name)


async def get_experiment_stats(
    redis,
    experiment_id: str,
) -> dict[str, Any]:
    """Retrieve aggregate stats for all variants of an experiment."""
    exp = _EXPERIMENTS.get(experiment_id)
    if not exp or redis is None:
        return {}

    stats: dict[str, Any] = {}
    for variant in exp.variants:
        key = f"{_EXPERIMENT_PREFIX}{experiment_id}:{variant.name}"
        try:
            raw_entries = await redis.lrange(key, 0, -1)
            entries = [json.loads(e) for e in raw_entries]
            if not entries:
                stats[variant.name] = {"n": 0}
                continue

            metric_values = [e.get(exp.metric_key, 0) for e in entries if exp.metric_key in e]
            n = len(metric_values)
            stats[variant.name] = {
                "n": n,
                "mean": round(sum(metric_values) / n, 4) if n else 0,
                "min": round(min(metric_values), 4) if n else 0,
                "max": round(max(metric_values), 4) if n else 0,
            }
        except Exception:
            stats[variant.name] = {"n": 0, "error": True}

    return stats


async def check_and_promote(
    redis,
    experiment_id: str,
) -> str | None:
    """Check if a variant has enough data and a clear win. Returns winner name or None."""
    exp = _EXPERIMENTS.get(experiment_id)
    if not exp:
        return None

    stats = await get_experiment_stats(redis, experiment_id)
    candidates = [(name, s) for name, s in stats.items() if s.get("n", 0) >= _MIN_SAMPLES_FOR_PROMOTION]

    if len(candidates) < 2:
        return None

    best_name = max(candidates, key=lambda x: x[1]["mean"])[0]
    second = sorted(candidates, key=lambda x: x[1]["mean"], reverse=True)[1]

    improvement = (candidates[0][1]["mean"] - second[1]["mean"]) / max(second[1]["mean"], 0.01)
    if improvement >= 0.05:
        logger.info(
            "A/B experiment %s: variant '%s' wins (mean=%.4f vs %.4f, +%.1f%%)",
            experiment_id, best_name,
            max(c[1]["mean"] for c in candidates),
            second[1]["mean"],
            improvement * 100,
        )
        return best_name

    return None


def apply_variant_overrides(base_anchors: dict[str, str], variant: PromptVariant) -> dict[str, str]:
    """Apply a variant's anchor overrides to the base anchor set."""
    result = dict(base_anchors)
    result.update(variant.anchor_overrides)
    return result

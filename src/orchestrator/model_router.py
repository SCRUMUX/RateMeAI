"""Smart model router: dynamic provider selection based on capability, cost, and budget.

Each registered model has a cost estimate, quality tier, and capability set.
The router picks the best provider for each pipeline step while respecting budget.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.providers.base import ImageGenProvider

logger = logging.getLogger(__name__)


@dataclass
class ModelSpec:
    name: str
    provider: ImageGenProvider
    capabilities: set[str] = field(default_factory=lambda: {"remix"})
    cost_per_call: float = 0.02
    avg_latency_ms: int = 5000
    quality_tier: int = 2  # 1=best, 3=economy

    @property
    def effective_score(self) -> float:
        """Lower is better: combines tier and cost."""
        return self.quality_tier + self.cost_per_call * 10


class ModelRouter:
    """Select the best image-gen provider for a given pipeline step."""

    def __init__(self, models: list[ModelSpec] | None = None):
        self._models: list[ModelSpec] = models or []

    def register(self, spec: ModelSpec) -> None:
        self._models.append(spec)

    @property
    def cheapest_cost(self) -> float:
        if not self._models:
            return 0.0
        return min(m.cost_per_call for m in self._models)

    def select(
        self,
        required_capability: str,
        remaining_budget: float,
    ) -> tuple[ModelSpec, dict] | None:
        """Pick the best model that fits budget and has the required capability.

        Returns (ModelSpec, extra_params) or None if nothing fits.
        """
        candidates = [
            m for m in self._models
            if required_capability in m.capabilities and m.cost_per_call <= remaining_budget
        ]
        if not candidates:
            candidates = [
                m for m in self._models
                if "remix" in m.capabilities and m.cost_per_call <= remaining_budget
            ]

        if not candidates:
            return None

        candidates.sort(key=lambda m: m.effective_score)
        best = candidates[0]

        extra: dict = {}
        if "edit" in best.capabilities and required_capability == "edit":
            extra["use_edit"] = True

        logger.info(
            "ModelRouter selected %s (tier=%d, cost=$%.3f) for capability=%s, budget_left=$%.3f",
            best.name, best.quality_tier, best.cost_per_call,
            required_capability, remaining_budget,
        )
        return best, extra


def build_model_registry(
    image_gen: ImageGenProvider | None,
    cost_reve: float = 0.02,
    cost_replicate: float = 0.05,
) -> ModelRouter:
    """Build a ModelRouter from the given image_gen provider (or chain)."""
    router = ModelRouter()

    if image_gen is None:
        return router

    from src.providers.image_gen.chain import ChainImageGen
    from src.providers.image_gen.reve_provider import ReveImageGen
    from src.providers.image_gen.replicate import ReplicateImageGen
    from src.providers.image_gen.mock import MockImageGen

    if isinstance(image_gen, ChainImageGen):
        providers = image_gen.providers
    else:
        providers = [image_gen]

    for p in providers:
        if isinstance(p, ReveImageGen):
            router.register(ModelSpec(
                name="reve_remix",
                provider=p,
                capabilities={"remix", "edit"},
                cost_per_call=cost_reve,
                avg_latency_ms=5000,
                quality_tier=2,
            ))
        elif isinstance(p, ReplicateImageGen):
            router.register(ModelSpec(
                name="replicate_flux",
                provider=p,
                capabilities={"remix", "inpaint", "edit"},
                cost_per_call=cost_replicate,
                avg_latency_ms=8000,
                quality_tier=1,
            ))
        elif isinstance(p, MockImageGen):
            router.register(ModelSpec(
                name="mock",
                provider=p,
                capabilities={"remix", "edit", "inpaint"},
                cost_per_call=0.0,
                avg_latency_ms=100,
                quality_tier=3,
            ))
        else:
            router.register(ModelSpec(
                name=type(p).__name__,
                provider=p,
                capabilities={"remix"},
                cost_per_call=cost_replicate,
                quality_tier=2,
            ))

    return router

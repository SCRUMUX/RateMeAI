"""Public registry API for scenarios."""

from __future__ import annotations

from src.scenarios.loader import load_scenarios
from src.scenarios.models import Scenario, ScenarioKind


def get_scenario(slug: str) -> Scenario | None:
    if not slug:
        return None
    return load_scenarios().get(slug)


def list_scenarios(kind: ScenarioKind | None = None) -> list[Scenario]:
    """Return all loaded scenarios, optionally filtered by kind.

    Includes scenarios with ``enabled=False`` — callers that need only
    the live set should use :func:`list_enabled_scenarios`.
    """

    items = list(load_scenarios().values())
    if kind is not None:
        items = [s for s in items if s.kind == kind]
    return sorted(items, key=lambda s: s.slug)


def list_enabled_scenarios(kind: ScenarioKind | None = None) -> list[Scenario]:
    return [s for s in list_scenarios(kind=kind) if s.enabled]

"""Variation Engine for handling user inputs and style variations."""

from typing import Any
import random

from src.prompts.style_spec import StructuredStyleSpec, StyleType


class VariationEngine:
    """Handles user input mapping and variation selection."""

    @staticmethod
    def apply_variation(spec: StructuredStyleSpec, user_input: dict[str, Any]) -> str:
        """Apply user input to the style spec, respecting its type constraints."""

        # Start with base scene
        scene = spec.base_scene

        # Handle variations based on style type
        if spec.type == StyleType.SCENE_LOCKED:
            # Cannot change base scene, only allowed variations (lighting, weather, etc)
            if user_input.get("lighting") in spec.allowed_variations:
                scene += f", {user_input['lighting']} lighting"
            if user_input.get("weather") in spec.allowed_variations:
                scene += f", {user_input['weather']} weather"

        elif spec.type == StyleType.SEMI_LOCKED:
            # Can change sub-locations if allowed
            if user_input.get("sub_location") in spec.allowed_variations:
                scene = f"{user_input['sub_location']} in {spec.base_scene}"

        elif spec.type == StyleType.FLEXIBLE:
            # Can change scene entirely if requested
            if user_input.get("scene_override"):
                scene = user_input["scene_override"]

        # Always allow clothing changes if provided
        clothing = user_input.get("clothing_override", spec.clothing)

        return f"{scene}. Subject is wearing {clothing}."

    @staticmethod
    def get_random_variation(spec: StructuredStyleSpec) -> dict[str, str]:
        """Pick a random allowed variation for the 'Другой вариант' button."""
        if not spec.allowed_variations:
            return {}

        # Pick 1-2 random variations to keep cost down
        num_vars = random.randint(1, min(2, len(spec.allowed_variations)))
        chosen = random.sample(spec.allowed_variations, num_vars)

        # Map them to generic variation keys
        return {"variation_hints": ", ".join(chosen)}

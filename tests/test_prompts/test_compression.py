"""Regression tests for :func:`src.prompts.compression.compress_prompt`.

The May 2026 audit found that the historical ``noise_words`` list
contained ``"in the background"`` / ``"in the foreground"`` — both of
which are load-bearing tokens in catalogue triggers like
``"Eiffel Tower in the background"`` (see
``data/styles.json::dating.paris_eiffel.trigger_pool``). With those
phrases stripped, the spatial anchor collapsed to a bare landmark
name and edit-models routinely hallucinated the landmark as a
foreground prop.

These tests pin the fix:

1. The two phrases survive a ``compress_prompt`` round-trip for the
   canonical ``"Eiffel Tower in the background"`` trigger.
2. The remaining filler ``noise_words`` keep getting stripped (so we
   know the regex pipeline is still wired and the change is
   genuinely scoped to the spatial-anchor escape).
"""

from __future__ import annotations

import pytest

from src.prompts.compression import compress_prompt


class TestSpatialAnchorsSurvive:
    @pytest.mark.parametrize(
        "trigger",
        [
            "Eiffel Tower in the background",
            "Brooklyn Bridge in the background",
            "Tokyo Tower glowing in the background",
            "neon billboards in the foreground",
        ],
    )
    def test_background_anchor_round_trips(self, trigger: str) -> None:
        out = compress_prompt(trigger)
        assert "in the background" in out or "in the foreground" in out, (
            f"compress_prompt stripped the spatial anchor from {trigger!r}; "
            f"got {out!r}"
        )

    def test_full_prompt_keeps_background_anchor(self) -> None:
        prompt = (
            "A picture of a person standing near the Seine, "
            "Eiffel Tower in the background, golden hour, 35mm lens"
        )
        out = compress_prompt(prompt)
        assert "Eiffel Tower in the background" in out, out


class TestFillersStillStripped:
    @pytest.mark.parametrize(
        "filler",
        [
            "a picture of",
            "an image of",
            "a photo of",
            "showing",
            "depicting",
            "featuring",
            "there is",
            "we see",
        ],
    )
    def test_known_filler_is_removed(self, filler: str) -> None:
        prompt = f"{filler} a person on a rooftop"
        out = compress_prompt(prompt)
        assert filler not in out.lower(), (
            f"compress_prompt no longer strips {filler!r}: {out!r}"
        )

    def test_dedup_still_runs(self) -> None:
        out = compress_prompt("beautiful beautiful sunset over Paris")
        assert "beautiful beautiful" not in out
        assert "beautiful sunset" in out

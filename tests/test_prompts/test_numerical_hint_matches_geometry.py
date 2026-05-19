"""v1.68 — keep ``_COMPOSITION_NUMERICAL_HINT`` wording in lock-step
with ``_FRAMING_GEOMETRY``.

The textual doctrine (``_COMPOSITION_NUMERICAL_HINT`` in
:mod:`src.prompts.image_gen`) and the geometric doctrine
(``_FRAMING_GEOMETRY`` in
:mod:`src.services.reference_preprocess`) describe the same target
layout from two angles. v1.67 had them drift apart: the prompt said
``upper quarter of the canvas`` (= ~25%) while the geometry laid
out ``face_height_ratio=0.28`` (= ~28% / roughly upper third).
Edit-models receiving the two contradictory signals averaged them,
which contributed to the "head too small" complement of the "head
too large" pathology on tight selfies.

v1.68 re-aligned the two:

* portrait → ``upper third of the canvas height`` matches
  ``face_height_ratio=0.28`` and ``face_center_y_ratio=0.30``.
* half_body → ``upper fifth of the canvas height`` matches
  ``face_height_ratio=0.15``.
* full_body → ``roughly an eighth of the canvas height`` matches
  ``face_height_ratio=0.08``.

These tests guard the alignment as a structural contract — a maintainer
who tweaks one side WITHOUT touching the other will trip an assertion
here.
"""

from __future__ import annotations

import pytest

from src.prompts.image_gen import _COMPOSITION_NUMERICAL_HINT
from src.services.reference_preprocess import _FRAMING_GEOMETRY


# Per-framing canonical wording fragments. Each fragment must appear
# in the matching ``_COMPOSITION_NUMERICAL_HINT`` entry; if the prompt
# wording changes, this dict must change too — that is the point.
_EXPECTED_WORDING: dict[str, tuple[str, ...]] = {
    "portrait": (
        "head-and-shoulders bust shot",
        "upper third of the canvas height",
    ),
    "half_body": (
        "medium waist-up shot",
        "upper fifth of the canvas height",
    ),
    "full_body": (
        "full-length standing shot",
        "an eighth of the canvas height",
    ),
}


@pytest.mark.parametrize("framing", sorted(_FRAMING_GEOMETRY))
def test_framings_covered_in_both_doctrines(framing: str):
    """Every framing key in ``_FRAMING_GEOMETRY`` MUST have a matching
    entry in ``_COMPOSITION_NUMERICAL_HINT`` (and vice versa)."""
    assert framing in _COMPOSITION_NUMERICAL_HINT, (
        f"framing={framing!r} missing in _COMPOSITION_NUMERICAL_HINT — "
        "doctrines drifted; add the matching prompt fragment."
    )


@pytest.mark.parametrize("framing", sorted(_COMPOSITION_NUMERICAL_HINT))
def test_no_extra_framings_in_hint(framing: str):
    assert framing in _FRAMING_GEOMETRY, (
        f"framing={framing!r} present in _COMPOSITION_NUMERICAL_HINT "
        "but missing in _FRAMING_GEOMETRY — geometry contract "
        "incomplete."
    )


@pytest.mark.parametrize("framing,fragments", list(_EXPECTED_WORDING.items()))
def test_hint_wording_contains_expected_canvas_fraction(
    framing: str, fragments: tuple[str, ...],
):
    """The hint string for each framing must contain the canonical
    wording fragments above — these encode the target face-height
    ratio in plain English so the edit-model and the geometry
    receive the same message."""
    hint = _COMPOSITION_NUMERICAL_HINT[framing]
    for fragment in fragments:
        assert fragment in hint, (
            f"framing={framing!r}: hint missing canonical fragment "
            f"{fragment!r}. The textual doctrine drifted away from "
            f"_FRAMING_GEOMETRY[{framing!r}]="
            f"{_FRAMING_GEOMETRY[framing]} — re-align before "
            "shipping.\nhint={hint!r}"
        )


def test_portrait_face_height_ratio_unchanged():
    """v1.68 explicitly aligned ``upper third`` with
    ``face_height_ratio=0.28``. If a future tweak changes the
    geometry value WITHOUT updating the prompt fragment, the
    doctrines will drift again — this assertion makes that drift
    impossible to land silently."""
    assert _FRAMING_GEOMETRY["portrait"]["face_height_ratio"] == pytest.approx(0.28), (
        "_FRAMING_GEOMETRY[portrait].face_height_ratio changed. Update "
        "the _COMPOSITION_NUMERICAL_HINT wording (currently 'upper "
        "third of the canvas height') so the two doctrines stay in "
        "sync, then update this assertion."
    )


def test_half_body_face_height_ratio_unchanged():
    assert _FRAMING_GEOMETRY["half_body"]["face_height_ratio"] == pytest.approx(0.15), (
        "_FRAMING_GEOMETRY[half_body].face_height_ratio changed. "
        "Update the _COMPOSITION_NUMERICAL_HINT wording ('upper fifth' "
        "currently) and this assertion together."
    )


def test_full_body_face_height_ratio_unchanged():
    assert _FRAMING_GEOMETRY["full_body"]["face_height_ratio"] == pytest.approx(0.08), (
        "_FRAMING_GEOMETRY[full_body].face_height_ratio changed. "
        "Update the _COMPOSITION_NUMERICAL_HINT wording ('an eighth' "
        "currently) and this assertion together."
    )

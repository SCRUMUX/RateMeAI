"""Pre-generation style × reference compatibility check (v1.14.2).

When the user picks a full-body style (yoga_outdoor, beach_sunset,
running, ...) but their reference is a tight head-crop selfie
(face_area_ratio > 0.35), FLUX Kontext Pro has nothing to anchor the
invented body to and consistently drifts off identity. The bot runs
``check_style_reference_compat`` right after style selection and
surfaces an explicit warning with a reupload / continue choice.
"""

from __future__ import annotations

import pytest

from src.services.input_quality import (
    FACE_TOO_TIGHT_FOR_BODY_THRESHOLD,
    check_style_reference_compat,
)
from src.services.photo_requirements import IssueCode


@pytest.mark.parametrize(
    "style_key",
    [
        "yoga_outdoor",
        "beach_sunset",
        "running",
        "swimming_pool",
        "hiking",
        "cycling",
    ],
)
def test_warn_for_full_body_style_with_tight_crop(style_key):
    issue = check_style_reference_compat(
        face_area_ratio=FACE_TOO_TIGHT_FOR_BODY_THRESHOLD + 0.05,
        mode="dating",
        style_key=style_key,
    )
    assert issue is not None
    assert issue.code == IssueCode.FACE_TOO_TIGHT_FOR_BODY_SHOT
    assert issue.severity == "warn"


def test_no_warn_when_face_ratio_below_threshold():
    """A photo that shows torso/shoulders (low face ratio) is fine."""
    issue = check_style_reference_compat(
        face_area_ratio=FACE_TOO_TIGHT_FOR_BODY_THRESHOLD - 0.05,
        mode="dating",
        style_key="yoga_outdoor",
    )
    assert issue is None


def test_no_warn_for_portrait_style_even_with_tight_crop():
    """Studio / coffee-date / cafe styles stay close-up, so the mismatch
    check must return None regardless of face_area_ratio."""
    for style in ("studio_elegant", "coffee_date", "cafe"):
        issue = check_style_reference_compat(
            face_area_ratio=0.45,
            mode="dating",
            style_key=style,
        )
        assert issue is None, f"unexpected warning for portrait style '{style}'"


def test_no_warn_for_unknown_style():
    issue = check_style_reference_compat(
        face_area_ratio=0.9,
        mode="dating",
        style_key="totally_made_up_style_42",
    )
    assert issue is None


def test_no_warn_for_cv_doc_styles():
    """CV document styles inherently crop to head/shoulders; never warn."""
    issue = check_style_reference_compat(
        face_area_ratio=0.6,
        mode="cv",
        style_key="photo_3x4",
    )
    assert issue is None

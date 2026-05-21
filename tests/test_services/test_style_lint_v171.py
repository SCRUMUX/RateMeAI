"""Unit tests for the v1.71 style-lint rules.

Two new codes added in v1.71:

* ``WARDROBE_POSE_LEAK`` (error) — ``default_clothing`` /
  ``clothing.default.*`` carries a position directive
  (``visible above desk``, ``headshot``, ``framed at the chest`` …).
  This is the regression that drove the v1.71 ``video_call`` hot-fix:
  pose-cues leaking through wardrobe override every framing /
  shoulder hint downstream and reproduce the "glued head" pathology.

* ``TIGHT_INDOOR_SCREEN_SCENE`` (warning) — ``scene_anchor`` /
  ``base_scene`` / ``background.base`` describe a screen-facing
  workspace (``ring light`` / ``monitor glow on the subject`` /
  ``webcam`` / ``camera on tripod``) without any spatial depth cue
  (``behind`` / ``across the room`` / ``floor`` / ``window`` …).
  Edit models associate the former cues with tight webcam-style
  crops; a depth cue gives them the perspective needed for a
  balanced full-body composition.
"""

from __future__ import annotations

from src.services.style_lint import lint_style


def _codes(issues) -> list[str]:
    return [i["code"] for i in issues]


# ---------------------------------------------------------------------------
# WARDROBE_POSE_LEAK
# ---------------------------------------------------------------------------


def test_wardrobe_pose_leak_fires_on_visible_above_desk():
    raw = {
        "id": "fictional_video_call",
        "schema_version": 3,
        "default_clothing": (
            "professional fitted shirt, crisp collar, clean grooming "
            "visible above desk, collar and shoulder seam clearly visible"
        ),
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    codes = _codes(issues)
    assert "WARDROBE_POSE_LEAK" in codes, codes
    leak = next(i for i in issues if i["code"] == "WARDROBE_POSE_LEAK")
    assert leak["severity"] == "error"
    assert leak["field"] == "default_clothing"
    tokens = leak["detail"]["tokens"]
    assert any("visible above" in t for t in tokens), tokens


def test_wardrobe_pose_leak_fires_on_headshot_in_clothing_default():
    raw = {
        "id": "fictional_headshot_style",
        "schema_version": 3,
        "clothing": {
            "default": {
                "male": "tailored blazer, neat headshot framing",
                "female": "tailored blazer, neat headshot framing",
                "neutral": "tailored blazer, neat headshot framing",
            }
        },
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    leak_fields = {
        i["field"]
        for i in issues
        if i["code"] == "WARDROBE_POSE_LEAK"
    }
    assert leak_fields == {
        "clothing.default.male",
        "clothing.default.female",
        "clothing.default.neutral",
    }


def test_wardrobe_pose_leak_silent_on_clean_garment_string():
    raw = {
        "id": "fictional_clean_wardrobe",
        "schema_version": 3,
        "default_clothing": (
            "tailored navy three-piece suit, well-fitted across the "
            "shoulders, crisp white shirt"
        ),
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "WARDROBE_POSE_LEAK" not in _codes(issues)


def test_wardrobe_pose_leak_skipped_for_document_styles():
    # Document styles legitimately encode a tight head-and-shoulders
    # framing; the v1.71 wardrobe-pose lint must respect the existing
    # anatomy-exempt whitelist so visa / passport styles don't flood
    # the admin warnings panel.
    raw = {
        "id": "passport_rf",
        "schema_version": 3,
        "default_clothing": "neutral business top, head-and-shoulders crop",
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "WARDROBE_POSE_LEAK" not in _codes(issues)


# ---------------------------------------------------------------------------
# TIGHT_INDOOR_SCREEN_SCENE
# ---------------------------------------------------------------------------


def test_tight_indoor_screen_scene_fires_without_depth_cue():
    raw = {
        "id": "fictional_naked_webcam_scene",
        "schema_version": 3,
        "scene_anchor": (
            "minimal home office, ring light on the subject, monitor "
            "glow, neutral palette"
        ),
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    leaks = [i for i in issues if i["code"] == "TIGHT_INDOOR_SCREEN_SCENE"]
    assert leaks, _codes(issues)
    assert leaks[0]["severity"] == "warning"
    assert leaks[0]["field"] == "scene_anchor"


def test_tight_indoor_screen_scene_silent_with_depth_cue():
    raw = {
        "id": "fictional_balanced_scene",
        "schema_version": 3,
        "scene_anchor": (
            "modern home office with floor-to-ceiling bookshelf behind, "
            "polished wooden floor, daylight from a tall window across "
            "the room"
        ),
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "TIGHT_INDOOR_SCREEN_SCENE" not in _codes(issues)


def test_tight_indoor_screen_scene_silent_without_screen_cue():
    # Cafe / outdoor scenes don't carry screen-facing cues at all;
    # the rule must not fire purely on the absence of depth keywords.
    raw = {
        "id": "fictional_cafe_scene",
        "schema_version": 3,
        "scene_anchor": "cozy cafe interior, warm key light, brick wall",
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "TIGHT_INDOOR_SCREEN_SCENE" not in _codes(issues)


def test_tight_indoor_screen_scene_skipped_for_studio_portrait():
    # Studio portrait styles legitimately use ring-light vocabulary
    # and are part of the anatomy-exempt whitelist.
    raw = {
        "id": "studio_elegant",
        "schema_version": 3,
        "scene_anchor": "ring light against a neutral seamless backdrop",
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "TIGHT_INDOOR_SCREEN_SCENE" not in _codes(issues)

"""Unit tests for the v1.66 style-lint rules.

Three new error / warning codes added in v1.66:

* ``EXPRESSION_PORTRAIT_LEAK`` (error) — ``expression`` carries
  studio-portrait phrasing on a non-exempt style.
* ``SCENE_POSE_LEAK`` (error) — scene fields carry implicit-pose
  fragments (``leather chair``, ``behind a desk``, …).
* ``WARDROBE_TIGHT_SUIT`` (warning) — tailored-suit clothing lacks
  the shoulder cue that prevents the over-narrow silhouette
  pathology.

Each rule has an exempt-whitelist of studio-portrait and document
styles where the banned phrasing is legitimate.
"""

from __future__ import annotations

from src.services.style_lint import lint_style


def _codes(issues) -> list[str]:
    return [i["code"] for i in issues]


def test_expression_portrait_leak_fires_on_career_style():
    raw = {
        "id": "fictional_boardroom",
        "schema_version": 3,
        "expression": (
            "Authoritative composed expression, steady leadership gaze, "
            "strong confident brow."
        ),
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    codes = _codes(issues)
    assert "EXPRESSION_PORTRAIT_LEAK" in codes
    leak_issue = next(i for i in issues if i["code"] == "EXPRESSION_PORTRAIT_LEAK")
    assert leak_issue["severity"] == "error"
    # The regex's non-overlapping ``finditer`` consumes ``steady
    # leadership`` first, so the bare ``leadership gaze`` token is not
    # reported separately. Either token is acceptable — they are both
    # part of the same portrait-pose cluster.
    leaked_tokens = leak_issue["detail"]["tokens"]
    assert "authoritative" in leaked_tokens
    assert any(
        "leadership" in tok for tok in leaked_tokens
    ), leaked_tokens


def test_expression_portrait_leak_skipped_for_studio_whitelist():
    raw = {
        "id": "formal_portrait",
        "schema_version": 3,
        "expression": (
            "Steady composed direct gaze, neutral professional expression, "
            "timeless authority."
        ),
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "EXPRESSION_PORTRAIT_LEAK" not in _codes(issues)


def test_expression_portrait_leak_skipped_for_document_styles():
    raw = {
        "id": "passport_rf",
        "schema_version": 3,
        "expression": "Authoritative composed expression for the sake of test.",
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "EXPRESSION_PORTRAIT_LEAK" not in _codes(issues)


def test_scene_pose_leak_catches_leather_chair():
    raw = {
        "id": "fictional_legal",
        "schema_version": 3,
        "scene_anchor": "warm wood-panelled office with a leather chair beside the desk",
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    pose_issues = [i for i in issues if i["code"] == "SCENE_POSE_LEAK"]
    assert pose_issues, _codes(issues)
    assert pose_issues[0]["severity"] == "error"
    assert "leather chair" in pose_issues[0]["detail"]["tokens"]


def test_scene_pose_leak_catches_webcam_friendly():
    raw = {
        "id": "fictional_video_call",
        "schema_version": 3,
        "base_scene": "clean home office with webcam-friendly framing, even lighting",
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "SCENE_POSE_LEAK" in _codes(issues)


def test_scene_pose_leak_allows_rembrandt_lighting_token():
    """``Rembrandt lighting`` is a legitimate cinematography term; only
    bare ``Rembrandt`` (implies a studio headshot setup) is flagged."""
    raw = {
        "id": "fictional_studio",
        "schema_version": 3,
        "scene_anchor": "neutral studio backdrop with classic Rembrandt lighting and gentle fill",
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "SCENE_POSE_LEAK" not in _codes(issues)


def test_scene_pose_leak_skipped_for_studio_whitelist():
    raw = {
        "id": "formal_portrait",
        "schema_version": 3,
        "scene_anchor": "neutral gradient studio backdrop with leather chair detail",
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "SCENE_POSE_LEAK" not in _codes(issues)


def test_wardrobe_tight_suit_warns_without_shoulder_cue():
    raw = {
        "id": "fictional_legal",
        "schema_version": 3,
        "default_clothing": "three-piece suit, silk tie, pocket square",
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    suit_issues = [i for i in issues if i["code"] == "WARDROBE_TIGHT_SUIT"]
    assert suit_issues
    assert suit_issues[0]["severity"] == "warning"


def test_wardrobe_tight_suit_quiet_when_shoulder_cue_present():
    raw = {
        "id": "fictional_legal",
        "schema_version": 3,
        "default_clothing": (
            "three-piece suit, silk tie, pocket square, "
            "well-fitted across the shoulders"
        ),
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "WARDROBE_TIGHT_SUIT" not in _codes(issues)


def test_wardrobe_tight_suit_only_one_warning_per_style():
    """A style may carry tailored-suit phrasing in multiple fields
    (default_clothing + clothing.default.{male,female,neutral}). The
    lint emits at most one ``WARDROBE_TIGHT_SUIT`` per style — the
    finding is "this style needs a shoulder cue", not "every field
    needs one"."""
    raw = {
        "id": "fictional_legal",
        "schema_version": 3,
        "default_clothing": "three-piece suit, silk tie",
        "clothing": {
            "default": {
                "male": "three-piece suit, silk tie",
                "female": "three-piece suit, silk tie",
                "neutral": "three-piece suit, silk tie",
            }
        },
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert _codes(issues).count("WARDROBE_TIGHT_SUIT") == 1


def test_wardrobe_tight_suit_skipped_for_studio_whitelist():
    raw = {
        "id": "formal_portrait",
        "schema_version": 3,
        "default_clothing": "dark formal suit, white shirt, conservative tie",
        "trigger_pool": ["dummy"],
    }
    issues = lint_style(raw)
    assert "WARDROBE_TIGHT_SUIT" not in _codes(issues)

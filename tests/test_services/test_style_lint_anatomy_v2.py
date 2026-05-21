"""v1.77 anatomy lint extensions — regression pins."""

from __future__ import annotations

from src.services.style_lint import lint_style


def test_trigger_selfie_fires_on_mirror_aesthetic_trigger_pool():
    issues = lint_style(
        {
            "id": "mirror_aesthetic",
            "schema_version": 3,
            "trigger_pool": [
                "mirror selfie composition with the reflection visible",
            ],
        }
    )
    codes = {i["code"] for i in issues}
    assert "TRIGGER_SELFIE" in codes


def test_expression_authority_fires():
    issues = lint_style(
        {
            "id": "analytics_review",
            "schema_version": 3,
            "expression": "Sharp analytical expression, intelligent authority.",
        }
    )
    assert any(i["code"] == "EXPRESSION_PORTRAIT_LEAK" for i in issues)


def test_wardrobe_collar_seam_leak_fires():
    issues = lint_style(
        {
            "id": "cafe",
            "schema_version": 3,
            "default_clothing": "shirt, collar and shoulder seam clearly visible",
        }
    )
    assert any(i["code"] == "WARDROBE_POSE_LEAK" for i in issues)


def test_lighting_pool_screen_leak_fires():
    issues = lint_style(
        {
            "id": "video_call",
            "schema_version": 3,
            "ambient": {"lighting": ["ring light", "soft key"]},
        }
    )
    assert any(i["code"] == "LIGHTING_POOL_SCREEN_LEAK" for i in issues)


def test_lighting_pool_pose_leak_fires():
    issues = lint_style(
        {
            "id": "legal_finance",
            "schema_version": 3,
            "allowed_variations": {
                "lighting": ["wood-paneled office with leather chair"],
            },
        }
    )
    assert any(i["code"] == "LIGHTING_POOL_POSE_LEAK" for i in issues)


def test_composed_focused_gaze_is_allowed():
    issues = lint_style(
        {
            "id": "shooting_range_pistol",
            "schema_version": 3,
            "expression": "Composed focused gaze, calm steady smile.",
        }
    )
    assert not any(i["code"] == "EXPRESSION_PORTRAIT_LEAK" for i in issues)


def test_studio_portrait_exempt_from_expression_leak():
    issues = lint_style(
        {
            "id": "formal_portrait",
            "schema_version": 3,
            "expression": "Steady composed direct gaze, timeless authority.",
        }
    )
    assert not any(i["code"] == "EXPRESSION_PORTRAIT_LEAK" for i in issues)

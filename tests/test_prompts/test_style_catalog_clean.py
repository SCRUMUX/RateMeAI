"""v1.66 — assert ``data/styles.json`` is clean of portrait-pose semantic leaks.

After the v1.66 ``Style Catalog Normalization`` migration ran across the
catalog the following invariants must hold on every non-studio,
non-document style:

* ``expression`` strings do NOT contain studio-portrait tokens like
  ``authoritative``, ``leadership gaze``, ``gravitas``,
  ``executive vision``, ``timeless authority``, ``commanding
  charismatic``, ``piercing``, ``composed gaze`` etc. — the
  semantic-conflict cluster identified by the v1.66 root-cause
  analysis. Edit models read these as "render this person as a
  tight studio portrait" and that competes with the v1.65 cinematic
  composition anchor.

* ``scene_anchor`` / ``base_scene`` / ``background.base`` do NOT
  contain implicit-pose tokens like ``behind a desk``,
  ``leather chair``, ``webcam-friendly framing`` — the catch-all
  cluster identified for scene-level pose leaks.

* ``default_clothing`` / ``clothing.default.{male,female,neutral}``
  strings that mention a tailored suit also mention the shoulder
  cue (``shoulders``, ``shoulder line``, ``well-fitted across the
  shoulders``) so edit models do not draw an over-narrow silhouette
  that exaggerates the head.

Studio-portrait (``formal_portrait`` / ``studio_elegant``) and
document styles are explicitly exempt — those genres legitimately
carry portrait-pose phrasing.

This test runs against the live ``data/styles.json`` so it fails
loudly if a future admin edit re-introduces any of the banned tokens.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.services.style_lint import (
    _EXPRESSION_PORTRAIT_LEAK_RE,
    _LINT_ANATOMY_EXEMPT,
    _SCENE_POSE_LEAK_RE,
    _WARDROBE_SHOULDER_CUE_PATTERN,
    _WARDROBE_SUIT_PATTERN,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"


def _load_styles() -> list[dict]:
    return json.loads(STYLES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", _load_styles(), ids=lambda e: e.get("id", "?"))
def test_expression_has_no_portrait_pose_leak(entry):
    """Non-studio styles must not carry studio-portrait expressions."""
    sid = entry.get("id", "")
    if sid in _LINT_ANATOMY_EXEMPT:
        pytest.skip(f"{sid}: exempt (studio-portrait / document)")
    expression = entry.get("expression", "")
    if not isinstance(expression, str) or not expression:
        return
    match = _EXPRESSION_PORTRAIT_LEAK_RE.search(expression)
    assert match is None, (
        f"{sid}: expression {expression!r} still contains "
        f"portrait-pose token {match.group(0)!r} after v1.66 "
        "migration. Re-run scripts/migrations/2026_05_styles_v4_anatomy/"
        "migrate.py or add to the studio-portrait whitelist."
    )


@pytest.mark.parametrize("entry", _load_styles(), ids=lambda e: e.get("id", "?"))
def test_scene_has_no_pose_leak(entry):
    """Non-studio styles must not encode an implicit pose in scene fields."""
    sid = entry.get("id", "")
    if sid in _LINT_ANATOMY_EXEMPT:
        pytest.skip(f"{sid}: exempt")
    candidates: list[tuple[str, str]] = []
    for field in ("scene_anchor", "base_scene"):
        value = entry.get(field)
        if isinstance(value, str) and value:
            candidates.append((field, value))
    bg = entry.get("background")
    if isinstance(bg, dict):
        bg_base = bg.get("base")
        if isinstance(bg_base, str) and bg_base:
            candidates.append(("background.base", bg_base))
    for field, value in candidates:
        match = _SCENE_POSE_LEAK_RE.search(value)
        assert match is None, (
            f"{sid}: {field} {value!r} still contains pose-leak token "
            f"{match.group(0)!r}. Re-run the migration or rewrite the "
            "scene to describe the SPACE only."
        )


@pytest.mark.parametrize("entry", _load_styles(), ids=lambda e: e.get("id", "?"))
def test_tailored_suit_has_shoulder_cue(entry):
    """Tailored suits in non-studio styles must carry a shoulder cue."""
    sid = entry.get("id", "")
    if sid in _LINT_ANATOMY_EXEMPT:
        pytest.skip(f"{sid}: exempt")
    candidates: list[tuple[str, str]] = []
    default_clothing = entry.get("default_clothing")
    if isinstance(default_clothing, str) and default_clothing:
        candidates.append(("default_clothing", default_clothing))
    clothing_block = entry.get("clothing")
    if isinstance(clothing_block, dict):
        default_block = clothing_block.get("default")
        if isinstance(default_block, dict):
            for gender_key in ("male", "female", "neutral"):
                value = default_block.get(gender_key)
                if isinstance(value, str) and value:
                    candidates.append(
                        (f"clothing.default.{gender_key}", value)
                    )
    for field, value in candidates:
        if not _WARDROBE_SUIT_PATTERN.search(value):
            continue
        assert _WARDROBE_SHOULDER_CUE_PATTERN.search(value), (
            f"{sid}: {field} {value!r} mentions a tailored suit but "
            "no shoulder cue. Add ``, well-fitted across the shoulders``"
            " (the migration script does this automatically)."
        )


def test_migration_marker_styles_were_normalised():
    """Sanity check on canonical examples: ``legal_finance`` and
    ``boardroom`` are the two motivating cases from the v1.66
    root-cause analysis. Pin the post-migration form so a partial
    rollback is immediately obvious."""
    styles = {entry["id"]: entry for entry in _load_styles() if "id" in entry}

    legal = styles.get("legal_finance")
    assert legal is not None, "legal_finance disappeared from the catalog"
    assert "gravitas" not in legal.get("expression", "").lower()
    assert "leather chair" not in legal.get("scene_anchor", "").lower()
    assert re.search(
        r"well-fitted across the shoulders",
        legal.get("default_clothing", ""),
        re.IGNORECASE,
    )

    boardroom = styles.get("boardroom")
    assert boardroom is not None, "boardroom disappeared from the catalog"
    assert "leadership gaze" not in boardroom.get("expression", "").lower()
    assert "leather chair" not in boardroom.get("scene_anchor", "").lower()

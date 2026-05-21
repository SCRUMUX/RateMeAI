"""v1.68 P3.12 — golden wire-prompt snapshots.

Locks the EXACT final wire prompt for a curated matrix of styles so
ANY future pipeline change that alters the prompt (slot ordering,
constant wording, default flag values, …) breaks the test and forces
the author to acknowledge the diff in code review.

Matrix
------
* 30 style keys spread across the three photo modes
  (``cv`` / ``dating`` / ``social``).
* Single framing (``portrait``) — exercises the most attention-heavy
  layout and keeps the fixture set tractable.
* Single gender (``male``).
* Deterministic ``seed=42`` so the slot sampler always rolls the same
  scene / lighting / weather pool entries.
* Target model ``gpt_image_2`` (the production default).

Fixture files live at ``tests/fixtures/golden_prompts/<mode>__<style>.txt``.
They are checked into the repo so the test runs hermetically on CI.

Regenerating goldens
--------------------
When a legitimate refactor changes the wire prompt the goldens must
be regenerated. Two ways:

* Set the env var when running pytest::

    RATEMEAI_UPDATE_GOLDEN_PROMPTS=1 pytest tests/test_prompts/test_golden_wire_prompts.py

  This OVERWRITES every fixture with the freshly-generated prompt.

* Delete the offending fixture file. The test auto-creates missing
  fixtures on its first observation; the next run will then assert
  against them.

Either way, the diff against ``main`` is what reviewers actually
inspect — that is the entire point of the snapshot.

Stability
---------
The fixtures are stable as long as:

* Style data in ``data/styles.json`` for the listed keys is
  unchanged (the migration in
  ``scripts/migrations/2026_06_styles_cleanup/`` is one-shot — the
  doubled-word fix is permanent).
* The remaining v1.68 feature flags
  (``pose_hint_enabled``, ``studio_portrait_whitelist_v2``) stay at
  ``True``. v1.69 (May 2026) flipped them on by default after the
  staged rollout proved the prompt-level audit fixes never reached
  production via the staging env-override path. (v1.70 already
  retired ``numerical_percent_anchor_enabled`` and
  ``photoreal_by_framing_enabled``; v1.71 retired
  ``light_match_clause_enabled``.)
* ``csl_padding_v2_enabled`` (which only affects the padder, not the
  prompt) stays ``True``.
* The trigger/scene fuzzy-overlap guard in
  ``composition_builder._ensure_trigger_in_scene`` (v1.69) stays
  active — it removes the duplicate ``scene_anchor`` echo in the
  early-attention slot for studio styles
  (corporate / boardroom / video_call / …).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.models.enums import AnalysisMode
from src.prompts.engine import PromptEngine
from src.prompts.image_gen import STYLE_REGISTRY
from src.services.style_loader_v2 import register_v2_styles_from_json
from src.services.style_loader_v3 import register_v3_styles_from_json


_FIXTURE_DIR = (
    Path(__file__).resolve().parents[1] / "fixtures" / "golden_prompts"
)
_UPDATE_ENV = "RATEMEAI_UPDATE_GOLDEN_PROMPTS"


@pytest.fixture(scope="module", autouse=True)
def _register_all_styles():
    snapshot_v2 = dict(STYLE_REGISTRY._v2_by_key)
    snapshot_v3 = dict(STYLE_REGISTRY._v3_by_key)
    snapshot_promoted = set(STYLE_REGISTRY._v3_promoted)

    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v3_promoted.clear()

    register_v2_styles_from_json()
    register_v3_styles_from_json()
    yield

    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v2_by_key.update(snapshot_v2)
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v3_by_key.update(snapshot_v3)
    STYLE_REGISTRY._v3_promoted.clear()
    STYLE_REGISTRY._v3_promoted.update(snapshot_promoted)


# Curated 30-style matrix. Picks 10 styles per mode that exercise the
# main genre clusters: career-studio (cv), travel-landmark (dating),
# lifestyle (social). Style keys must be stable across the schema —
# we add new keys to the dict, never rename existing ones, so the
# fixture file names stay valid across catalog re-curations.
_MATRIX: list[tuple[AnalysisMode, str]] = [
    # CV — career and studio portrait styles
    (AnalysisMode.CV, "corporate"),
    (AnalysisMode.CV, "boardroom"),
    (AnalysisMode.CV, "formal_portrait"),
    (AnalysisMode.CV, "startup_casual"),
    (AnalysisMode.CV, "coworking"),
    (AnalysisMode.CV, "video_call"),
    (AnalysisMode.CV, "analytics_review"),
    (AnalysisMode.CV, "notebook_ideas"),
    (AnalysisMode.CV, "tablet_stylus"),
    (AnalysisMode.CV, "coffee_break_work"),
    # Dating — travel/landmark styles
    (AnalysisMode.DATING, "paris_eiffel"),
    (AnalysisMode.DATING, "dubai_burj_khalifa"),
    (AnalysisMode.DATING, "nyc_brooklyn_bridge"),
    (AnalysisMode.DATING, "rome_colosseum"),
    (AnalysisMode.DATING, "venice_san_marco"),
    (AnalysisMode.DATING, "barcelona_sagrada"),
    (AnalysisMode.DATING, "london_eye"),
    (AnalysisMode.DATING, "tokyo_tower"),
    (AnalysisMode.DATING, "singapore_marina_bay"),
    (AnalysisMode.DATING, "sf_golden_gate"),
    # Social — lifestyle styles
    (AnalysisMode.SOCIAL, "mirror_aesthetic"),
    (AnalysisMode.SOCIAL, "elevator_clean"),
    (AnalysisMode.SOCIAL, "candid_street"),
    (AnalysisMode.SOCIAL, "shopfront"),
    (AnalysisMode.SOCIAL, "focused_mood"),
    (AnalysisMode.SOCIAL, "influencer_urban"),
    (AnalysisMode.SOCIAL, "influencer_minimal"),
    (AnalysisMode.SOCIAL, "golden_hour"),
    (AnalysisMode.SOCIAL, "neon_night"),
    (AnalysisMode.SOCIAL, "reading_home"),
]


def _fixture_path(mode: AnalysisMode, style: str) -> Path:
    return _FIXTURE_DIR / f"{mode.value}__{style}.txt"


def _generate_prompt(mode: AnalysisMode, style: str) -> str:
    return PromptEngine().build_image_prompt_v2(
        mode,
        style=style,
        gender="male",
        framing="portrait",
        target_model="gpt_image_2",
        seed=42,
    ) or ""


@pytest.mark.parametrize(
    ("mode", "style"),
    _MATRIX,
    ids=[f"{m.value}__{s}" for m, s in _MATRIX],
)
def test_wire_prompt_matches_golden(mode: AnalysisMode, style: str):
    """Assert the live wire prompt matches the stored golden fixture.

    When the env var ``RATEMEAI_UPDATE_GOLDEN_PROMPTS=1`` is set,
    OR the fixture file does not yet exist, the prompt is written
    to the fixture and the assertion is skipped — that is the
    "seed the catalog" path used both at first installation and
    after a deliberate refactor.
    """
    actual = _generate_prompt(mode, style)
    fixture = _fixture_path(mode, style)
    update = os.environ.get(_UPDATE_ENV) == "1"

    if update or not fixture.exists():
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(actual, encoding="utf-8")
        if update:
            pytest.skip(
                f"Updated golden fixture {fixture.name} "
                "(RATEMEAI_UPDATE_GOLDEN_PROMPTS=1)."
            )
        else:
            pytest.skip(
                f"Seeded golden fixture {fixture.name} "
                "on first observation; re-run pytest to assert."
            )

    expected = fixture.read_text(encoding="utf-8")
    assert actual == expected, (
        f"Wire prompt for ({mode.value}, {style}) drifted from "
        f"golden fixture {fixture.name}.\n"
        f"Set {_UPDATE_ENV}=1 to regenerate the fixture if the "
        "diff is intentional.\n"
        f"Expected:\n{expected!r}\nActual:\n{actual!r}"
    )

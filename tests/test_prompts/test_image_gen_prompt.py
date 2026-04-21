"""Snapshot-style tests for the refactored image-generation prompt builder.

These tests do not assert exact byte strings (which would be brittle across
prompt tweaks) — they assert the structural invariants introduced by the
"single-call-quality-hardening" plan:

  - sectioned [CHANGE] / [PRESERVE] / [QUALITY] layout
  - HAIR_ANCHOR and COMPOSITION_ANCHOR always present in PRESERVE
  - BACKGROUND_FOCUS no longer used (conflict with shallow-DoF styles)
  - conditional injections are triggered by input quality hints
  - depth_of_field drives the QUALITY block
"""
from __future__ import annotations

from src.prompts import image_gen as ig
from src.prompts.style_spec import StyleSpec, detect_depth_of_field


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------


def test_prompt_has_three_sections():
    p = ig.build_dating_prompt(style="warm_outdoor", gender="male")
    assert "[CHANGE]" in p
    assert "[PRESERVE]" in p
    assert "[QUALITY]" in p
    # Order must be CHANGE -> PRESERVE -> QUALITY
    assert p.index("[CHANGE]") < p.index("[PRESERVE]") < p.index("[QUALITY]")


def test_prompt_contains_hair_and_composition_anchors():
    p = ig.build_dating_prompt(style="warm_outdoor", gender="male")
    assert "HAIR:" in p
    assert "COMPOSITION:" in p


def test_background_focus_anchor_is_retired():
    """The old 'BACKGROUND FOCUS' blanket anchor must be gone — it conflicted
    with styles that explicitly want shallow DoF / bokeh."""
    p = ig.build_dating_prompt(style="rooftop_city", gender="male")
    assert "BACKGROUND FOCUS" not in p


def test_all_modes_build_without_error():
    for builder in (
        ig.build_dating_prompt,
        ig.build_cv_prompt,
        ig.build_social_prompt,
    ):
        p = builder(style="", gender="male")
        assert "[CHANGE]" in p


def test_document_style_still_builds():
    p = ig.build_cv_prompt(style="passport_rf", gender="female")
    assert "[PRESERVE]" in p
    # ID-style headshot must mention the neutral backdrop requirement.
    assert "neutral" in p.lower()


# ---------------------------------------------------------------------------
# Conditional injections from input quality hints
# ---------------------------------------------------------------------------


def test_small_face_hint_injects_small_face_protection():
    hints = {"face_area_ratio": 0.06, "yaw": 0, "hair_bg_contrast": 0.5}
    p = ig.build_dating_prompt(
        style="warm_outdoor", gender="male", input_hints=hints,
    )
    assert ig.SMALL_FACE_PROTECTION in p


def test_low_hair_contrast_injects_strong_hair_anchor():
    hints = {"face_area_ratio": 0.4, "yaw": 0, "hair_bg_contrast": 0.02}
    p = ig.build_dating_prompt(
        style="warm_outdoor", gender="male", input_hints=hints,
    )
    assert ig.HAIR_BG_STRONG in p


def test_non_frontal_injects_hint():
    hints = {"face_area_ratio": 0.4, "yaw": 35.0, "hair_bg_contrast": 0.5}
    p = ig.build_social_prompt(
        style="", gender="male", input_hints=hints,
    )
    assert ig.NON_FRONTAL_HINT in p


def test_clean_hints_injects_nothing_extra():
    hints = {"face_area_ratio": 0.25, "yaw": 0, "hair_bg_contrast": 0.4}
    p = ig.build_dating_prompt(
        style="warm_outdoor", gender="male", input_hints=hints,
    )
    assert ig.SMALL_FACE_PROTECTION not in p
    assert ig.NON_FRONTAL_HINT not in p


# ---------------------------------------------------------------------------
# depth_of_field
# ---------------------------------------------------------------------------


def test_detect_depth_of_field_keywords():
    assert detect_depth_of_field("blurred city lights at night") == "shallow"
    assert detect_depth_of_field("softly blurred park at golden hour") == "shallow"
    assert detect_depth_of_field("clean studio with gradient backdrop") == "deep"


def test_depth_of_field_prompt_variants():
    deep = StyleSpec(
        key="x", mode="dating",
        background="bg", clothing_male="c", clothing_female="c",
        lighting="l", expression="e",
        depth_of_field="deep",
    )
    shallow = StyleSpec(
        key="y", mode="dating",
        background="bg", clothing_male="c", clothing_female="c",
        lighting="l", expression="e",
        depth_of_field="shallow",
    )
    deep_prompt = deep.depth_of_field_prompt()
    shallow_prompt = shallow.depth_of_field_prompt()
    assert "deep natural focus" in deep_prompt
    assert "fully resolved" in deep_prompt
    for token in ("bokeh", "defocus", "blur"):
        assert token not in deep_prompt
        assert token not in shallow_prompt
    assert "mid-aperture" in shallow_prompt


# ---------------------------------------------------------------------------
# Blur hygiene and hand anatomy anchors
# ---------------------------------------------------------------------------


_BLUR_WORDS = ("bokeh", "blurred", "softly blurred", "out of focus", "defocused")


def test_no_bokeh_words_in_default_builds():
    """The [CHANGE] block of every style must not positively request blur.

    After the positive-framing rewrite the [QUALITY] block also no longer
    contains any blur/bokeh/defocus tokens (see
    test_no_blur_tokens_anywhere_in_prompt), but this guard specifically
    pins down the style-driven [CHANGE] section.
    """
    checks = (
        (ig.build_dating_prompt, ig.DATING_STYLES),
        (ig.build_cv_prompt, ig.CV_STYLES),
        (ig.build_social_prompt, ig.SOCIAL_STYLES),
    )
    for builder, styles in checks:
        for style_key in styles:
            p = builder(style=style_key, gender="male")
            change_block = p.split("[CHANGE]", 1)[1].split("[PRESERVE]", 1)[0].lower()
            for word in _BLUR_WORDS:
                assert word not in change_block, (
                    f"{style_key}: leaked blur word {word!r} in [CHANGE]"
                )


def test_hands_anchor_present_in_preserve():
    for builder in (
        ig.build_dating_prompt,
        ig.build_cv_prompt,
        ig.build_social_prompt,
    ):
        p = builder(style="", gender="male")
        assert "HANDS:" in p
        preserve = p.split("[PRESERVE]", 1)[1].split("[QUALITY]", 1)[0]
        assert "HANDS:" in preserve


def test_hands_anchor_in_step_templates():
    for step in ("background_edit", "clothing_edit"):
        p = ig.build_step_prompt(step, style="warm_outdoor", mode="dating")
        assert "HANDS:" in p


# ---------------------------------------------------------------------------
# Phase 1 hygiene: silhouette lighting, bare torso, FACE_ANCHOR flexibility
# ---------------------------------------------------------------------------


import re  # noqa: E402


_SILHOUETTE_RE = re.compile(r"silhouette\s+(rim|against)", re.IGNORECASE)


def test_no_silhouette_light_in_change():
    """No style should describe the subject as a backlit silhouette in the
    CHANGE block — that patterns blackens the face and kills identity.
    """
    checks = (
        (ig.build_dating_prompt, ig.DATING_STYLES),
        (ig.build_cv_prompt, ig.CV_STYLES),
        (ig.build_social_prompt, ig.SOCIAL_STYLES),
    )
    for builder, styles in checks:
        for style_key in styles:
            p = builder(style=style_key, gender="male")
            change_block = p.split("[CHANGE]", 1)[1].split("[PRESERVE]", 1)[0]
            assert not _SILHOUETTE_RE.search(change_block), (
                f"{style_key}: silhouette light pattern leaked in [CHANGE]"
            )


def test_no_bare_torso_in_change():
    checks = (
        (ig.build_dating_prompt, ig.DATING_STYLES),
        (ig.build_cv_prompt, ig.CV_STYLES),
        (ig.build_social_prompt, ig.SOCIAL_STYLES),
    )
    for builder, styles in checks:
        for style_key in styles:
            for gender in ("male", "female"):
                p = builder(style=style_key, gender=gender)
                change_block = p.split("[CHANGE]", 1)[1].split("[PRESERVE]", 1)[0]
                assert "bare torso" not in change_block.lower(), (
                    f"{style_key}/{gender}: 'bare torso' leaked in [CHANGE]"
                )


def test_face_anchor_allows_expression_change():
    """FACE_ANCHOR must not freeze the mouth expression — personality-driven
    styles need to adapt smile/laugh while keeping identity."""
    assert "exactly as-is" not in ig.FACE_ANCHOR
    assert (
        "may adapt" in ig.FACE_ANCHOR
        or "natural lip shape" in ig.FACE_ANCHOR
    )


# ---------------------------------------------------------------------------
# Phase 2: low-key sharpness + shallow-DoF regression + doc composition
# ---------------------------------------------------------------------------


def test_no_style_triggers_shallow_dof():
    """No style background in the registry should ship with shallow-DoF keywords.

    If someone later writes 'softly blurred' or 'bokeh' into a style,
    detect_depth_of_field() will flip it to shallow and the [QUALITY]
    block will flip to bokeh wording — which contradicts the deep-DoF
    guarantee we added to CAMERA. Catch that at CI.
    """
    from src.prompts.style_spec import _SHALLOW_DOF_KEYWORDS

    for mode in ("dating", "cv", "social"):
        for spec in ig.STYLE_REGISTRY.all_for_mode(mode):
            low = spec.background.lower()
            for kw in _SHALLOW_DOF_KEYWORDS:
                assert kw not in low, (
                    f"{mode}/{spec.key}: shallow-DoF keyword {kw!r} "
                    f"leaked into style background"
                )


_BUILDERS_BY_MODE = {
    "dating": ig.build_dating_prompt,
    "cv": ig.build_cv_prompt,
    "social": ig.build_social_prompt,
}


def test_low_key_styles_get_sharpness_anchor():
    """Every style in _LOW_KEY_STYLES must receive LOW_KEY_SHARPNESS in PRESERVE.

    This covers the original 8 styles plus the expanded set of dim/amber/
    tungsten-lit styles across dating, cv, and social.
    """
    for mode, style_key in ig._LOW_KEY_STYLES:
        builder = _BUILDERS_BY_MODE[mode]
        p = builder(style=style_key, gender="male")
        preserve = p.split("[PRESERVE]", 1)[1].split("[QUALITY]", 1)[0]
        assert "SCENE FOCUS" in preserve, (
            f"{mode}/{style_key}: LOW_KEY_SHARPNESS missing in [PRESERVE]"
        )


def test_low_key_styles_cover_expanded_set():
    """Regression guard: the expanded low-key list must still contain the
    dim/lamp/amber styles we identified in the follow-up audit."""
    required = {
        ("dating", "cafe"),
        ("dating", "coffee_date"),
        ("dating", "airplane_window"),
        ("dating", "evening_home"),
        ("dating", "travel_luxury"),
        ("dating", "rooftop_city"),
        ("dating", "dubai_burj_khalifa"),
        ("dating", "singapore_marina_bay"),
        ("dating", "nyc_times_square"),
        ("cv", "late_hustle"),
        ("cv", "quiet_expert"),
        ("cv", "intellectual"),
        ("cv", "creative_director"),
        ("cv", "speaker_stage"),
        ("cv", "decision_moment"),
        ("cv", "man_with_mission"),
        ("social", "luxury"),
        ("social", "evening_planning"),
        ("social", "after_work"),
        ("social", "panoramic_window"),
    }
    missing = required - set(ig._LOW_KEY_STYLES)
    assert not missing, f"Low-key styles regressed: {missing}"


def test_non_low_key_style_has_no_sharpness_anchor():
    p = ig.build_dating_prompt(style="warm_outdoor", gender="male")
    assert "SCENE FOCUS" not in p


def test_document_styles_skip_rigid_composition():
    """Document styles must use DOC_COMPOSITION_ANCHOR, not the rigid
    'Do not re-pose' anchor — otherwise we block the model from actually
    centering the head to the document format it just described.
    """
    for style_key in (
        "passport_rf", "visa_us", "photo_3x4",
        "doc_passport_neutral", "doc_visa_compliant", "doc_resume_headshot",
    ):
        p = ig.build_cv_prompt(style=style_key, gender="male")
        assert "Do not re-pose" not in p, (
            f"{style_key}: rigid composition anchor leaked into document style"
        )
        assert "center the head and shoulders" in p.lower()


def test_non_document_cv_style_keeps_rigid_composition():
    p = ig.build_cv_prompt(style="corporate", gender="male")
    assert "Do not re-pose" in p


# ---------------------------------------------------------------------------
# Phase 5: NATURAL_MOUTH anchor — guards realism after FACE_ANCHOR relaxation
# ---------------------------------------------------------------------------


def test_natural_mouth_anchor_present_in_preserve():
    """NATURAL_MOUTH must appear in [PRESERVE] for every mode — it is the
    photorealism safety net that complements the relaxed FACE_ANCHOR.
    """
    for builder in (
        ig.build_dating_prompt,
        ig.build_cv_prompt,
        ig.build_social_prompt,
    ):
        p = builder(style="", gender="male")
        preserve = p.split("[PRESERVE]", 1)[1].split("[QUALITY]", 1)[0]
        assert "MOUTH:" in preserve
        assert "plastic smile" in preserve


def test_natural_mouth_anchor_works_for_documents_too():
    """Even for rigid document styles, NATURAL_MOUTH must stay in PRESERVE
    so that passport/visa photos don't look mannequin-like.
    """
    p = ig.build_cv_prompt(style="passport_rf", gender="female")
    preserve = p.split("[PRESERVE]", 1)[1].split("[QUALITY]", 1)[0]
    assert "MOUTH:" in preserve


# ---------------------------------------------------------------------------
# Phase 6: sport-style deep focus + complex hand pose anchors
# ---------------------------------------------------------------------------


def test_sport_styles_get_deep_focus_and_complex_hands():
    """Athletic styles receive SPORT_DEEP_FOCUS and HANDS_COMPLEX_POSE in
    [PRESERVE] to counter the bokeh bias of sport photography and protect
    fingers in complex poses (fists, grips, overlapping hands).
    """
    for mode, style_key in ig._SPORT_STYLES:
        builder = _BUILDERS_BY_MODE[mode]
        p = builder(style=style_key, gender="male")
        preserve = p.split("[PRESERVE]", 1)[1].split("[QUALITY]", 1)[0]
        assert "athletic setting" in preserve, (
            f"{mode}/{style_key}: SPORT_DEEP_FOCUS missing"
        )
        assert "HANDS DETAIL" in preserve, (
            f"{mode}/{style_key}: HANDS_COMPLEX_POSE missing"
        )


def test_sport_styles_cover_expected_set():
    """Regression guard: all gym/running/yoga/cycling/tennis/swim/hike styles
    must remain in _SPORT_STYLES."""
    required = {
        ("dating", "gym_fitness"),
        ("dating", "running"),
        ("dating", "tennis"),
        ("dating", "swimming_pool"),
        ("dating", "hiking"),
        ("dating", "yoga_outdoor"),
        ("dating", "cycling"),
        ("social", "fitness_lifestyle"),
        ("social", "yoga_social"),
        ("social", "cycling_social"),
    }
    missing = required - set(ig._SPORT_STYLES)
    assert not missing, f"Sport styles regressed: {missing}"


def test_non_sport_style_has_no_sport_anchors():
    p = ig.build_dating_prompt(style="restaurant", gender="male")
    assert "athletic setting" not in p
    assert "HANDS DETAIL" not in p


def test_gym_fitness_gets_full_sharp_background_stack():
    """The user's reported failure case: gym_fitness must end up with every
    anti-bokeh and anti-finger-merge anchor we have.
    """
    p = ig.build_dating_prompt(style="gym_fitness", gender="male")
    preserve = p.split("[PRESERVE]", 1)[1].split("[QUALITY]", 1)[0]
    quality = p.split("[QUALITY]", 1)[1]

    assert "athletic setting" in preserve
    assert "HANDS DETAIL" in preserve
    assert "HANDS:" in preserve
    assert "legible and clearly resolved" in quality
    assert "fully resolved" in quality
    for token in ("blur", "bokeh", "defocus"):
        assert token not in quality.lower(), (
            f"gym_fitness QUALITY block leaked blur-family token {token!r}"
        )


# ---------------------------------------------------------------------------
# Phase 7: positive-framing guard + distant-softness anchor
# ---------------------------------------------------------------------------


_NO_SYNDROME_TOKENS = ("blur", "bokeh", "defocus")


def test_no_blur_tokens_anywhere_in_prompt():
    """After the positive-framing rewrite, no prompt block (CHANGE, PRESERVE,
    QUALITY) should contain the tokens blur/bokeh/defocus for any style.

    Diffusion models tend to latch onto these as positive tokens even when
    they are embedded in "no X" phrases — so the whole pipeline now avoids
    them entirely.
    """
    checks = (
        (ig.build_dating_prompt, ig.DATING_STYLES),
        (ig.build_cv_prompt, ig.CV_STYLES),
        (ig.build_social_prompt, ig.SOCIAL_STYLES),
    )
    for builder, styles in checks:
        for style_key in styles:
            p = builder(style=style_key, gender="male").lower()
            for token in _NO_SYNDROME_TOKENS:
                assert token not in p, (
                    f"{style_key}: leaked blur-family token {token!r} in prompt"
                )


def test_distant_softness_styles_get_anchor():
    """Every style in _DISTANT_SOFTNESS_STYLES must receive the new
    DISTANT_ATMOSPHERE_OK anchor in [PRESERVE]."""
    for mode, style_key in ig._DISTANT_SOFTNESS_STYLES:
        builder = _BUILDERS_BY_MODE[mode]
        p = builder(style=style_key, gender="male")
        preserve = p.split("[PRESERVE]", 1)[1].split("[QUALITY]", 1)[0]
        assert "ATMOSPHERE:" in preserve, (
            f"{mode}/{style_key}: DISTANT_ATMOSPHERE_OK missing in [PRESERVE]"
        )


def test_non_distant_softness_style_has_no_atmosphere_anchor():
    p = ig.build_dating_prompt(style="warm_outdoor", gender="male")
    assert "ATMOSPHERE:" not in p

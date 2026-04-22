"""Phase 4 hygiene tests — registry validator, female-clothing edge cases,
document style compactness, and NSFW brace escaping.
"""
from __future__ import annotations

from src.prompts import image_gen as ig
from src.prompts import rating, dating, social, cv
from src.prompts.style_spec import adapt_female_clothing


# ---------------------------------------------------------------------------
# Registry-level validation
# ---------------------------------------------------------------------------


def test_validate_all_returns_no_warnings():
    """Hard-fails if any style still carries negative framing.

    After the 1.14.3 positive-framing refresh the validator whitelist was
    reduced to the empty set, so any ``no X`` / ``without X`` / ``avoid X``
    / ``don't X`` fragment in a style's background / clothing / lighting
    now surfaces here.

    Since 1.15.0 the same hygiene discipline is extended to every
    ``StyleVariant`` (scene / lighting / props / camera / clothing accent),
    so a sloppy variant addition will also fail this test.
    """
    warnings = ig.STYLE_REGISTRY.validate_all()
    assert warnings == [], (
        "Style registry emitted quality warnings:\n"
        + "\n".join(warnings)
    )


def test_validator_flags_negative_phrases_in_variants():
    """Meta-check: the validator must surface banned negative framing
    when it appears inside a variant field.
    """
    from src.prompts.style_spec import StyleSpec, StyleVariant, validate_style

    bad_spec = StyleSpec(
        key="test_bad_variant",
        mode="dating",
        background="sunlit garden",
        clothing_male="smart casual shirt",
        clothing_female="elegant summer dress",
        lighting="soft daylight",
        expression="calm, confident",
        variants=(
            StyleVariant(
                id="bad",
                scene="park bench",
                lighting="no plastic smile, warm afternoon light",
            ),
        ),
    )
    warnings = validate_style(bad_spec)
    assert any("variants[bad]" in w for w in warnings), (
        "Validator must flag disallowed negative framing inside variants; "
        f"got warnings: {warnings}"
    )


# ---------------------------------------------------------------------------
# adapt_female_clothing edge cases
# ---------------------------------------------------------------------------


def test_adapt_female_clothing_subtle_tie_or_scarf():
    """Input like 'subtle tie or silk scarf' must not produce the ugly
    'statement necklace or silk scarf' collision."""
    male = "tailored formal charcoal suit, crisp white shirt, subtle tie or silk scarf."
    female = adapt_female_clothing(male)
    assert "necklace or silk scarf" in female or "delicate necklace" in female
    # Specifically: no 'statement necklace or silk scarf' — that's the regression.
    assert "statement necklace or silk scarf" not in female


def test_adapt_female_clothing_power_tie_intact():
    male = "navy suit, power tie, pocket square, cufflinks."
    female = adapt_female_clothing(male)
    assert "statement necklace" in female
    assert "delicate bracelet" in female


def test_adapt_female_clothing_conservative_tie():
    male = "dark formal suit, white shirt, conservative tie, clean grooming."
    female = adapt_female_clothing(male)
    assert "elegant silk scarf" in female
    assert "conservative tie" not in female


def test_adapt_female_clothing_no_bare_torso_input():
    male = "fitted swim trunks, athletic build, optional sunglasses in hand."
    female = adapt_female_clothing(male)
    assert "bare torso" not in female
    assert "swimsuit" in female


# ---------------------------------------------------------------------------
# Document styles: no 'or' options in background/clothing
# ---------------------------------------------------------------------------


def test_document_styles_no_or():
    for key in ig._DOCUMENT_STYLE_KEYS:
        spec = ig.STYLE_REGISTRY.get("cv", key)
        if spec is None:
            continue
        combined = f"{spec.background} {spec.clothing_male} {spec.clothing_female}"
        assert " or " not in combined, (
            f"{key}: document style still offers an 'or' option: {combined}"
        )


# ---------------------------------------------------------------------------
# edit_compatible removed
# ---------------------------------------------------------------------------


def test_no_edit_compatible_false_overrides():
    for (mode, key), override in ig._STYLE_OVERRIDES.items():
        assert override.get("edit_compatible", True) is True, (
            f"{mode}/{key}: edit_compatible=False fallback is no longer supported"
        )


# ---------------------------------------------------------------------------
# NSFW prefix braces
# ---------------------------------------------------------------------------


def test_nsfw_prefix_has_no_doubled_braces_in_analysis_prompts():
    """Any prompt consumer of NSFW_INLINE_PREFIX must end up with plain
    '{' and '}' rather than the previous '{{' / '}}' escape sequences.
    """
    prompts = {
        "rating": rating.build_prompt({}),
        "dating": dating.build_prompt({}),
        "social": social.build_prompt({}),
        "cv": cv.build_prompt({"profession": "IT"}),
    }
    for name, p in prompts.items():
        assert "{{" not in p, f"{name}: literal '{{{{' leaked into prompt"
        assert "}}" not in p, f"{name}: literal '}}}}' leaked into prompt"

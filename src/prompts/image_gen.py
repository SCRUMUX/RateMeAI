"""Centralized image-generation prompt builder for all modes.

Compact photorealistic template (v1.13, retained through v1.20): a
single natural paragraph in the 800–1200 character budget. Empirically
FAL's edit endpoints (Kontext, FLUX.2 Pro Edit, Seedream, PuLID) all
degrade when handed tag-sectioned layouts ([CHANGE]/[PRESERVE]/
[QUALITY]) or prompts above ~1200 characters. Two short anchors —
PRESERVE_PHOTO and QUALITY_PHOTO — cover the semantics that previously
required 10+ individual constants.
"""

from __future__ import annotations

import logging

from src.prompts.style_spec import (
    OutputAspect,
    StyleRegistry,
    StyleSpec,
    StyleVariant,
)

logger = logging.getLogger(__name__)

# Hard cap — worker logs a warning and truncates anything above this
# before handing off to the image-gen provider. Matches the test budget
# in tests/test_prompts/test_prompt_length_budget.py.
# For GPT-2 we now allow longer prompts, this cap is primarily for legacy models.
PROMPT_MAX_LEN = 2500


# ---------------------------------------------------------------------------
# Output size resolver — aspect preset → concrete {width, height} for FAL.
# ---------------------------------------------------------------------------

# Pixel sizes per aspect. Every non-square bucket is ≈2 MP (dimensions are
# multiples of 16 for stable FLUX.2 Pro Edit inference); ``square_hd`` is
# the 1 MP document bucket. The FLUX.2 API accepts these verbatim as a
# ``{"width": W, "height": H}`` object — passing the custom shape instead
# of the preset enum gives us the exact pixel count we want rather than
# whatever the model chooses for the preset name.
_ASPECT_PIXEL_SIZE: dict[str, tuple[int, int]] = {
    "square_hd": (1024, 1024),
    "portrait_4_3": (1280, 1600),
    "portrait_16_9": (1088, 1920),
    "landscape_4_3": (1600, 1280),
    "landscape_16_9": (1920, 1088),
}

# v1.64 — ``_PULID_PIXEL_SIZE`` (1 MP variants for PuLID) was retired
# alongside the PuLID provider. Edit-mode models run at the full
# ``_ASPECT_PIXEL_SIZE`` table.


def resolve_output_size(
    spec: StyleSpec | None,
    face_area_ratio: float | None = None,
    *,
    framing: str | None = None,
) -> dict[str, int] | None:
    """Translate a style's ``output_aspect`` into a FAL ``image_size`` dict.

    Returns ``None`` when the spec is missing — callers should fall back to
    the provider's configured default (``portrait_4_3`` in production).

    v1.17 adaptive sizing: for ``needs_full_body`` styles with a tiny
    reference face (``face_area_ratio < 0.10``) we force the output
    down to 1 MP ``square_hd``. At 2 MP FAL edit-models distribute
    "attention budget" across the full-body scene and the face ends up
    soft; at 1 MP the model has to prioritise facial detail, and
    Real-ESRGAN restores the output resolution after the fact.

    v1.17.1: the 1 MP branch only runs when ``settings.real_esrgan_enabled``
    is on — without a diffusion-aware upscaler downstream, shipping 1024×1024
    regresses perceived face quality relative to the 2 MP portrait path.
    When ESRGAN is off we therefore keep the 2 MP ``portrait_4_3`` even
    for full-body × small-face cases. ``face_area_ratio=None`` (legacy
    callers / unit tests) also keeps the 2 MP behaviour regardless of
    the flag.

    v1.64: ``generation_mode`` was removed from the signature; the
    PuLID-only 1 MP table (``_PULID_PIXEL_SIZE``) is gone.
    """
    if spec is None:
        return None

    aspect: OutputAspect = getattr(spec, "output_aspect", "portrait_4_3")

    # v1.26: framing is a composition hint for the PROMPT, not for output
    # aspect. Earlier revisions had ``portrait`` → ``square_hd``, etc.,
    # which broke users' expectations (they selected the framing and
    # got the wrong canvas shape). Now ``framing`` only drives the
    # numerical anchor + reference padding; size is style-only.
    _ = framing  # retained in signature for callers; intentionally unused.

    needs_full_body = bool(getattr(spec, "needs_full_body", False))
    if (
        needs_full_body
        and face_area_ratio is not None
        and face_area_ratio > 0.0
        and face_area_ratio < 0.10
    ):
        # Local import to avoid a circular settings→prompts dependency at
        # module-load time (prompts are imported by config validators in
        # several code paths during app startup).
        try:
            from src.config import settings as _runtime_settings

            esrgan_on = bool(
                getattr(_runtime_settings, "real_esrgan_enabled", False),
            )
        except Exception:
            esrgan_on = False

        if esrgan_on:
            aspect = "square_hd"
            logger.info(
                "adaptive image_size: full-body style with small face "
                "(%.3f) → square_hd 1 MP (Real-ESRGAN will restore)",
                face_area_ratio,
            )
        else:
            logger.info(
                "adaptive image_size: full-body style with small face "
                "(%.3f) — ESRGAN disabled, keeping 2 MP portrait",
                face_area_ratio,
            )

    pixels = _ASPECT_PIXEL_SIZE.get(aspect)
    if pixels is None:
        pixels = _ASPECT_PIXEL_SIZE["portrait_4_3"]
    w, h = pixels
    return {"width": w, "height": h}


# ---------------------------------------------------------------------------
# Compact anchors — one PRESERVE phrase + one QUALITY phrase.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# v4.1 (May 2026) prompt-pipeline anchors.
#
# Two short blocks form the entire fixed tail for every photo prompt:
#
# * IDENTITY_PRESERVE_BLOCK — explicit identity anchors (face shape,
#   eye shape and colour, hairline, skin undertone, proportions). The
#   v1.32 wording is the proven baseline; v4.0 dropped most of these
#   anchors and replaced them with vague "facial features unchanged"
#   which the OpenAI / Nano Banana 2 docs warn against (the model
#   re-renders facial geometry given that latitude). v4.1 puts the
#   anchors back, in positive-framed prose.
#
# * PHOTOREAL_BLOCK — one camera-block, one materiality clause, one
#   light-integration clause. Skin tone is mentioned exactly once. No
#   color-grading / white-balance language — those forced the model
#   to re-tone the face on warm / neon scenes (the "вклеенное лицо"
#   failure mode reported by users).
#
# Pasted-on guard is dissolved into PHOTOREAL_BLOCK as a positive-
# framed "subject is genuinely present" clause; the standalone
# PASTED_ON_GUARD block is removed.
# ---------------------------------------------------------------------------

# Identity-preserve canonical block (v1.67, ~170 chars).
# v1.65 trimmed from 9 face anchors to 4: face shape, eye shape /
# colour, hairline, skin undertone. v1.67 drops "face shape" too —
# audit of v1.66 generations showed that the geometric reading of
# "identical face shape" was pulling edit-models toward copying the
# reference head/torso ratio (the "huge head" pathology). The
# remaining anchors (eyes / hairline / skin undertone) are purely
# textural — they carry identity without imposing a geometric
# constraint on the head's relative size in the frame. Wording
# stays positive-framed (no "unchanged" / "pasted on" / "rather
# than") so it passes the ``_has_disallowed_negative`` guard.
#
# v1.67 also relocates this block: ``model_wrappers._assemble`` now
# appends it as the LAST sentence of the prompt (after
# ``PHOTOREAL_BLOCK``), so recency bias reinforces composition
# rather than identity geometry. The cinematic anchor
# (``_COMPOSITION_NUMERICAL_HINT``) is still emitted FIRST and owns
# the early-attention budget.
IDENTITY_PRESERVE_BLOCK = (
    "Use the reference photo as the identity source — preserve the same "
    "person's facial features: eye shape and colour, hairline, skin "
    "undertone."
)


# v1.68 — P2.9 light-matching clause.
#
# The legacy ``PHOTOREAL_BLOCK`` already includes a brief
# "scene's ambient light grounds the subject" sentence, but its
# wording is generic enough that edit-models routinely fall back
# to a default studio key light when the reference photo carries a
# different light recipe than the requested scene (the
# "studio key-light on a sunset terrace" pathology surfaced in the
# May 2026 image-quality audit).
#
# This dedicated clause is sharper: it names the three axes that
# matter for perceived realism — colour temperature, direction,
# softness — and explicitly forbids overriding them with a studio
# key light unless the scene says so. Inserted immediately BEFORE
# :data:`IDENTITY_PRESERVE_BLOCK` so it lives at the tail of the
# prompt where edit-models weigh it heavily via recency bias.
# Gated on ``settings.light_match_clause_enabled``.
LIGHT_MATCH_CLAUSE = (
    "Match the subject's lighting to the scene's ambient light — "
    "colour temperature, direction, and softness — and do not add a "
    "studio key light unless the scene explicitly contains one."
)

# Photoreal block (v1.66, ~340 chars).
# v1.65 swapped the camera anchor from ``50mm lens at eye level`` to
# ``85mm portrait lens at chest height``. The 50mm-at-eye-level pair
# is the canonical "selfie perspective" wording — on tight-selfie
# references edit-models took it as a green light to copy the
# enlarged-head geometry of the input verbatim. 85mm at chest height
# is the canonical portrait-photography setup that compresses
# perspective and renders natural head-to-body proportions.
#
# v1.66 dropped the word ``portrait`` from the lens descriptor
# (``85mm portrait lens`` → ``85mm short-telephoto lens``). The second
# ``portrait`` mention in the prompt (the first is the framing
# directive in the cinematic anchor above) acted as a recency cue on
# edit models: even after the cinematic anchor instructed ``bust shot``
# the trailing ``portrait lens`` token pulled the model toward a
# tighter headshot crop. ``short-telephoto`` describes the same lens
# in technically-correct terms (85mm sits between standard and
# telephoto) without re-introducing the framing word.
# Single camera/DoF block, single materiality clause, single
# light-integration clause. Mentions skin tone exactly once (in the
# identity block above we say "skin undertone" — here we focus on
# lighting integration without re-grading the face).
# v1.70 — lens spec and shallow DoF removed. Edit-models (Nano Banana 2,
# GPT Image 2) on FAL routinely interpreted the explicit lens token
# (``85mm short-telephoto lens at chest height``) as a recency cue for
# headshot perspective, which compounded with the cinematic composition
# anchor and the per-framing pose hint to over-anchor the prompt on
# portrait crops. The lens/DoF lines were removed; we now only describe
# what makes a photo look real (skin texture + lighting integration)
# and let the model pick the camera setup that fits the scene. See
# docs/ANATOMY_INVESTIGATION.md F1 / F3 for the audit reasoning.
PHOTOREAL_BLOCK = (
    "Authentic skin texture with visible pores and small natural "
    "imperfections. The lighting matches the scene's ambient light in "
    "direction, colour temperature, and softness."
)


# v1.70 — per-framing block collapsed.
#
# The v1.68 per-framing dict carried three different lens specs
# (85mm / 50-70mm / 35-50mm) plus per-framing DoF directives. The
# v1.70 audit (docs/ANATOMY_INVESTIGATION.md) concluded that lens
# tokens are not a useful lever against the "huge head" pathology —
# they only over-anchored portrait perspective without compensating
# benefit. v1.70 made every entry equal :data:`PHOTOREAL_BLOCK`,
# which collapsed the ``photoreal_by_framing_enabled`` flag into a
# no-op. v1.70.4 then removed the flag and the gate in
# ``model_wrappers._resolve_tail``. The dict itself survives purely
# as a regression marker: ``test_photoreal_by_framing`` asserts each
# entry still equals ``PHOTOREAL_BLOCK`` so a future re-introduction
# of per-framing lens specs is caught immediately.
_PHOTOREAL_BY_FRAMING: dict[str, str] = {
    "portrait": PHOTOREAL_BLOCK,
    "half_body": PHOTOREAL_BLOCK,
    "full_body": PHOTOREAL_BLOCK,
}


# Natural-expression fallback. Used by ``composition_builder`` when
# the user did NOT pass an explicit mood / expression override.
# Wording is intentionally short and positive-framed so it survives
# prompt compression and passes the negative-phrase guard.
EXPRESSION_NATURAL = (
    "Keep the subject's natural facial expression and gaze from the "
    "reference photo."
)


# Short identity-lock suffix appended at the very end of every non-emoji
# prompt. Kept under 80 chars so it rarely trips the 1200 PROMPT_MAX_LEN
# budget; positive-framing only so it passes the regression guard in
# tests/test_prompts/test_positive_framing.py. Acts as a final anchor
# for FLUX.2 Pro Edit — empirically repeating "same person as the
# reference" once more at the tail improves prompt adherence on borderline
# identity cases without extra cost.
IDENTITY_LOCK_SUFFIX = "Final anchor: output must be the exact same person."

# ---------------------------------------------------------------------------
# v1.18 identity_scene (PuLID) anchors
# ---------------------------------------------------------------------------
# PuLID locks the face at the model level via ID adapter + face reference,
# so repeating PRESERVE_PHOTO's facial anchors actually harms the output:
# the Lightning sampler overcommits pixels to "identical face" semantics
# and the scene loses detail. For the identity_scene branch we therefore
# describe the scene, lighting, pose and camera — and let PuLID hold
# identity. A short ``SOLO_SUBJECT_ANCHOR`` guard still ships because
# PuLID is known to occasionally spawn a second face from a crowded prompt
# ("dating profile", "yacht party" etc.) and the VLM gate rejects those.
SOLO_SUBJECT_ANCHOR = (
    "Single subject in frame, one person only, full-face clearly visible, "
    "hands with five clearly separated fingers."
)

IDENTITY_SCENE_QUALITY = (
    "Photorealistic unedited photograph with natural depth of field: "
    "subject sharp, background softly resolved. "
    "True-to-life colors, even realistic lighting, "
    "authentic skin texture with natural pores."
)

DOC_PRESERVE = (
    "Preserve the exact same person from the reference photo: identical facial "
    "features, skin tone with natural pores, hair color and length, and "
    "head-to-shoulders proportion."
)

DOC_QUALITY = (
    "Photorealistic ID-style headshot, soft even frontal light, clean "
    "backdrop, true-to-life skin tones, authentic skin texture, sharp detail."
)

# ---------------------------------------------------------------------------
# Style dictionaries — removed in v1.70.10
# ---------------------------------------------------------------------------
#
# The historical ``DATING_STYLES`` / ``CV_STYLES`` / ``SOCIAL_STYLES``
# raw text-prompt dicts, their accompanying ``*_PERSONALITIES`` maps and
# the ``_STYLE_OVERRIDES`` clothing-override table all lived here as a
# JSON-load fallback. They have not been a runtime source of truth since
# the v1.66 → v3 migration: every style now ships through ``data/styles.json``
# and ``src/services/style_loader_v3.py``. The v1.70.6 cleanup converted the
# JSON-load exception path into a hard ``RuntimeError`` (style bootstrap is
# deploy-blocking), which left these ~800 lines of stale 2025 content with
# no consumer at all. v1.70.10 retires them.
#
# If a future change ever needs to look at the old text again, browse the
# pre-v1.70.10 history of this file (commit before the v1.70.10 bump).

# ---------------------------------------------------------------------------
# Typed style registry — built from the raw dicts above
# ---------------------------------------------------------------------------

STYLE_REGISTRY = StyleRegistry()

# ``_STYLE_OVERRIDES`` (gender-specific female clothing override table) was
# retired in v1.70.10 together with the legacy text-prompt dicts above.
# Every spec in ``data/styles.json`` now carries its own
# ``clothing_female`` / ``clothing_male`` fields, so a runtime override
# table is no longer needed. The hygiene test
# ``test_no_edit_compatible_false_specs`` was repointed to iterate
# ``STYLE_REGISTRY`` directly.

try:
    from src.services.style_loader import get_structured_specs

    # v1.70.19 (Phase 3.4 audit): the v1 registration pass below
    # populates ``STYLE_REGISTRY._by_key`` with ``StructuredStyleSpec``
    # entries and is **runtime authoritative**, not a leftover dupe.
    # The orchestrator (executor.py), input-quality gate, bot
    # handlers, and prompt builders all reach for it via
    # ``STYLE_REGISTRY.get(mode, style)`` to consume
    # ``output_aspect`` / ``needs_full_body`` / ``needs_torso`` /
    # ``.variant_by_id(...)`` / ``.clothing_for(gender)``. See
    # ``scripts/migrations/2026_05_v1_registration_audit/AUDIT.md``
    # for the full callsite map and the proposed multi-step follow-up
    # cycle that would let us finally drop this pass.
    for spec in get_structured_specs():
        STYLE_REGISTRY.register(spec)

    # v1.70.18 (Phase 3.3): the v2 bootstrap pass was retired. Every
    # entry in ``data/styles.json`` ships at ``schema_version: 3``
    # (locked by ``test_styles_json_v3_coverage``), so the historical
    # ``register_v2_styles_from_json`` call only built a parallel map
    # the runtime never consulted in production. ``StyleRegistry.get_v2``
    # / ``has_v2`` survive as a defensive lookup for the engine's
    # mid-bootstrap fallback path and for tests that exercise the v2
    # composition surface explicitly via
    # ``src.services.style_loader_v2.register_v2_styles_from_json``.

    # style-schema-v3 (prompt-pipeline-overhaul, 2026-04). As of
    # v1.70.x ``data/styles.json`` carries every entry at
    # ``schema_version: 3``; the ``style_schema_v3_enabled`` flag is
    # always-on. Phase 3 of the cleanup roadmap is collapsing the
    # three registration passes into the single v3 pass below.
    try:
        from src.services.style_loader_v3 import register_v3_styles_from_json

        register_v3_styles_from_json()
    except Exception as _v3_exc:  # noqa: BLE001 — additive path must never break v2
        logger.warning("style_loader_v3 failed: %s", _v3_exc)
except Exception as e:
    # v1.71 (Stage 7 of audit fix-up): the legacy
    # ``DATING_STYLES`` / ``CV_STYLES`` / ``SOCIAL_STYLES`` hardcoded
    # fallback was retired. The data was last touched in 2025 and
    # would silently re-register STALE specs if ``styles.json``
    # failed to load — which is exactly the kind of "ship the wrong
    # styles to users while the real ones are broken" failure mode
    # we want to catch loudly. Fail fast instead: a missing or
    # corrupt ``styles.json`` is a deploy-blocking error that must
    # be visible to the operator, not silently masked.
    #
    # v1.70.10 follow-up: the dicts themselves (~815 lines of stale
    # text content) have now been deleted from this module too —
    # nothing in ``src/`` consumed them after v1.70.6 made the JSON
    # bootstrap fail-fast. ``style_lint`` builds its hint table from
    # ``STYLE_REGISTRY`` and the one hygiene test that used to
    # iterate ``_STYLE_OVERRIDES`` was repointed to the registry.
    logger.critical(
        "style_registry_bootstrap_failed",
        extra={"error": str(e), "phase": "load_styles_from_json"},
    )
    raise RuntimeError(
        "Failed to bootstrap the style registry from data/styles.json. "
        "This is a deploy-blocking error: the service cannot generate "
        "images without a valid style catalogue."
    ) from e


# ---------------------------------------------------------------------------
# Prompt builders — compact 800–1200 char photorealistic template
# ---------------------------------------------------------------------------

_DOCUMENT_STYLE_KEYS = frozenset(
    {
        "photo_3x4",
        "passport_rf",
        "visa_eu",
        "visa_schengen",
        "visa_us",
        "photo_4x6",
        "driver_license",
    }
)


def is_document_style(style: str) -> bool:
    """True для CV-стилей «Фото на документы», где требуется строгая композиция."""
    return (style or "").strip() in _DOCUMENT_STYLE_KEYS


# v1.66 — studio-portrait exempt whitelist. These styles are by-design
# tight headshots / bust-shots taken in a controlled studio environment,
# so the "portrait pose directives" that v1.66 strips from career and
# lifestyle styles (``composed gaze``, ``Rembrandt lighting``, etc.)
# are legitimate here and must be preserved. The whitelist also makes
# them exempt from style-lint rules ``EXPRESSION_PORTRAIT_LEAK`` and
# ``SCENE_POSE_LEAK`` and from the CV-mode reference-padding boost —
# studio portraits are the one place where a tighter crop is the
# intended creative output.
_STUDIO_PORTRAIT_STYLE_KEYS: frozenset[str] = frozenset(
    {
        "formal_portrait",
        "studio_elegant",
    }
)


# v1.68 — extended whitelist gated by
# ``settings.studio_portrait_whitelist_v2``. These additional career
# styles share the same design intent as the v1.66 whitelist (a
# controlled environment, formal wardrobe, classic head-and-shoulders
# composition) — but they were historically left out, which meant
# they routed to ``half_body`` framing on default uploads and
# inherited the "huge head" pathology. With the flag on, they are
# short-circuited to ``portrait`` framing by
# :func:`src.services.composition_safety.resolve_effective_framing`
# just like the v1.66 entries, and the reference-padding gate keeps
# their intentionally tight crop intact.
_STUDIO_PORTRAIT_STYLE_KEYS_V2: frozenset[str] = frozenset(
    {
        "formal_portrait",
        "studio_elegant",
        # New in v1.68:
        "corporate",
        "boardroom",
        "legal_finance",
        "neutral",
        "medical",
    }
)


def is_studio_portrait_style(style: str) -> bool:
    """True для студийно-портретных стилей, освобождённых от нормализации v1.66.

    v1.68 — when ``settings.studio_portrait_whitelist_v2`` is True the
    extended whitelist (corporate / boardroom / legal_finance /
    neutral / medical) is consulted on top of the v1.66 set. The flag
    defaults to ``False`` so the rollout phase can enable it after
    Phase 1 P0 QA bakes in.
    """
    key = (style or "").strip()
    try:
        from src.config import settings as _settings
        _whitelist_v2_on = bool(
            getattr(_settings, "studio_portrait_whitelist_v2", False)
        )
    except Exception:
        _whitelist_v2_on = False
    if _whitelist_v2_on:
        return key in _STUDIO_PORTRAIT_STYLE_KEYS_V2
    return key in _STUDIO_PORTRAIT_STYLE_KEYS


_DOC_COMPOSITION_HINT: dict[str, str] = {
    "photo_3x4": "3:4 portrait framing, face fills 50-60% of the frame, small margin above the head.",
    "passport_rf": "7:9 portrait framing, frontal pose, face fills 50-60% of the frame.",
    "visa_eu": "7:9 portrait framing, face centered, 50-60% of the frame.",
    "visa_schengen": "7:9 portrait framing, face centered, 50-60% of the frame.",
    "visa_us": "1:1 square framing, face centered, 40-50% of the frame.",
    "photo_4x6": "2:3 portrait framing, face fills 40-50% of the frame.",
    "driver_license": "3:4 portrait framing, face centered.",
}


def _truncate(prompt: str) -> str:
    """Enforce the PROMPT_MAX_LEN budget in production."""
    if len(prompt) <= PROMPT_MAX_LEN:
        return prompt
    logger.warning(
        "prompt exceeded budget (%d > %d), truncating",
        len(prompt),
        PROMPT_MAX_LEN,
    )
    return prompt[:PROMPT_MAX_LEN].rstrip()


# v1.26: framing — это user-facing ракурс (портрет / полрост / полный рост).
# Раньше он жёстко переключал output aspect через resolve_output_size
# (square_hd / portrait_4_3 / portrait_16_9), что ломало формат файла
# независимо от стиля и пугало пользователей. Теперь framing влияет ТОЛЬКО
# на композицию промпта: короткая директива в текст + ничего в размер.
# Размер изображения по-прежнему задаёт стиль (spec.output_aspect).
_FRAMING_PROMPT_DIRECTIVES: dict[str, str] = {
    "portrait": "Framing: natural waist-up snapshot.",
    "half_body": (
        "Framing: half-body composition from the waist up, "
        "hands may be partially visible."
    ),
    "full_body": (
        "Framing: complete body in frame, subject centered with "
        "natural negative space."
    ),
}


# v1.65 — cinematic composition anchor for non-document styles.
#
# Background: the document path (``_DOC_COMPOSITION_HINT``) consistently
# produces correct anatomical proportions because it hands edit models
# an explicit "face fills X% of frame" sentence. v1.64 mirrored that
# mechanism for non-document styles via percentage targets, but the
# results on tight selfies were still inconsistent — edit-model
# attention treats numeric strings as weak signals when they compete
# with the visual layout of the reference image.
#
# v1.65 switches to cinematic vocabulary that edit-models learned on
# their supervised training data:
#
# * Explicit ``Reframe the reference into …`` operator (positive-framed
#   command to CHANGE the layout, not preserve it). This is the
#   biggest single lever for overcoming the "copy the reference layout"
#   default on FAL Nano Banana 2 / GPT Image 2 Edit.
# * Cinematic shot vocabulary (``bust shot`` / ``medium waist-up shot``
#   / ``full-length standing shot``) instead of percentage targets.
# * One positive-framed proportions clause ``natural human head-to-body
#   scale`` (does not violate ``_has_disallowed_negative`` and reads
#   well to the model).
#
# v1.68 (May 2026) — two corrections from the audit:
#
#   1. Geometry/text alignment. The wording previously said ``upper
#      quarter of the canvas`` (~25%) for portrait while
#      :data:`src.services.reference_preprocess._FRAMING_GEOMETRY`
#      lays out 28% face height with the centre at 30% (i.e. roughly
#      the upper third). The mismatch put text and the padded canvas
#      in disagreement, which edit-models resolved by averaging — the
#      "head too small" complement of the "head too large" pathology
#      seen on tight selfies. Wording updated to ``upper third of the
#      canvas height`` etc. so the two doctrines describe the same
#      target.
#   2. Lens dedup. The block carried ``85mm short-telephoto lens at
#      chest height`` while :data:`PHOTOREAL_BLOCK` repeated the same
#      ``85mm short-telephoto lens at chest height``. Two mentions of
#      the same lens token over-anchored the headshot perspective on
#      half-body / full-body framings. The cinematic anchor now stays
#      lens-agnostic ("a portrait bust shot taken at chest height" /
#      "a medium waist-up shot at chest height" / "a full-length
#      standing shot from a slight low angle") and ``PHOTOREAL_BLOCK``
#      remains the single source of truth for the lens spec.
#
# ``model_wrappers._assemble`` injects the relevant entry BEFORE
# :data:`IDENTITY_PRESERVE_BLOCK` so the layout instruction sits in
# the first third of the prompt, where edit models pay the most
# attention.
# v1.70 — cinematic head-anchor removed. The v1.65 textual anchor
# ("Reframe the reference into a head-and-shoulders bust shot ...
# head occupying roughly the upper third") was the strongest of the
# 5 head-cues we counted in the audit. After v1.70 the geometric
# half of the doctrine still ships via ``reference_preprocess``
# (it physically lays out the canvas with the face at the correct
# relative size for the requested framing) — the textual half is
# no longer needed because the model receives the same intent
# spatially without competing tokens. ``_assemble`` falls back to
# omitting this block when the framing key is missing.
_COMPOSITION_NUMERICAL_HINT: dict[str, str] = {}


# v1.68 — P2.10 per-framing pose hint.
#
# Edit-models default to symmetrical "hero stance" framing on
# full_body shots (feet centred, shoulders squared, weight even)
# and stiff "passport-mug" framing on tight portraits (eyes dead
# centre, head perfectly straight). Both read as obviously
# AI-generated even when every other anchor is correct.
# ``_POSE_BY_FRAMING`` anchors a relaxed natural posture so the
# model produces candid-looking body language by default. Hints
# are short and additive — they only nudge body geometry, never
# the wardrobe or expression channels. Emitted by
# ``model_wrappers._assemble`` immediately AFTER the wardrobe line
# (the natural place for body geometry) and gated on
# ``settings.pose_hint_enabled``.
_POSE_BY_FRAMING: dict[str, str] = {
    "portrait": (
        "Pose: relaxed natural posture, shoulders slightly angled, "
        "subject turned slightly off the central axis."
    ),
    "half_body": (
        "Pose: relaxed standing pose with a slight weight shift, "
        "hands visible or naturally placed at the sides."
    ),
    "full_body": (
        "Pose: comfortable standing pose with weight on one leg, "
        "natural casual posture, no symmetrical hero stance."
    ),
}


# v1.68 — P1.4: quantitative early-attention anchor for the prompt head.
#
# The cinematic ``_COMPOSITION_NUMERICAL_HINT`` above is the qualitative
# half ("bust shot", "waist-up", "full-length standing") — it owns the
# narrative composition slot of the prompt. ``_FACE_AREA_ANCHOR_BY_FRAMING``
# is the quantitative half: a single short sentence that gives the
# edit-model an explicit, measurable target for the face's share of
# the canvas area. The two together mirror the document-style path,
# where ``_DOC_COMPOSITION_HINT`` consistently produces correct
# anatomical proportions because it hands the model BOTH "face fills
# X% of the frame" AND a shot vocabulary descriptor.
#
# Gated by ``settings.numerical_percent_anchor_enabled`` so the
# rollout phase can enable it cleanly after Phase 1 P0 QA bakes in.
# The anchor is emitted as the VERY FIRST sentence of the prompt by
# ``model_wrappers._assemble`` — early-attention slot is where edit-
# models weigh quantitative directives the most.
#
# The percentages here describe AREA (width × height), not height
# alone, so they roughly square the ``face_height_ratio`` values
# in :data:`src.services.reference_preprocess._FRAMING_GEOMETRY`:
#
#   portrait : face_height_ratio=0.28 → area ≈ 0.28² × 0.7 ≈ 6-8%
#              (real-world face ≈ 7-8% body-width / canvas-width on a
#              bust shot, so ~5%). We round to a familiar "fills
#              roughly 6% of the frame area".
#   half_body: face_height_ratio=0.15 → area ≈ 2-3%.
#   full_body: face_height_ratio=0.08 → area ≈ 0.5-1%.
#
# Rounded to user-friendly cohorts so the text is short and crisp.
# v1.70 — face-area anchor removed. The v1.68 P1.4 anchor
# ("Anchor: the face occupies about 6% of the frame area") duplicated
# the cinematic ``_COMPOSITION_NUMERICAL_HINT`` (now also gone) in
# the numeric channel. Removing both leaves geometric anchoring to
# ``reference_preprocess.pad_reference_for_framing`` which lays out
# the canvas spatially.
#
# v1.70.3 dropped the unreachable ``if framing in <empty dict>:``
# branch from ``model_wrappers._assemble``; v1.70.4 also removed
# the ``numerical_percent_anchor_enabled`` flag in ``config`` since
# it had no consumer left. The dict itself stays as a regression
# marker — ``tests/test_prompts/`` asserts it remains empty so a
# future PR cannot silently bring the 6%-anchor back.
_FACE_AREA_ANCHOR_BY_FRAMING: dict[str, str] = {}


def _framing_directive(framing: str | None) -> str:
    """Translate a framing key into a compact composition line for the prompt."""
    if not framing:
        return ""
    return _FRAMING_PROMPT_DIRECTIVES.get(framing.strip().lower(), "")


# v4.1 (May 2026) — public ``build_dating_prompt`` / ``build_cv_prompt``
# / ``build_social_prompt`` and the shared ``_build_mode_prompt`` helper
# were removed. The single entrypoint for photo prompt building is
# ``PromptEngine.build_image_prompt`` which always routes through the
# v3 slot-based path (with v2-promoted specs auto-registered as v3).


def _identity_scene_opener(mode: str, style: str) -> str:
    """Return the first line of an identity_scene (PuLID) prompt.

    PuLID is a text-to-image model with a face reference, not an edit
    model — describing the reference photo as a starting point confuses
    Lightning. We use a direct scene-generation verb so the sampler
    commits the pixel budget to the new scene rather than trying to
    "preserve" invisible pieces of the input.

    Full-body styles get a pose hint so the model doesn't default to a
    mid-chest crop for styles like yoga/running/hiking.
    """
    # v1.19 — phrasing trimmed. The previous "Render a portrait of the
    # reference person in the scene" mentioned "person" twice and was
    # part of the duplicate-subject regression. One mention of
    # "subject" is enough; PuLID's ID adapter does the rest.
    spec = STYLE_REGISTRY.get(mode, style)
    if spec is not None and getattr(spec, "needs_full_body", False):
        return (
            "Photorealistic full-body portrait of the reference subject, "
            "adopting a natural pose that fits the scene below."
        )
    return (
        "Photorealistic portrait of the reference subject in the scene "
        "described below, with a natural pose fitting the scene."
    )


def _dating_social_change_instruction(mode: str, style: str) -> str:
    """Pick the base change-instruction for photo styles.

    v4.1 (May 2026): a single Google-formula opener for every photo
    mode. Google's Nano Banana 2 prompting guide recommends starting
    edit prompts with a narrative sentence that names the reference
    photo and the desired action — this gives the model a clear
    high-level intent before any anchor or composition detail.

    The verb "render" + the explicit "the same person" reference make
    it unambiguous that the edit must keep the original identity and
    place that subject in a new scene. We deliberately drop the
    pose-and-clothing detail from v4.0 ("adopting a natural pose…")
    so the per-style scene/wardrobe/expression slots can drive those
    aspects without competing with a fixed sentence.

    v1.70 (May 2026) — dropped the v1.65 ``Recompose the body so
    head, shoulders and torso read at natural human proportions``
    tail. The clause was the only place where the opener mentioned
    ``head`` explicitly; after the audit (docs/ANATOMY_INVESTIGATION.md)
    we settle on a body-only formulation that pushes the model toward
    natural proportions without giving it a geometric anchor for the
    head's size in the frame.
    """
    _ = STYLE_REGISTRY.get(mode, style)  # registry lookup retained for warm-up
    return (
        "Using the reference photo, render the same person in a new "
        "scene that fits the chosen setting. Show the subject "
        "naturally with realistic body proportions."
    )


def resolve_style_variant(
    mode: str, style: str, variant_id: str
) -> StyleVariant | None:
    """Return the registered StyleVariant for (mode, style, variant_id).

    Returns ``None`` for unknown combinations or for document styles —
    callers can treat that as "fall back to the base style".
    """
    if not variant_id:
        return None
    if mode == "cv" and (style or "").strip() in _DOCUMENT_STYLE_KEYS:
        return None
    spec = STYLE_REGISTRY.get(mode, style)
    if spec is None:
        return None
    return spec.variant_by_id(variant_id)


# ---------------------------------------------------------------------------
# Multi-pass step templates — compact single-paragraph variants
# ---------------------------------------------------------------------------

_STEP_CHANGE: dict[str, str] = {
    "background_edit": "Change the background to {description} while maintaining facial features, skin tone and body proportions, keeping clothing and pose of the person in the reference photo.",
    "clothing_edit": "Change the clothing to {description} while maintaining facial features, skin tone and body proportions, keeping the original background and pose.",
    "lighting_adjust": "Adjust the lighting and color grading to {description} while maintaining facial features and skin tone of the person in the reference photo.",
    "expression_hint": "Apply subtle expression adjustment toward {description} while maintaining facial features and skin tone.",
    "skin_correction": "Apply minor skin tone refinement and blemish cleanup while maintaining facial features and skin undertone of the person in the reference photo.",
    "style_overall": "Apply overall style enhancement toward {description} while maintaining facial features, skin tone and body proportions.",
}

STEP_TEMPLATES: dict[str, str] = {
    key: f"{change} {IDENTITY_PRESERVE_BLOCK} {PHOTOREAL_BLOCK}"
    for key, change in _STEP_CHANGE.items()
}


ENHANCEMENT_LEVEL_MODIFIERS: dict[int, str] = {
    1: "Apply subtle, minimal changes. Focus only on lighting and skin tone. Strength: very light.",
    2: "Apply moderate enhancement. Improve background and clothing while keeping natural look. Strength: medium.",
    3: "Apply noticeable enhancement. Include expression refinement and styling. Strength: confident.",
    4: "Apply full style transformation. Complete look overhaul with strong aesthetic. Strength: full.",
}


def build_step_prompt(
    step_template: str,
    style: str,
    mode: str = "dating",
    gender: str = "male",
    enhancement_level: int = 0,
) -> str:
    """Build a prompt for a single pipeline step using the StyleSpec registry."""
    template = STEP_TEMPLATES.get(
        step_template, STEP_TEMPLATES.get("style_overall", "")
    )
    spec = STYLE_REGISTRY.get_or_default(mode, style)
    if step_template == "expression_hint":
        description = spec.expression
    else:
        clothing = spec.clothing_for(gender)
        description = f"Background: {spec.background}. Clothing: {clothing}."
    prompt = template.replace("{description}", description)
    if enhancement_level and enhancement_level in ENHANCEMENT_LEVEL_MODIFIERS:
        prompt += " " + ENHANCEMENT_LEVEL_MODIFIERS[enhancement_level]
    return prompt


_EMOJI_GENDER_HINT = {
    "male": "Male character, masculine silhouette, short or styled hair as in the reference.",
    "female": "Female character, feminine silhouette, hair styled as in the reference.",
}


def build_emoji_prompt(base_description: str = "", gender: str = "") -> str:
    gender_key = (gender or "").strip().lower()
    gender_line = _EMOJI_GENDER_HINT.get(gender_key, "")
    prompt = (
        "Cartoon-styled version of the same person from the reference photo. "
        "Sticker avatar while maintaining exact facial proportions, face shape, "
        "eye shape and color, hairstyle and hair color, and skin tone in "
        "cartoon style — the sticker must be instantly recognizable as the "
        "same person. Render clean even skin in cartoon style. "
        "Bold outlines, flat vibrant colors, friendly expression, square composition."
    )
    if gender_line:
        prompt = f"{prompt} {gender_line}"
    desc = base_description[:400]
    if desc:
        prompt = f"{prompt} Character: {desc}"
    return prompt

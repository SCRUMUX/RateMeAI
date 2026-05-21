"""Centralized image-generation prompt builder for all modes.

Compact photorealistic template (v1.13, retained through v1.71): a
single natural paragraph in the 800–1200 character budget. Empirically
FAL's edit endpoints (Nano Banana 2, GPT Image 2 Edit) all degrade
when handed tag-sectioned layouts ([CHANGE]/[PRESERVE]/[QUALITY]) or
prompts above ~1200 characters. Two short anchors —
:data:`IDENTITY_PRESERVE_BLOCK` and :data:`PHOTOREAL_BLOCK` — cover
the semantics that previously required 10+ individual constants.

v1.71 cleanup retired the historical PuLID / multi-pass / head-anchor
constants together with the gated ``LIGHT_MATCH_CLAUSE`` rollback
escape hatch. The wire-prompt assembly path (see
``src.prompts.model_wrappers._assemble``) is now a single 7-stage
sequence with no feature flags.
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


# v1.70 retired the per-framing block (``_PHOTOREAL_BY_FRAMING``) —
# lens / DoF tokens over-anchored portrait perspective without
# compensating benefit (see docs/ANATOMY_INVESTIGATION.md F3). The
# v1.71 cleanup dropped the regression-marker dict too; the
# pin against re-introduction lives in
# ``test_prompt_anatomy_catalog.test_photoreal_block_no_lens_or_dof``.


# Natural-expression fallback. Used by ``composition_builder`` when
# the user did NOT pass an explicit mood / expression override.
# Wording is intentionally short and positive-framed so it survives
# prompt compression and passes the negative-phrase guard.
EXPRESSION_NATURAL = (
    "Keep the subject's natural facial expression and gaze from the "
    "reference photo."
)


# v1.70 dropped the PuLID-only ``SOLO_SUBJECT_ANCHOR`` /
# ``IDENTITY_SCENE_QUALITY`` constants and the v1.13 ``IDENTITY_LOCK_SUFFIX``
# tail — they had zero runtime consumers since the PuLID provider was
# retired in v1.64. The edit-mode pipeline relies on
# ``IDENTITY_PRESERVE_BLOCK`` for identity preservation.


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
#
# v1.71.2 — wording sharpened from passive ``Framing: …`` notes to an
# explicit ``Crop the frame …; do not render …`` directive. The
# post-mortem on the May 2026 ``singapore_marina_bay`` regression
# (full-body output on a portrait-class upload) traced the root cause
# to the wire prompt carrying ZERO crop signal — only ``_POSE_BY_FRAMING``
# (which describes posture, not framing) ever reached the model. Edit
# models given a portrait padded canvas + a wardrobe that mentions
# ``trousers`` + a sweeping outdoor scene comfortably "filled in" the
# blurred lower 60 % of the canvas with a fabricated body. The new
# wording supplies the missing crop directive in language that v1.70
# anatomy lint allows (no ``head-and-shoulders`` / ``bust shot`` /
# ``upper third`` head-anchor tokens).
_FRAMING_PROMPT_DIRECTIVES: dict[str, str] = {
    "portrait": (
        "Crop the frame above the chest; do not render the lower body."
    ),
    "half_body": (
        "Crop the frame above the waist; do not render the legs."
    ),
    "full_body": (
        "Full body visible from head to feet, balanced negative space."
    ),
}


# v1.71.2 — wardrobe filter by framing.
#
# Catalogue-level wardrobe strings tend to enumerate the FULL outfit
# ("smart fitted shirt, tailored dark trousers, polished modern
# shoes, well-fitted across the shoulders"). On a portrait or half-
# body composition that enumeration becomes a body-shape hint — the
# edit model treats the trouser/shoe mention as licence to render
# the lower body even when the framing directive (above) tells it
# not to. The runtime fix is to STRIP lower-body / footwear segments
# from the wardrobe string before the prompt is assembled, without
# touching the on-disk catalogue (which keeps the full outfit so
# the same row is reusable on a future full-body upload).
#
# Tokens are matched case-insensitive against comma-separated wardrobe
# segments. A segment is kept iff it carries none of the banned
# tokens for the current framing. Document styles bypass the filter
# entirely (DOC_PRESERVE has its own composition contract).
_LOWER_BODY_WARDROBE_TOKENS: tuple[str, ...] = (
    "trousers",
    "pants",
    "jeans",
    "slacks",
    "chinos",
    "leggings",
    "shorts",
    "skirt",
    "dress trousers",
    "denim",
    "khakis",
    "joggers",
    "sweatpants",
)
_FOOTWEAR_WARDROBE_TOKENS: tuple[str, ...] = (
    "shoes",
    "loafers",
    "sneakers",
    "trainers",
    "boots",
    "heels",
    "espadrilles",
    "flats",
    "derbies",
    "oxfords",
    "brogues",
    "mules",
    "sandals",
)


def _wardrobe_banned_tokens(framing: str | None) -> tuple[str, ...]:
    """Return the wardrobe tokens that must NOT appear for ``framing``.

    * ``portrait`` — drop both lower-body garments and footwear; the
      crop directive shows only chest and above.
    * ``half_body`` — drop only footwear; trousers / skirts may still
      enter the frame at the waist edge.
    * ``full_body`` / unknown / ``None`` — no filtering; the entire
      outfit is visible by design.
    """
    if not framing:
        return ()
    f = framing.strip().lower()
    if f == "portrait":
        return _LOWER_BODY_WARDROBE_TOKENS + _FOOTWEAR_WARDROBE_TOKENS
    if f == "half_body":
        return _FOOTWEAR_WARDROBE_TOKENS
    return ()


def filter_wardrobe_by_framing(clothing: str, framing: str | None) -> str:
    """Drop lower-body / footwear segments from a wardrobe string.

    Args:
        clothing: raw wardrobe string from the catalogue (or override)
            — segments separated by commas. ``"smart fitted shirt,
            tailored dark trousers, polished modern shoes, well-fitted
            across the shoulders"``.
        framing: ``"portrait" | "half_body" | "full_body" | None``.

    Returns:
        Filtered string; empty string if every segment matched a
        banned token. Whitespace is preserved between kept segments,
        trailing punctuation is left to the caller.
    """
    if not clothing:
        return ""
    banned = _wardrobe_banned_tokens(framing)
    if not banned:
        return clothing
    segments = [seg.strip() for seg in clothing.split(",")]
    kept: list[str] = []
    for seg in segments:
        if not seg:
            continue
        lower = seg.lower()
        if any(tok in lower for tok in banned):
            continue
        kept.append(seg)
    return ", ".join(kept)


# v1.65 introduced ``_COMPOSITION_NUMERICAL_HINT`` (cinematic
# "Reframe the reference …" anchor); v1.70 emptied the dict because
# the textual anchor stacked with reference padding to over-anchor
# headshot perspective (audit: docs/ANATOMY_INVESTIGATION.md F1).
# The geometric half of the doctrine still ships via
# ``reference_preprocess.pad_reference_for_framing`` — the canvas
# is physically laid out so the face lands at the right relative
# size, with no competing prompt token. v1.71 dropped the empty
# regression-marker dict; the pin against re-introduction lives in
# ``test_no_composition_reframe_sentence_in_wire_prompt``.


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


# v1.68 introduced ``_FACE_AREA_ANCHOR_BY_FRAMING`` (quantitative
# "face fills ~6% of the frame area" hint). v1.70 emptied it because
# it duplicated the cinematic anchor (also retired) in the numeric
# channel; v1.71 dropped the empty regression-marker dict. Geometric
# anchoring lives in ``reference_preprocess.pad_reference_for_framing``;
# the pin against re-introduction lives in
# ``test_no_composition_reframe_sentence_in_wire_prompt``.


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


# v1.71 — the multi-pass step templates (``_STEP_CHANGE`` /
# ``STEP_TEMPLATES`` / ``ENHANCEMENT_LEVEL_MODIFIERS`` /
# ``build_step_prompt``) were retired together with the reserved
# ``src.orchestrator.advanced`` package. The runtime always runs
# single-pass through ``ImageGenerationExecutor.single_pass``.


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

"""Style lint + naming-conflict engine.

Powers the admin curation workflow introduced in 1.29.0. The functions
here are read-only — they consume raw JSON entries (the same shape
:func:`src.services.style_loader.load_styles_from_json` returns) and
emit structured issue lists. The admin frontend renders these as
inline warnings on the style editor and as a separate report on the
conflicts page.

Two top-level entry points:

* :func:`lint_style` — single-style audit. Returns a list of
  :class:`LintIssue` records. Empty list = the style is clean.
* :func:`find_conflicts` — cross-style scan. Returns a dict with
  ``duplicate_labels`` / ``similar_labels`` / ``duplicate_ids``
  buckets. Empty buckets = catalog is clean.

The lint rules cover the four concrete defects the user flagged on
``mirror_aesthetic`` plus a handful of structural sanity checks:

* ``TRIGGER_DIRTY`` — trigger pool entry contains framing / lighting /
  weather words that should live in their own channel pool.
* ``SCENE_FRAMING_LEAK`` (v1.65) — ``scene_anchor`` contains framing
  tokens. Framing belongs to the framing slot
  (:data:`_FRAMING_PROMPT_DIRECTIVES` / :data:`_POSE_BY_FRAMING`);
  framing words in the scene description duplicate the signal and
  produce contradictory directives.
* ``QI_BASE_NONEMPTY`` (v1.65) — ``quality_identity.base`` is
  non-empty. The v4.1 pipeline funnels every photo style through the
  central :data:`PHOTOREAL_BLOCK`; per-style quality overrides
  compete with the curated 85mm-lens anchors.
* ``QI_PER_MODEL_TAIL_NONEMPTY`` (v1.65) — same logic for per-model
  tail overrides.
* ``INDOOR_SEASON`` / ``INDOOR_WEATHER`` — indoor styles must not
  expose season / weather (those make no sense indoors).
* ``DOCUMENT_AMBIENT`` — document styles should not expose any ambient
  channel — these go through the ``scene_preserve`` generation mode
  with neutral lighting.
* ``SEASON_INCOMPLETE`` — when ``season`` is enabled the pool must
  list all four (``spring`` / ``summer`` / ``autumn`` / ``winter``).
* ``EMPTY_POOL`` — channel is enabled but its ambient pool is empty,
  so the sampler has nothing to roll.
* ``UNKNOWN_CHANNEL`` — ``available_channels`` lists a name not in
  :data:`CONFIGURABLE_CHANNELS` (typo or schema drift).
* ``UNKNOWN_LOCATION`` — ``location_type`` is set to a value not in
  :data:`LOCATION_TYPES`.
* ``WARDROBE_POSE_LEAK`` (v1.71) — ``default_clothing`` or
  ``clothing.default.{male|female|neutral}`` contains a position
  directive (``above desk``, ``behind the desk``, ``in the foreground``,
  ``headshot``, ``visible above ...``). The wardrobe channel must
  describe the GARMENT, never how it is framed; pose-cues leaking
  through wardrobe override every framing / shoulder hint downstream
  and reproduce the v1.71 ``video_call`` glued-head pathology.
* ``TIGHT_INDOOR_SCREEN_SCENE`` (v1.71) — ``scene_anchor`` /
  ``base_scene`` / ``background.base`` describe a screen-facing
  workspace (``ring light``, ``monitor glow on the subject``,
  ``webcam``, ``camera on tripod``) without any spatial depth cue
  (``behind``, ``across the room``, ``in foreground``, ``window``,
  ``floor``). Edit models trained on the public web associate the
  former cues with tight webcam-style crops and render an oversized
  head; a depth cue gives them the perspective needed for a balanced
  full-body composition.
* ``WARDROBE_LOWER_BODY_NOT_FULL_BODY`` (v1.71.2) — informational
  notice. ``default_clothing`` / ``clothing.default.*`` enumerates
  lower-body garments (``trousers`` / ``jeans`` / ``slacks`` / …)
  or footwear (``shoes`` / ``loafers`` / ``boots`` / …) on a style
  whose framing pool exposes ``portrait`` or ``half_body``. The
  v1.71.2 ``filter_wardrobe_by_framing`` runtime strips those
  segments on tight-framing requests, so the on-disk wardrobe is
  curatorially correct (catalogue describes the full outfit) but
  the curator should know which segments will be invisible at
  prompt-assembly time.

Severity is either ``"error"`` (blocks save in strict admin mode) or
``"warning"`` (informational, save still allowed).
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

from src.prompts.style_schema_v3 import (
    CHANNEL_LIGHTING,
    CHANNEL_SEASON,
    CHANNEL_TIME_OF_DAY,
    CHANNEL_WEATHER,
    CONFIGURABLE_CHANNELS,
    LOCATION_TYPE_DOCUMENT,
    LOCATION_TYPE_INDOOR,
    LOCATION_TYPES,
)


# v1.66 — exempt-whitelist for the anatomy-cleanup lint rules below.
# Studio portrait styles are by-design tight headshots, and document
# styles have a fixed vendor-policy framing — both legitimately carry
# the "portrait pose directives" we strip from everything else.
#
# Inlined rather than re-imported from src.prompts.image_gen to avoid a
# style_lint → image_gen → style_loader import cycle when the linter
# runs over a partially-loaded module graph during admin save.
_LINT_STUDIO_PORTRAIT_STYLE_KEYS: frozenset[str] = frozenset(
    {
        "formal_portrait",
        "studio_elegant",
    }
)
_LINT_DOCUMENT_STYLE_KEYS: frozenset[str] = frozenset(
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
_LINT_ANATOMY_EXEMPT: frozenset[str] = (
    _LINT_STUDIO_PORTRAIT_STYLE_KEYS | _LINT_DOCUMENT_STYLE_KEYS
)


# v1.66 — EXPRESSION_PORTRAIT_LEAK. Semantic-conflict catalog: tokens
# that read as "render a tight studio portrait" to edit models, in
# direct competition with the v1.65 ``bust shot at natural human
# head-to-body scale`` cinematic anchor. The list is intentionally
# minimal (only canonical portrait-pose phrasing) so it never fires on
# legitimate lifestyle expressions like ``confident smile`` or
# ``relaxed gaze``.
_EXPRESSION_PORTRAIT_LEAK_RE = re.compile(
    r"\b("
    r"authoritative"
    r"|composed\s+gaze"
    r"|composed\s+brow"
    r"|composed\s+mouth"
    r"|composed\s+still"
    r"|composed\s+worldly"
    r"|composed\s+decisive"
    r"|steady\s+leadership"
    r"|leadership\s+gaze"
    r"|executive\s+vision"
    r"|timeless\s+authority"
    r"|distinguished\s+gravitas"
    r"|gravitas"
    r"|commanding\s+charismatic"
    r"|piercing"
    r"|polished\s+still\s+mouth"
    r"|steady\s+composed"
    r"|composed\s+powerful"
    r"|elevated\s+sophisticated\s+still"
    r")\b",
    re.IGNORECASE,
)


# v1.66 — SCENE_POSE_LEAK. Catches scene fragments that encode an
# implicit pose ("sit in a leather chair", "behind a desk",
# "webcam-friendly framing"). These make edit models compress the
# torso and enlarge the head relative to the visible body. Rembrandt
# lighting is whitelisted only when followed by ``lighting`` (the
# legitimate cinematography term) — the bare ``Rembrandt`` token is
# treated as a portrait-pose cue (it implies a studio headshot setup).
_SCENE_POSE_LEAK_RE = re.compile(
    r"\b("
    r"behind\s+(?:a|the)\s+desk"
    r"|leather\s+chair"
    r"|webcam-?friendly"
    r"|behind\s+(?:a|the)?\s*monitor"
    r"|seated\s+(?:in|behind|at)\s+(?:a|the)\s+(?:leather|chair|desk)"
    r"|Rembrandt(?!\s+lighting)"
    r")\b",
    re.IGNORECASE,
)


# v1.66 — WARDROBE_TIGHT_SUIT. Warn (not error) when a tailored-suit
# clothing string lacks an explicit shoulder cue. Without one, edit
# models tend to draw the suit silhouette too narrow at the
# shoulders, which makes the head look oversized. The migration script
# auto-appends ``, well-fitted across the shoulders`` for these — this
# lint protects against future admin edits that strip the cue.
_WARDROBE_SUIT_PATTERN = re.compile(
    r"\b("
    r"three-piece\s+suit"
    r"|tailored\s+\w*\s*suit"
    r"|navy\s+suit"
    r"|charcoal\s+suit"
    r"|formal\s+suit"
    r"|dark\s+formal\s+suit"
    r"|tailored\s+dark\s+suit"
    r")\b",
    re.IGNORECASE,
)
_WARDROBE_SHOULDER_CUE_PATTERN = re.compile(
    r"\b(shoulders?|shoulder\s+line|well-fitted\s+across\s+the\s+shoulders|"
    r"natural\s+shoulder)\b",
    re.IGNORECASE,
)


# v1.71 — WARDROBE_POSE_LEAK. Catches position directives sneaking
# through the wardrobe channel (the v1.71 ``video_call`` regression).
# ``default_clothing`` and ``clothing.default.*`` describe the GARMENT
# only — never how the model should crop the body. The phrasing
# ``visible above desk`` / ``framed at the chest`` / ``headshot`` etc.
# is treated by edit models as a hard crop directive and overrides
# every framing / shoulder cue downstream. ``Above the desk`` is a
# common photography expression and would create false positives —
# we therefore anchor on the explicit ``visible above`` / ``framed at``
# templates plus a handful of canonical pose terms.
_WARDROBE_POSE_LEAK_RE = re.compile(
    r"\b("
    r"visible\s+above"
    r"|above\s+(?:the\s+)?desk"
    r"|behind\s+(?:a|the)\s+desk"
    r"|framed\s+(?:at|from)"
    r"|head(?:shot|\s+shot)"
    r"|head-?and-?shoulders"
    r"|webcam(?:-friendly)?"
    r"|cropped\s+at\s+(?:the\s+)?(?:chest|shoulders|waist)"
    r"|sitting\s+at\s+(?:a|the)\s+desk"
    r"|on\s+(?:the\s+)?screen"
    # May 2026 audit — ``shoulders fully in frame`` is a crop
    # directive masquerading as a fit cue; the May 2026 social /
    # dating curation pass injected it into ``clothing.default.*``
    # of 40+ styles and it now overrides framing on portrait /
    # half_body draws (the model anchors the crop on the
    # shoulders even when scene_anchor implies a full-body).
    r"|shoulders\s+fully\s+in\s+frame"
    r")\b",
    re.IGNORECASE,
)


# v1.71 — TIGHT_INDOOR_SCREEN_SCENE. The post-mortem on
# ``video_call`` showed that screen-facing scene anchors ("ring
# light", "monitor glow on the subject", "webcam", "camera on
# tripod") collapse the head-to-body ratio toward a webcam selfie
# unless they are paired with a depth cue ("behind",
# "across the room", "in foreground", "window", "floor"). The
# warning fires only when the screen cue is present AND no depth
# cue rescues it. Curator can either drop the screen cue or add a
# depth keyword to dismiss the warning.
_SCREEN_FACING_RE = re.compile(
    r"\b("
    r"ring\s*light"
    r"|monitor\s+glow(?:\s+on\s+the\s+subject)?"
    r"|webcam"
    r"|camera\s+on\s+(?:a\s+)?tripod"
    r"|softbox\s+on\s+(?:the\s+)?subject"
    r"|on-?camera\s+light"
    r")\b",
    re.IGNORECASE,
)
_DEPTH_CUE_RE = re.compile(
    r"\b("
    r"behind"
    r"|across\s+(?:the|a)\s+room"
    r"|in\s+(?:the\s+)?foreground"
    r"|tall\s+window"
    r"|floor-to-ceiling"
    r"|polished\s+(?:wood(?:en)?|concrete|hardwood|marble)\s+floor"
    r"|hardwood\s+floor"
    r"|window\s+(?:light|behind|across)"
    r"|skyline"
    r"|bookshelf"
    r"|brick\s+wall"
    r"|plant\s+wall"
    r"|backdrop\s+wall"
    r"|acoustic\s+(?:panel|foam)"
    r"|panel\s+wall"
    r"|side\s+window"
    r")\b",
    re.IGNORECASE,
)


# v1.71.2 — WARDROBE_LOWER_BODY_NOT_FULL_BODY. Tokens whose presence
# in a wardrobe string means the runtime
# ``src.prompts.image_gen.filter_wardrobe_by_framing`` will strip
# the containing segment on a portrait / half_body framing request.
# The catalogue keeps the full outfit (correct on full_body), but
# the curator needs visibility into which segments will be invisible
# at prompt-assembly time. Source of truth for the runtime filter
# is :data:`src.prompts.image_gen._LOWER_BODY_WARDROBE_TOKENS` +
# :data:`src.prompts.image_gen._FOOTWEAR_WARDROBE_TOKENS`; we mirror
# the union here so the lint can run independently of the runtime
# module (avoids a style_lint → image_gen import cycle when admin
# saves load a partially-initialised module graph).
_WARDROBE_LOWER_BODY_TOKENS_RE = re.compile(
    r"\b("
    r"trousers"
    r"|pants"
    r"|jeans"
    r"|slacks"
    r"|chinos"
    r"|leggings"
    r"|shorts"
    r"|skirt"
    r"|dress\s+trousers"
    r"|denim"
    r"|khakis"
    r"|joggers"
    r"|sweatpants"
    r"|shoes"
    r"|loafers"
    r"|sneakers"
    r"|trainers"
    r"|boots"
    r"|heels"
    r"|espadrilles"
    r"|flats"
    r"|derbies"
    r"|oxfords"
    r"|brogues"
    r"|mules"
    r"|sandals"
    r")\b",
    re.IGNORECASE,
)


# v1.68 — DOUBLED_WORD. Catches accidental adjacent repetitions like
# ``diffused diffused daylight`` or ``warm warm sunlight``. The
# 2026_06_styles_cleanup migration removes existing instances; this
# lint protects against new ones sneaking back via admin edits.
# Pattern: any word (\w+) followed by whitespace and an identical
# word, case-insensitive. The duplication is the user-visible defect
# (the token costs prompt budget without adding signal) — never a
# legitimate pattern in a curated catalog.
_DOUBLED_WORD_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)


# v1.68 — SCENE_LIGHTING_DUPLICATE. The plan's P1.6 audit flagged 22
# styles whose ``scene_anchor`` carries a lighting cue (``golden
# sunset``, ``diffused daylight``) AND whose ``available_channels``
# enables ``lighting`` (so the sampler also rolls a separate lighting
# string). When both fire the wire prompt receives two lighting
# recipes; edit models tend to render a hybrid that satisfies neither.
# Warning-severity (not error) because the scene-narrative often needs
# the lighting cue for coherence — curator may legitimately keep it.
# v1.70 — NO_HEAD_TOKEN_IN_PROMPT.
#
# Defensive lint for the wire prompt. After the v1.70 cleanup the
# non-document prompt pipeline carries ZERO mentions of "head",
# "bust shot", "upper third" etc. The historical audit (see
# ``docs/ANATOMY_INVESTIGATION.md`` F1) attributed the "huge head"
# pathology to a 5:1 ratio of portrait-anchor cues vs body-anchor
# cues in the wire prompt. The clean-up reduced that ratio to 0:1;
# this lint ensures that future edits to ``image_gen.py``,
# ``model_wrappers.py`` or ``data/styles.json`` cannot re-introduce
# the forbidden tokens silently.
#
# Document styles (passport / visa / driver's licence) are exempt
# because their format requires a tight head-and-shoulders headshot
# by law; ``DOC_PRESERVE`` deliberately retains the phrasing.
#
# Public entrypoint: :func:`forbidden_head_tokens_in_prompt`. The
# golden-prompt test sweeps every fixture through this function and
# asserts the returned list is empty for non-document styles.
_PROMPT_FORBIDDEN_HEAD_TOKENS: tuple[str, ...] = (
    "head-and-shoulders",
    "bust shot",
    "upper third",
    "upper fifth",
    "upper quarter",
    "head occupying",
    "head-to-body",
    "head subtly turned",
    "head-to-shoulders",
)


def forbidden_head_tokens_in_prompt(
    prompt: str,
    *,
    style_id: str | None = None,
) -> list[str]:
    """Return the head-portrait tokens that appear in ``prompt``.

    Document styles (passport / visa / driver's licence / id-style
    headshots) are exempt because their vendor policy requires the
    tight head-and-shoulders framing. For every other style the
    returned list must be empty after the v1.70 cleanup.

    Case-insensitive substring scan against
    :data:`_PROMPT_FORBIDDEN_HEAD_TOKENS`.
    """
    if style_id and style_id.strip() in _LINT_DOCUMENT_STYLE_KEYS:
        return []
    haystack = (prompt or "").lower()
    return [t for t in _PROMPT_FORBIDDEN_HEAD_TOKENS if t in haystack]


_SCENE_LIGHTING_TOKENS: tuple[str, ...] = (
    "golden sunset",
    "warm sunset",
    "golden hour",
    "blue hour",
    "morning golden",
    "warm tungsten",
    "diffused daylight",
    "diffused window light",
    "natural daylight",
    "soft golden",
    "warm afternoon",
    "warm rim light",
    "rim light",
    "warm key light",
    "ambient lighting",
    "candlelight",
    "ring light",
)


class LintIssue(TypedDict):
    code: str
    severity: str  # "error" | "warning"
    message: str
    field: str
    detail: dict[str, Any]


_FRAMING_TOKENS: tuple[str, ...] = (
    "full-length",
    "full length",
    "tall standing",
    "head-to-toe",
    "head to toe",
    "full body",
    "full-body",
    "headshot",
    "head shot",
    "close-up",
    "close up",
    "wide shot",
    "from above",
    "low angle",
    "high angle",
    "bird's eye",
    "birds eye",
)


# v1.65 — SCENE_FRAMING_LEAK uses a narrower set than _FRAMING_TOKENS
# because ``from above`` / ``low angle`` / ``high angle`` are routinely
# used in scene descriptions to describe LIGHT direction
# (``warm light from above``) or stage geometry, not camera angle.
# Flagging them would produce noisy false positives on otherwise-clean
# styles. The list below is strictly composition / shot-size vocabulary
# that has no legitimate non-camera meaning.
_SCENE_FRAMING_TOKENS: tuple[str, ...] = (
    "full-length",
    "full length",
    "tall standing",
    "head-to-toe",
    "head to toe",
    "full body",
    "full-body",
    "headshot",
    "head shot",
    "close-up",
    "close up",
    "wide shot",
    "bird's eye",
    "birds eye",
)

_LIGHTING_TOKENS: tuple[str, ...] = (
    "warm light",
    "soft light",
    "diffused light",
    "rim light",
    "backlight",
    "blue hour",
    "golden hour",
    "harsh sunlight",
    "overcast lighting",
)

_WEATHER_TOKENS: tuple[str, ...] = (
    "rainy",
    "stormy",
    "snowy",
    "cloudy",
    "foggy",
    "misty",
    "in the rain",
    "in the snow",
)

_SEASON_TOKENS: tuple[str, ...] = (
    "in winter",
    "in summer",
    "in spring",
    "in autumn",
    "wintertime",
    "summertime",
    "springtime",
    "autumnal",
)

_REQUIRED_SEASONS: frozenset[str] = frozenset(("spring", "summer", "autumn", "winter"))

_AMBIENT_KEYS: tuple[str, ...] = (CHANNEL_LIGHTING, CHANNEL_WEATHER, CHANNEL_TIME_OF_DAY, CHANNEL_SEASON)


def _normalise_pool(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(v).strip() for v in raw if isinstance(v, str) and str(v).strip()]


def _hits(text: str, tokens: tuple[str, ...]) -> list[str]:
    """Case-insensitive substring scan returning the matched tokens."""
    haystack = text.lower()
    return [t for t in tokens if t in haystack]


def _iter_string_fields(obj: Any, path: list[str | int]):
    """Recursively yield ``(dotted_path, str_value)`` pairs.

    Used by the v1.68 ``DOUBLED_WORD`` rule which must inspect every
    string carried by a style entry (top-level + nested under
    ``ambient.*`` / ``channel_overrides`` / ``trigger_pool`` / etc.).
    The dotted path stays readable in the admin warning panel so the
    curator can navigate directly to the offending field.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            sub = path + [k]
            if isinstance(v, str):
                yield ".".join(str(p) for p in sub), v
            else:
                yield from _iter_string_fields(v, sub)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            sub = path + [i]
            if isinstance(v, str):
                yield ".".join(str(p) for p in sub), v
            else:
                yield from _iter_string_fields(v, sub)


def lint_style(raw: dict[str, Any]) -> list[LintIssue]:
    """Audit one style entry. Returns a list of :class:`LintIssue`.

    Accepts either a v2 or v3 raw entry — rules that depend on v3
    fields (``trigger_pool``, ``available_channels``, ``location_type``)
    are skipped silently when the entry is v1 / v2. The admin UI is
    expected to lint after every save; CI can call this on the live
    JSON to detect regressions.
    """
    issues: list[LintIssue] = []
    schema_version = int(raw.get("schema_version") or 0)

    # v1.68 — DOUBLED_WORD. Walk every string field in the entry
    # (including nested ones — ambient pools, channel overrides) and
    # flag adjacent repetitions like ``diffused diffused``. We collect
    # at most one issue per ``field path`` so an entry with three
    # offending pool entries surfaces three distinct rows, but a
    # single string with the same defect surfaces once.
    for field_path, value in _iter_string_fields(raw, []):
        m = _DOUBLED_WORD_RE.search(value)
        if not m:
            continue
        repeated = m.group(1)
        issues.append(
            LintIssue(
                code="DOUBLED_WORD",
                severity="error",
                message=(
                    f"{field_path} contains the adjacent doubled word "
                    f"{repeated!r} (in {value!r}). Run "
                    "``python -m scripts.migrations.2026_06_styles_cleanup."
                    "migrate`` to auto-fix, or strip the duplicate by "
                    "hand."
                ),
                field=field_path,
                detail={"word": repeated, "value": value},
            )
        )

    raw_channels = raw.get("available_channels") or []
    if isinstance(raw_channels, (list, tuple)):
        channels: list[str] = [str(c) for c in raw_channels if isinstance(c, str)]
    else:
        channels = []

    for ch in channels:
        if ch not in CONFIGURABLE_CHANNELS:
            issues.append(
                LintIssue(
                    code="UNKNOWN_CHANNEL",
                    severity="error",
                    message=(
                        f"available_channels contains unknown channel "
                        f"{ch!r}. Allowed: {list(CONFIGURABLE_CHANNELS)!r}."
                    ),
                    field="available_channels",
                    detail={"channel": ch},
                )
            )

    location_type = str(raw.get("location_type") or "").strip().lower()
    if location_type and location_type not in LOCATION_TYPES:
        issues.append(
            LintIssue(
                code="UNKNOWN_LOCATION",
                severity="error",
                message=(
                    f"location_type {location_type!r} is not one of "
                    f"{list(LOCATION_TYPES)!r}."
                ),
                field="location_type",
                detail={"value": location_type},
            )
        )

    trigger_pool = _normalise_pool(raw.get("trigger_pool"))
    if schema_version == 3 and not trigger_pool:
        issues.append(
            LintIssue(
                code="EMPTY_TRIGGER_POOL",
                severity="error",
                message=(
                    "v3 styles require a non-empty trigger_pool. The "
                    "trigger is the inviolable motif of the style."
                ),
                field="trigger_pool",
                detail={},
            )
        )

    for idx, trig in enumerate(trigger_pool):
        framing = _hits(trig, _FRAMING_TOKENS)
        lighting = _hits(trig, _LIGHTING_TOKENS)
        weather = _hits(trig, _WEATHER_TOKENS)
        season = _hits(trig, _SEASON_TOKENS)
        leaks = framing + lighting + weather + season
        if leaks:
            issues.append(
                LintIssue(
                    code="TRIGGER_DIRTY",
                    severity="warning",
                    message=(
                        f"trigger_pool[{idx}] = {trig!r} contains "
                        f"framing/lighting/weather/season tokens "
                        f"({leaks!r}); these belong in the corresponding "
                        "channel pool, not in the trigger."
                    ),
                    field="trigger_pool",
                    detail={"index": idx, "value": trig, "tokens": leaks},
                )
            )

    # v1.65 — ``SCENE_FRAMING_LEAK``. The scene description is meant to
    # describe the WHERE (landmark / setting), not the HOW (framing /
    # lens). When framing tokens leak into it they collide with the
    # framing directive that ``_FRAMING_PROMPT_DIRECTIVES`` /
    # ``_POSE_BY_FRAMING`` already deliver, so edit models receive
    # contradictory cues — the failure mode that drove the v1.65
    # anatomy fix in the first place. (Until v1.70 the textual head
    # anchor lived in ``_COMPOSITION_NUMERICAL_HINT``; that anchor was
    # retired but the lint stays — framing has no business in a scene
    # description.)
    #
    # We check both ``scene_anchor`` (v3 native) and ``base_scene`` (v2
    # / legacy admin entries) because :func:`migrate._apply` accepts
    # either as the source of truth for the resolved anchor.
    for scene_field in ("scene_anchor", "base_scene"):
        scene_value = raw.get(scene_field)
        if not isinstance(scene_value, str) or not scene_value.strip():
            continue
        framing_leaks = _hits(scene_value, _SCENE_FRAMING_TOKENS)
        if framing_leaks:
            issues.append(
                LintIssue(
                    code="SCENE_FRAMING_LEAK",
                    severity="warning",
                    message=(
                        f"{scene_field} = {scene_value!r} contains "
                        f"framing tokens {framing_leaks!r}; framing "
                        "belongs to the framing slot (_FRAMING_PROMPT_"
                        "DIRECTIVES / _POSE_BY_FRAMING), not the scene "
                        "description. Move these to a framing field or "
                        "strip them."
                    ),
                    field=scene_field,
                    detail={"tokens": framing_leaks},
                )
            )

        # v1.68 — SCENE_LIGHTING_DUPLICATE. Only fires when the
        # ``lighting`` channel is ALSO enabled — a scene-narrative
        # lighting cue is fine in styles whose ambient.lighting is
        # disabled (the scene cue is then the sole light directive).
        if CHANNEL_LIGHTING in channels:
            lighting_leaks = _hits(scene_value, _SCENE_LIGHTING_TOKENS)
            if lighting_leaks:
                issues.append(
                    LintIssue(
                        code="SCENE_LIGHTING_DUPLICATE",
                        severity="warning",
                        message=(
                            f"{scene_field} mentions lighting tokens "
                            f"{lighting_leaks!r} while the ``lighting`` "
                            "channel is enabled; the sampler will roll "
                            "an additional lighting string and the wire "
                            "prompt will carry two lighting recipes. "
                            "Move the cue into ``ambient.lighting`` or "
                            "drop it from the scene field."
                        ),
                        field=scene_field,
                        detail={"tokens": lighting_leaks},
                    )
                )

    # v1.65 — ``QI_BASE_NONEMPTY`` / ``QI_PER_MODEL_TAIL_NONEMPTY``.
    # The v4.1 prompt pipeline funnels every photo style through the
    # central :data:`PHOTOREAL_BLOCK`. Non-empty ``quality_identity.base``
    # or ``quality_identity.per_model_tail`` overrides on a style means
    # the style ships with bespoke quality wording that competes with
    # the centrally-curated v1.65 ``85mm portrait lens`` /
    # ``shallow depth of field`` anchors. The May 2026 v4 migration
    # already zeroed these fields across all ~100 styles; this lint
    # protects future admin edits from undoing that.
    quality_identity = raw.get("quality_identity")
    if isinstance(quality_identity, dict):
        base = quality_identity.get("base")
        if isinstance(base, str) and base.strip():
            issues.append(
                LintIssue(
                    code="QI_BASE_NONEMPTY",
                    # Escalated from ``warning`` to ``error`` in the
                    # May 2026 audit follow-up — the May 2026 v4
                    # migration zeroed these fields across the whole
                    # catalogue, so any non-empty value here is a
                    # regression that competes with PHOTOREAL_BLOCK.
                    severity="error",
                    message=(
                        "quality_identity.base is non-empty; v4.1 funnels "
                        "every style through the central PHOTOREAL_BLOCK "
                        "(85mm portrait lens, shallow DoF). Style-level "
                        "overrides compete with the curated anchors and "
                        "should be left empty."
                    ),
                    field="quality_identity.base",
                    detail={"length": len(base)},
                )
            )

        per_model = quality_identity.get("per_model_tail")
        if isinstance(per_model, dict):
            non_empty = sorted(
                k for k, v in per_model.items()
                if isinstance(v, str) and v.strip()
            )
            if non_empty:
                issues.append(
                    LintIssue(
                        code="QI_PER_MODEL_TAIL_NONEMPTY",
                        # Escalated to ``error`` in the May 2026 audit
                        # follow-up — see :data:`QI_BASE_NONEMPTY`
                        # above for the same reasoning.
                        severity="error",
                        message=(
                            f"quality_identity.per_model_tail has "
                            f"non-empty entries for models {non_empty!r}; "
                            "v4.1 routes every photo style through the "
                            "central PHOTOREAL_BLOCK so per-model overrides "
                            "should stay empty until a curation PR "
                            "re-introduces them deliberately."
                        ),
                        field="quality_identity.per_model_tail",
                        detail={"models": non_empty},
                    )
                )

    # v1.66 anatomy lint — three rules with a shared exempt-whitelist
    # for studio-portrait / document styles (the only legitimate
    # carriers of tight-portrait / studio-pose vocabulary in the
    # catalog).
    style_id = str(raw.get("id") or "").strip()
    anatomy_exempt = style_id in _LINT_ANATOMY_EXEMPT

    if not anatomy_exempt:
        expression = raw.get("expression")
        if isinstance(expression, str) and expression.strip():
            leaks = sorted({
                m.group(0).lower()
                for m in _EXPRESSION_PORTRAIT_LEAK_RE.finditer(expression)
            })
            if leaks:
                issues.append(
                    LintIssue(
                        code="EXPRESSION_PORTRAIT_LEAK",
                        severity="error",
                        message=(
                            f"expression contains studio-portrait tokens "
                            f"{leaks!r}; these compete with the v1.65 "
                            "cinematic composition anchor and produce "
                            "oversized-head artefacts on edit models. "
                            "Use lifestyle phrasing (``open``, ``relaxed``, "
                            "``natural``, ``confident``) instead, or add "
                            "the style to ``_STUDIO_PORTRAIT_STYLE_KEYS`` "
                            "if it really is a studio headshot."
                        ),
                        field="expression",
                        detail={"tokens": leaks},
                    )
                )

        scene_pose_sources: list[tuple[str, str]] = []
        for scene_field in ("scene_anchor", "base_scene"):
            scene_value = raw.get(scene_field)
            if isinstance(scene_value, str) and scene_value.strip():
                scene_pose_sources.append((scene_field, scene_value))
        bg = raw.get("background")
        if isinstance(bg, dict):
            bg_base = bg.get("base")
            if isinstance(bg_base, str) and bg_base.strip():
                scene_pose_sources.append(("background.base", bg_base))

        for field_name, scene_value in scene_pose_sources:
            pose_leaks = sorted({
                m.group(0).lower()
                for m in _SCENE_POSE_LEAK_RE.finditer(scene_value)
            })
            if pose_leaks:
                issues.append(
                    LintIssue(
                        code="SCENE_POSE_LEAK",
                        severity="error",
                        message=(
                            f"{field_name} contains implicit-pose tokens "
                            f"{pose_leaks!r} ({'leather chair' if 'leather chair' in pose_leaks else 'see tokens'} "
                            "and similar cues make edit models compress "
                            "the torso and enlarge the head). Describe "
                            "the SPACE only, not how the subject is "
                            "positioned inside it."
                        ),
                        field=field_name,
                        detail={"tokens": pose_leaks},
                    )
                )

        clothing_sources: list[tuple[str, str]] = []
        default_clothing = raw.get("default_clothing")
        if isinstance(default_clothing, str) and default_clothing.strip():
            clothing_sources.append(("default_clothing", default_clothing))
        clothing_block = raw.get("clothing")
        if isinstance(clothing_block, dict):
            default_block = clothing_block.get("default")
            if isinstance(default_block, dict):
                for gender_key in ("male", "female", "neutral"):
                    value = default_block.get(gender_key)
                    if isinstance(value, str) and value.strip():
                        clothing_sources.append(
                            (f"clothing.default.{gender_key}", value)
                        )

        seen_wardrobe_warning = False
        for field_name, value in clothing_sources:
            if not _WARDROBE_SUIT_PATTERN.search(value):
                continue
            if _WARDROBE_SHOULDER_CUE_PATTERN.search(value):
                continue
            if seen_wardrobe_warning:
                break  # one warning per style is enough
            seen_wardrobe_warning = True
            issues.append(
                LintIssue(
                    code="WARDROBE_TIGHT_SUIT",
                    severity="warning",
                    message=(
                        f"{field_name} mentions a tailored suit without "
                        "an explicit shoulder cue; append "
                        "``, well-fitted across the shoulders`` so the "
                        "edit model does not draw an over-narrow "
                        "silhouette (which makes the head look oversized)."
                    ),
                    field=field_name,
                    detail={"value": value},
                )
            )

        # v1.71 — WARDROBE_POSE_LEAK. Walk every wardrobe source and
        # flag every embedded pose directive; we emit one record per
        # offending field so the admin UI can highlight all of them
        # rather than burying duplicates behind a single notice.
        for field_name, value in clothing_sources:
            pose_leaks = sorted({
                m.group(0).lower()
                for m in _WARDROBE_POSE_LEAK_RE.finditer(value)
            })
            if not pose_leaks:
                continue
            issues.append(
                LintIssue(
                    code="WARDROBE_POSE_LEAK",
                    severity="error",
                    message=(
                        f"{field_name} = {value!r} contains pose / "
                        f"framing tokens {pose_leaks!r}; the wardrobe "
                        "channel must describe the GARMENT only. Pose "
                        "cues in clothing override every framing / "
                        "shoulder hint downstream and reproduce the "
                        "v1.71 ``video_call`` glued-head pathology. "
                        "Move framing to the framing slot and strip the "
                        "directive from the clothing string."
                    ),
                    field=field_name,
                    detail={"tokens": pose_leaks, "value": value},
                )
            )

        # v1.71.2 — WARDROBE_LOWER_BODY_NOT_FULL_BODY. Informational
        # notice for the curator. The runtime
        # ``filter_wardrobe_by_framing`` strips lower-body / footwear
        # segments on portrait / half_body framings; the catalogue is
        # still curatorially correct, but the curator should be aware
        # that on tight-framing requests those segments will not enter
        # the wire prompt. We only emit when:
        #
        #  * the style exposes ``portrait`` or ``half_body`` in its
        #    framing pool (``allowed_variations.framing`` /
        #    ``context_slots.framing``), AND
        #  * at least one wardrobe field carries a lower-body / footwear
        #    token from ``_WARDROBE_LOWER_BODY_TOKENS_RE``.
        #
        # The runtime wardrobe filter source-of-truth lives in
        # ``src.prompts.image_gen``; the regex below is intentionally
        # broader (covers a few extra synonyms) so the lint flags more
        # styles than the runtime silently filters — the curator sees
        # the full set in one place.
        framing_pool: list[str] = []
        for path in (
            ("allowed_variations", "framing"),
            ("context_slots", "framing"),
        ):
            cursor: Any = raw
            for key in path:
                if isinstance(cursor, dict):
                    cursor = cursor.get(key)
                else:
                    cursor = None
                    break
            if isinstance(cursor, list):
                framing_pool.extend(
                    str(v).strip().lower()
                    for v in cursor
                    if isinstance(v, str) and str(v).strip()
                )

        tight_framing_allowed = any(
            f in {"portrait", "half_body"} for f in framing_pool
        )
        if tight_framing_allowed:
            for field_name, value in clothing_sources:
                lower_hits = sorted({
                    m.group(0).lower()
                    for m in _WARDROBE_LOWER_BODY_TOKENS_RE.finditer(value)
                })
                if not lower_hits:
                    continue
                issues.append(
                    LintIssue(
                        code="WARDROBE_LOWER_BODY_NOT_FULL_BODY",
                        severity="warning",
                        message=(
                            f"{field_name} = {value!r} enumerates "
                            f"lower-body / footwear segments "
                            f"{lower_hits!r} on a style whose framing "
                            "pool exposes ``portrait`` or ``half_body``. "
                            "The v1.71.2 runtime ``filter_wardrobe_by_"
                            "framing`` will strip those segments on tight "
                            "framing requests — the catalogue stays "
                            "curatorially correct but the segments do "
                            "not reach the wire prompt. No action "
                            "required unless you want the segments to "
                            "survive: in that case move them to a "
                            "separate channel or split the style."
                        ),
                        field=field_name,
                        detail={
                            "tokens": lower_hits,
                            "framings_allowed": sorted(set(framing_pool)),
                        },
                    )
                )

        # v1.71 — TIGHT_INDOOR_SCREEN_SCENE. Walk every scene field;
        # warn (do not block) when a screen-facing cue ships without
        # any depth keyword. Curator can either drop the screen cue or
        # add a depth keyword (``behind`` / ``across the room`` /
        # ``window`` / ``floor``) to dismiss the warning.
        for field_name, scene_value in scene_pose_sources:
            screen_hits = sorted({
                m.group(0).lower()
                for m in _SCREEN_FACING_RE.finditer(scene_value)
            })
            if not screen_hits:
                continue
            if _DEPTH_CUE_RE.search(scene_value):
                continue
            issues.append(
                LintIssue(
                    code="TIGHT_INDOOR_SCREEN_SCENE",
                    severity="warning",
                    message=(
                        f"{field_name} mentions screen-facing cues "
                        f"{screen_hits!r} without any depth keyword "
                        "(``behind`` / ``across the room`` / ``in "
                        "foreground`` / ``window`` / ``floor``). Edit "
                        "models trained on the public web associate "
                        "these cues with tight webcam-style crops and "
                        "render an oversized head; add a depth keyword "
                        "or drop the screen cue."
                    ),
                    field=field_name,
                    detail={"tokens": screen_hits},
                )
            )

    ambient_raw = raw.get("ambient") if isinstance(raw.get("ambient"), dict) else {}
    pools: dict[str, list[str]] = {
        ch: _normalise_pool((ambient_raw or {}).get(ch)) for ch in _AMBIENT_KEYS
    }

    if location_type == LOCATION_TYPE_INDOOR:
        if CHANNEL_SEASON in channels:
            issues.append(
                LintIssue(
                    code="INDOOR_SEASON",
                    severity="error",
                    message=(
                        "indoor styles should not expose the season "
                        "channel — seasonal context is invisible inside."
                    ),
                    field="available_channels",
                    detail={},
                )
            )
        if CHANNEL_WEATHER in channels:
            issues.append(
                LintIssue(
                    code="INDOOR_WEATHER",
                    severity="error",
                    message=(
                        "indoor styles should not expose the weather "
                        "channel — weather context is invisible inside."
                    ),
                    field="available_channels",
                    detail={},
                )
            )

    if location_type == LOCATION_TYPE_DOCUMENT:
        for ch in _AMBIENT_KEYS:
            if ch in channels:
                issues.append(
                    LintIssue(
                        code="DOCUMENT_AMBIENT",
                        severity="error",
                        message=(
                            "document styles use a neutral lighting "
                            "context and should not expose any ambient "
                            f"channel (offending: {ch!r})."
                        ),
                        field="available_channels",
                        detail={"channel": ch},
                    )
                )

    if CHANNEL_SEASON in channels:
        season_pool = pools[CHANNEL_SEASON]
        seen = {s.lower() for s in season_pool}
        missing = sorted(_REQUIRED_SEASONS - seen)
        if missing:
            issues.append(
                LintIssue(
                    code="SEASON_INCOMPLETE",
                    severity="warning",
                    message=(
                        f"season channel enabled but pool is missing "
                        f"{missing!r}. All four seasons "
                        "(spring, summer, autumn, winter) should be "
                        "available so the sampler can roll any of them."
                    ),
                    field="ambient.season",
                    detail={"missing": missing, "have": sorted(seen)},
                )
            )

    for ch in _AMBIENT_KEYS:
        if ch in channels and not pools[ch]:
            issues.append(
                LintIssue(
                    code="EMPTY_POOL",
                    severity="error",
                    message=(
                        f"channel {ch!r} is enabled in available_channels "
                        f"but ambient.{ch} pool is empty — the sampler "
                        "would have nothing to roll."
                    ),
                    field=f"ambient.{ch}",
                    detail={"channel": ch},
                )
            )

    return issues


def _normalise_label(label: str) -> str:
    """Strip leading emoji + whitespace and lowercase for conflict matching."""
    text = (label or "").strip()
    out = []
    leading = True
    for ch in text:
        if leading and (not ch.isalnum() and ch not in "-_."):
            continue
        leading = False
        out.append(ch)
    return "".join(out).strip().lower()


def _levenshtein(a: str, b: str, *, cutoff: int = 5) -> int:
    """Bounded Levenshtein distance.

    Returns ``cutoff + 1`` once the running distance exceeds the
    cutoff so callers can short-circuit when they only care about
    "near matches". Pure Python; the catalog has < 200 entries so
    O(N^2) is fine.
    """
    if abs(len(a) - len(b)) > cutoff:
        return cutoff + 1
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        row_min = i
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            row_min = min(row_min, curr[j])
        if row_min > cutoff:
            return cutoff + 1
        prev = curr
    return prev[-1]


def find_conflicts(
    raw_styles: list[dict[str, Any]], *, similarity_cutoff: int = 2
) -> dict[str, list[dict[str, Any]]]:
    """Scan the catalog for duplicate / similar names and IDs.

    Args:
        raw_styles: list of raw JSON entries (same shape as
            :func:`src.services.style_loader.load_styles_from_json`).
        similarity_cutoff: maximum Levenshtein distance for a pair of
            normalised labels to count as "similar but not duplicate".
            ``2`` catches plurals, accidental typos, and emoji swaps;
            higher cutoffs pollute the report with unrelated styles.

    Returns:
        ``{
            "duplicate_labels": [{"label": str, "ids": [str, ...]}, ...],
            "similar_labels":   [{"label_a": str, "label_b": str,
                                  "id_a": str, "id_b": str,
                                  "distance": int}, ...],
            "duplicate_ids":    [str, ...]
        }``
    """
    seen_ids: dict[str, int] = {}
    by_label: dict[str, list[tuple[str, str]]] = {}
    rows: list[tuple[str, str, str]] = []

    for entry in raw_styles:
        sid = str(entry.get("id") or "").strip()
        if not sid:
            continue
        seen_ids[sid] = seen_ids.get(sid, 0) + 1
        label = str(entry.get("display_label") or "").strip()
        norm = _normalise_label(label)
        rows.append((sid, label, norm))
        if norm:
            by_label.setdefault(norm, []).append((sid, label))

    duplicate_labels: list[dict[str, Any]] = []
    for norm, group in sorted(by_label.items()):
        if len(group) > 1:
            duplicate_labels.append(
                {
                    "label": group[0][1] or norm,
                    "normalised": norm,
                    "ids": [g[0] for g in group],
                }
            )

    duplicate_ids = sorted(sid for sid, n in seen_ids.items() if n > 1)

    similar: list[dict[str, Any]] = []
    norms = [(sid, label, norm) for sid, label, norm in rows if norm]
    for i in range(len(norms)):
        sid_a, label_a, norm_a = norms[i]
        for j in range(i + 1, len(norms)):
            sid_b, label_b, norm_b = norms[j]
            if norm_a == norm_b:
                continue  # already covered by duplicate_labels
            dist = _levenshtein(norm_a, norm_b, cutoff=similarity_cutoff)
            if dist <= similarity_cutoff:
                similar.append(
                    {
                        "id_a": sid_a,
                        "id_b": sid_b,
                        "label_a": label_a,
                        "label_b": label_b,
                        "distance": dist,
                    }
                )

    similar.sort(key=lambda r: (r["distance"], r["id_a"], r["id_b"]))

    return {
        "duplicate_labels": duplicate_labels,
        "similar_labels": similar,
        "duplicate_ids": duplicate_ids,
    }

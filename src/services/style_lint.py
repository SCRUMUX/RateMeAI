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
  tokens. Framing is delivered exclusively by the central
  :data:`_COMPOSITION_NUMERICAL_HINT`; framing words in the scene
  description duplicate the signal and produce contradictory
  directives.
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

Severity is either ``"error"`` (blocks save in strict admin mode) or
``"warning"`` (informational, save still allowed).
"""

from __future__ import annotations

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
    # lens). When framing tokens leak into it they end up in the wire
    # prompt twice (once via ``_COMPOSITION_NUMERICAL_HINT``, once via
    # the scene line) and edit models receive contradictory directives
    # — the failure mode that drove the v1.65 anatomy fix in the first
    # place.
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
                        f"framing tokens {framing_leaks!r}; framing is "
                        "delivered by _COMPOSITION_NUMERICAL_HINT, not by "
                        "the scene description. Move these to a framing "
                        "field or strip them."
                    ),
                    field=scene_field,
                    detail={"tokens": framing_leaks},
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
                    severity="warning",
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
                        severity="warning",
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

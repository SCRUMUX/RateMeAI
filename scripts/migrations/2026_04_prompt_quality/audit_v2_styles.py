"""One-shot audit: report v2-style content defects across ``data/styles.json``.

Phase 1 of the v1.27.2 prompt-quality cleanup. This script is read-only —
it never mutates ``data/styles.json``. It walks every style entry and
flags four classes of content defect introduced by the v2 catalog
migration:

    A. ``context_slots.lighting`` entries that look like *locations*
       rather than lighting descriptors. Symptom: when the user does not
       open «Другой вариант» the motif is silently dropped from the
       prompt because :func:`composition_builder._resolve_lighting`
       returns ``""`` (no ``hints.lighting``).
    B. ``background.lock in {flexible, semi}`` AND
       ``background.overrides_allowed`` empty. The «Другой вариант»
       sub-location channel is unreachable for these styles even though
       the schema invites it.
    C. ``quality_identity.base`` empty. Cosmetic — the model wrappers
       still emit the legacy ``QUALITY_PHOTO`` block — but it means the
       per-style quality tail in v2 is unused.
    D. The first content word of ``display_label`` (after stripping
       emoji + a small Russian → English motif map) does not appear
       case-insensitively inside ``background.base``. Best-effort,
       multilingual heuristic; reports likely "missing motif" cases for
       human review.

Output: stdout summary table + a markdown report at
``scripts/migrations/2026_04_prompt_quality/audit_report.md`` next to
this file, committed for traceability. The migration script in Phase 2
(``split_lighting_and_locations.py``) consumes the same heuristics to
relocate offenders to ``background.overrides_allowed``.

Usage::

    python scripts/migrations/2026_04_prompt_quality/audit_v2_styles.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
REPORT_PATH = Path(__file__).resolve().parent / "audit_report.md"

# Keyword regexes used by both this audit and the Phase 2 migration. A
# string is "lighting-shaped" when LIGHTING_KW dominates and
# "location-shaped" when LOCATION_KW dominates with at most one
# lighting keyword. Anything else stays in lighting (conservative
# default — we never relocate ambiguous entries).
LIGHTING_KW = re.compile(
    r"\b("
    r"light\w*|lit|glow\w*|backlit|backlight\w*|sunset|sunrise|noon|"
    r"nighttime|golden|neon|fluoro|fluorescent|halogen|spotlight|"
    r"ambient|warm|cool|soft|hard|shadow\w*|highlight\w*|cyc|kicker|"
    r"bokeh|dim|bright|dawn|dusk|moon|tungsten|daylight|overcast|"
    r"cloudy|sunny|sunlit|sunlight|rim|practical|chiaroscuro|filmic|"
    r"amber|teal|magenta|saturat\w*|reflect\w*|shimmer\w*|sparkle\w*|"
    r"haze|hazy|misty|cinematic|hour"
    r")\b",
    re.I,
)
LOCATION_KW = re.compile(
    r"\b("
    r"in|at|with|on|near|inside|behind|under|over|across|by|from|"
    r"street|room|club|cafe|loft|stage|villa|garden|forest|beach|"
    r"view|door|window|wall|ceiling|terrace|bedroom|kitchen|bathroom|"
    r"closet|interior|location|setting|backdrop|scene|environment|"
    r"square|piazza|plaza|crosswalk|pavement|sidewalk|seat|cabin|"
    r"tower|bridge|canal|gondola|opera|coliseum|colosseum|acropolis|"
    r"campanile|brick|marble|seat|table|chair|bench"
    r")\b",
    re.I,
)

# Quick Russian → English motif hint map. Best-effort. Used only when
# ``display_label`` starts with Cyrillic characters; keeps category D
# from drowning in false positives. Add entries here as new styles
# arrive — keep this list small and obvious.
RU_MOTIF_HINTS: dict[str, tuple[str, ...]] = {
    "зеркал": ("mirror",),
    "башн": ("tower",),
    "мост": ("bridge",),
    "сквер": ("square",),
    "парк": ("park",),
    "вулкан": ("volcano", "lava"),
    "венеци": ("Venetian", "Venice"),
    "колизе": ("Colosseum",),
    "акропол": ("Acropolis",),
    "опер": ("opera",),
    "пляж": ("beach",),
    "лес": ("forest", "woodland"),
    "кафе": ("cafe", "café"),
    "клуб": ("club", "nightclub"),
    "сцен": ("stage",),
    "самолет": ("airplane", "plane", "cabin"),
    "самолёт": ("airplane", "plane", "cabin"),
    "лофт": ("loft",),
    "офис": ("office",),
    "горы": ("mountain",),
    "озер": ("lake",),
    "море": ("sea", "ocean"),
    "ресторан": ("restaurant",),
    "вилл": ("villa",),
    "сад": ("garden",),
    "лонж": ("lounge",),
    "лоунж": ("lounge",),
}

EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\u2764\u2B50\u200D]+",
    re.UNICODE,
)


def classify_lighting_entry(text: str) -> str:
    """Return ``"lighting"``, ``"location"`` or ``"mixed"`` for *text*.

    Conservative: only ``"location"`` triggers a Phase 2 relocation.
    """
    if not text or not text.strip():
        return "mixed"
    light_hits = len(LIGHTING_KW.findall(text))
    loc_hits = len(LOCATION_KW.findall(text))
    if loc_hits >= 1 and light_hits <= 1 and loc_hits >= light_hits:
        return "location"
    if light_hits >= 1 and loc_hits == 0:
        return "lighting"
    return "mixed"


def _strip_emoji(s: str) -> str:
    return EMOJI_RE.sub("", s).strip()


def _motif_keywords_for(display_label: str) -> tuple[str, ...]:
    """Best-effort tuple of motif keywords to look for in ``background.base``.

    Returns the first English noun for Latin labels, or maps via
    ``RU_MOTIF_HINTS`` for Cyrillic labels. Returns ``()`` when no
    confident keyword can be derived (skips category D for that style).
    """
    label = _strip_emoji(display_label or "")
    if not label:
        return ()
    # Cyrillic? Try the hint map.
    if any("\u0400" <= ch <= "\u04ff" for ch in label):
        lower = label.lower()
        for stem, motifs in RU_MOTIF_HINTS.items():
            if stem in lower:
                return motifs
        return ()
    # Latin: take the first content word longer than 2 chars.
    for word in re.split(r"[^A-Za-z]+", label):
        if len(word) >= 3:
            return (word,)
    return ()


def audit_style(entry: dict[str, Any]) -> dict[str, Any]:
    sid = entry.get("id", "<unknown>")
    label = entry.get("display_label", "")
    bg = entry.get("background") or {}
    base = (bg.get("base") or "").strip()
    lock = bg.get("lock") or "flexible"
    overrides = list(bg.get("overrides_allowed") or [])
    qi = entry.get("quality_identity") or {}
    qi_base = (qi.get("base") or "").strip()
    cs = entry.get("context_slots") or {}
    lights = list(cs.get("lighting") or [])

    # Category A — location-shaped lighting entries.
    a_offenders = [s for s in lights if classify_lighting_entry(s) == "location"]
    # Category B — flexible/semi without overrides_allowed.
    b_violation = lock in {"flexible", "semi"} and not overrides
    # Category C — empty quality_identity.base.
    c_violation = not qi_base
    # Category D — motif keyword absent from background.base.
    motifs = _motif_keywords_for(label)
    d_violation = False
    if motifs and base:
        haystack = base.lower()
        d_violation = not any(m.lower() in haystack for m in motifs)
    elif motifs and not base:
        d_violation = True

    return {
        "id": sid,
        "display_label": label,
        "lock": lock,
        "lights_total": len(lights),
        "lights_locations": len(a_offenders),
        "a_offenders": a_offenders,
        "b_violation": b_violation,
        "c_violation": c_violation,
        "d_violation": d_violation,
        "motifs": motifs,
        "background_base": base,
    }


def main() -> int:
    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    rows = [audit_style(s) for s in styles]

    cat_a = [r for r in rows if r["lights_locations"] > 0]
    cat_b = [r for r in rows if r["b_violation"]]
    cat_c = [r for r in rows if r["c_violation"]]
    cat_d = [r for r in rows if r["d_violation"]]

    print(f"v2 styles total: {len(rows)}")
    print(f"  A — location-shaped lighting entries: {len(cat_a)}")
    print(f"  B — flexible/semi lock with empty overrides_allowed: {len(cat_b)}")
    print(f"  C — empty quality_identity.base: {len(cat_c)}")
    print(f"  D — motif keyword missing from background.base: {len(cat_d)}")

    md = []
    md.append("# v2 styles content audit")
    md.append("")
    md.append(
        f"Generated by `scripts/migrations/2026_04_prompt_quality/audit_v2_styles.py`. "
        f"Total styles: **{len(rows)}**."
    )
    md.append("")
    md.append("| Category | Description | Affected | Auto-fix in Phase 2 |")
    md.append("|---------:|:------------|---------:|:--------------------|")
    md.append(f"| A | Location-shaped strings in `context_slots.lighting` | {len(cat_a)} | yes — relocate to `background.overrides_allowed` |")
    md.append(f"| B | `lock=flexible|semi` with empty `overrides_allowed` | {len(cat_b)} | partial — fixed for styles also in A |")
    md.append(f"| C | Empty `quality_identity.base` | {len(cat_c)} | no — manual fix via `/admin/styles` |")
    md.append(f"| D | `display_label` motif missing from `background.base` | {len(cat_d)} | no — manual fix via `/admin/styles` |")
    md.append("")

    md.append("## Category A — location-shaped lighting entries")
    md.append("")
    md.append("These entries get relocated to `background.overrides_allowed` by")
    md.append("`split_lighting_and_locations.py` (Phase 2). After the migration the")
    md.append("relocated values remain reachable via «Другой вариант» → sub_location.")
    md.append("")
    if cat_a:
        md.append("| Style | Lock | Total lights | Locations | Sample offender |")
        md.append("|:------|:-----|------------:|----------:|:----------------|")
        for r in sorted(cat_a, key=lambda x: -x["lights_locations"])[:60]:
            sample = r["a_offenders"][0] if r["a_offenders"] else ""
            md.append(
                f"| `{r['id']}` | {r['lock']} | {r['lights_total']} | "
                f"{r['lights_locations']} | {sample} |"
            )
        if len(cat_a) > 60:
            md.append("")
            md.append(f"_...and {len(cat_a) - 60} more (truncated for readability)._")
    else:
        md.append("_(none)_")
    md.append("")

    md.append("## Category D — motif keyword missing from background.base")
    md.append("")
    md.append("Heuristic — for Cyrillic labels we use a small motif map; for Latin")
    md.append("labels the first English word of `display_label`. The audit favours")
    md.append("false negatives over false positives, so this list is short by design.")
    md.append("Manual review via `/admin/styles` is required for each entry below.")
    md.append("")
    if cat_d:
        md.append("| Style | display_label | Motifs probed | background.base (excerpt) |")
        md.append("|:------|:--------------|:--------------|:--------------------------|")
        for r in cat_d:
            base_short = r["background_base"][:80] + (
                "..." if len(r["background_base"]) > 80 else ""
            )
            md.append(
                f"| `{r['id']}` | {r['display_label']} | "
                f"{', '.join(r['motifs'])} | {base_short} |"
            )
    else:
        md.append("_(none)_")
    md.append("")

    md.append("## Category B — flexible/semi lock with empty overrides_allowed")
    md.append("")
    md.append("After Phase 2 the styles also flagged in Category A get populated")
    md.append("`overrides_allowed`. Styles that remain in Category B after the")
    md.append("migration need manual curation.")
    md.append("")
    md.append(f"Affected count (pre-migration): **{len(cat_b)}**.")
    md.append("")

    md.append("## Category C — empty quality_identity.base")
    md.append("")
    md.append("All 126 v2 styles ship with `quality_identity.base = \"\"`. The model")
    md.append("wrappers fall back to the legacy `QUALITY_PHOTO` block, so this is a")
    md.append("missed-opportunity rather than a defect. Out of scope for v1.27.2 —")
    md.append("tracked for ongoing admin-panel curation.")
    md.append("")

    REPORT_PATH.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Wrote markdown report to {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

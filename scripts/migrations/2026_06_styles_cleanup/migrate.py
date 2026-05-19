"""v1.68 styles.json cleanup (Phase 2 P1.6).

The May 2026 image-quality audit found three classes of data-quality
defects in ``data/styles.json`` that contribute to noise in the
early-attention slot of the wire prompt:

1. **Doubled adjacent words** — typos like ``diffused diffused
   daylight`` or ``warm warm afternoon``. These leak into the wire
   prompt verbatim and waste the prompt's token budget on duplicate
   directives that the edit model has to reconcile. Confidence of
   the fix is high (a deterministic ``\\b(\\w+) \\1\\b`` regex).

2. **Lighting tokens in ``scene_anchor`` overlapping with
   ``ambient.lighting``** — when a style ships ``scene_anchor`` with
   "golden sunset" AND ``ambient.lighting`` with "warm afternoon
   sunlight", the prompt assembler emits the two as separate
   sentences and the model receives two competing lighting recipes.
   This is harder to auto-fix (the scene narrative often *needs*
   the lighting cue for coherence), so the script only AUDITS this
   class — it never rewrites scene narrative without human review.

3. **scene_overrides with mixed scene + lighting fragments** — same
   reason as (2), audit-only.

Usage::

    # dry-run preview (no file written, prints diff summary)
    python -m scripts.migrations.2026_06_styles_cleanup.migrate --dry-run

    # apply the doubled-word fixes + write audit CSV
    python -m scripts.migrations.2026_06_styles_cleanup.migrate

    # restrict to a subset of style keys (e.g. for cherry-pick QA)
    python -m scripts.migrations.2026_06_styles_cleanup.migrate --keys corporate boardroom

Outputs (in apply mode):

* ``data/styles.json`` updated in place with doubled-word fixes.
* ``data/.styles_backup/styles.<timestamp>.json`` backup of the
  pre-migration file (gitignored to avoid catalog history bloat).
* ``scripts/migrations/2026_06_styles_cleanup/audit.csv`` — per-field
  audit of every change applied AND every lighting-leak / mixed
  scene_override that the human curator should review separately.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
BACKUP_DIR = REPO_ROOT / "data" / ".styles_backup"
AUDIT_PATH = Path(__file__).resolve().parent / "audit.csv"


# ---------------------------------------------------------------------------
# Doubled adjacent words.
# ---------------------------------------------------------------------------
#
# ``\b(\w+)\s+\1\b`` matches any word repeated with whitespace between.
# Case-insensitive so ``Diffused diffused`` and ``WARM Warm`` both fire.
# We do NOT use the ``re.DOTALL`` flag — newlines never appear inside a
# styles.json string field, so word-boundary semantics are crisp.
_DOUBLED_WORD_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)


def _fix_doubled_words(value: str) -> tuple[str, int]:
    """Return (cleaned, n_fixes). ``n_fixes`` counts replacements."""
    n = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal n
        n += 1
        return match.group(1)

    cleaned = _DOUBLED_WORD_RE.sub(_sub, value)
    # The regex won't catch triplets in one pass; loop while it changes.
    while _DOUBLED_WORD_RE.search(cleaned):
        cleaned = _DOUBLED_WORD_RE.sub(_sub, cleaned)
    return cleaned, n


# ---------------------------------------------------------------------------
# Lighting / weather token taxonomy (audit-only).
# ---------------------------------------------------------------------------
_LIGHTING_TOKENS: tuple[str, ...] = (
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


def _scan_lighting_tokens(value: str) -> list[str]:
    """Return the lighting tokens that appear (case-insensitive) in ``value``."""
    if not isinstance(value, str):
        return []
    lower = value.lower()
    return [tok for tok in _LIGHTING_TOKENS if tok in lower]


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------


def _walk_string_fields(
    obj: Any,
    path: list[str | int],
):
    """Yield ``(path_str, value, setter)`` for every string field below
    ``obj``. ``setter`` is a callable that replaces the value in-place
    so the migration can mutate without rebuilding the structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            sub_path = path + [k]
            if isinstance(v, str):
                yield (".".join(str(p) for p in sub_path), v,
                       lambda new, _k=k, _o=obj: _o.__setitem__(_k, new))
            else:
                yield from _walk_string_fields(v, sub_path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            sub_path = path + [i]
            if isinstance(v, str):
                yield (".".join(str(p) for p in sub_path), v,
                       lambda new, _i=i, _o=obj: _o.__setitem__(_i, new))
            else:
                yield from _walk_string_fields(v, sub_path)


# ---------------------------------------------------------------------------
# Migration core
# ---------------------------------------------------------------------------


def _backup_styles_file(timestamp: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"styles.{timestamp}.json"
    shutil.copy2(STYLES_PATH, dest)
    return dest


def _load_styles() -> list[dict[str, Any]]:
    return json.loads(STYLES_PATH.read_text(encoding="utf-8"))


def _save_styles(entries: list[dict[str, Any]]) -> None:
    STYLES_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _process(
    entries: list[dict[str, Any]],
    allowed_keys: set[str] | None,
) -> tuple[int, int, list[dict[str, str]]]:
    """Walk entries, apply doubled-word fixes, gather audit rows.

    Returns ``(n_entries_changed, n_fixes_total, audit_rows)``.
    """
    n_entries_changed = 0
    n_fixes_total = 0
    audit_rows: list[dict[str, str]] = []

    for entry in entries:
        sid = str(entry.get("id") or "<unknown>")
        if allowed_keys is not None and sid not in allowed_keys:
            continue

        entry_touched = False
        for field_path, value, setter in _walk_string_fields(entry, []):
            cleaned, n = _fix_doubled_words(value)
            if n:
                audit_rows.append({
                    "id": sid,
                    "field": field_path,
                    "issue": "DOUBLED_WORD",
                    "before": value,
                    "after": cleaned,
                    "count": str(n),
                })
                setter(cleaned)
                entry_touched = True
                n_fixes_total += n

            # Audit-only: lighting tokens (don't auto-rewrite).
            if field_path.startswith("scene_anchor") or field_path.startswith(
                "scene_overrides"
            ):
                tokens = _scan_lighting_tokens(cleaned)
                if tokens:
                    audit_rows.append({
                        "id": sid,
                        "field": field_path,
                        "issue": "LIGHTING_IN_SCENE_FIELD",
                        "before": cleaned,
                        "after": cleaned,  # audit-only
                        "count": str(len(tokens)),
                    })

        if entry_touched:
            n_entries_changed += 1

    return n_entries_changed, n_fixes_total, audit_rows


def _write_audit_csv(rows: list[dict[str, str]]) -> None:
    fieldnames = ["id", "field", "issue", "count", "before", "after"]
    with AUDIT_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing styles.json or the audit CSV.",
    )
    parser.add_argument(
        "--keys",
        nargs="+",
        default=None,
        help="Restrict to a subset of style ids (default: process every style).",
    )
    args = parser.parse_args()

    entries = _load_styles()
    allowed = set(args.keys) if args.keys else None
    n_entries, n_fixes, audit_rows = _process(entries, allowed)

    print(
        f"styles_cleanup: scanned {len(entries)} entries"
        f"{(' filtered to ' + str(len(allowed))) if allowed else ''}, "
        f"touched {n_entries} entries with {n_fixes} doubled-word fixes; "
        f"{sum(1 for r in audit_rows if r['issue'] == 'LIGHTING_IN_SCENE_FIELD')}"
        " lighting-leak rows in the audit (review-only)."
    )

    if args.dry_run:
        print("--dry-run: not writing styles.json or audit.csv")
        # Print first 5 fix rows to stdout for quick eyeball.
        fix_rows = [r for r in audit_rows if r["issue"] == "DOUBLED_WORD"]
        for r in fix_rows[:5]:
            print(f"  - {r['id']}.{r['field']}: {r['before']!r} -> {r['after']!r}")
        return 0

    timestamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = _backup_styles_file(timestamp)
    print(f"styles_cleanup: backup written to {backup_path}")
    _save_styles(entries)
    _write_audit_csv(audit_rows)
    print(f"styles_cleanup: audit written to {AUDIT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

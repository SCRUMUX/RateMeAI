"""One-shot migration: relocate location-shaped strings out of
``context_slots.lighting`` into ``background.overrides_allowed``.

Phase 2 of the v1.27.2 prompt-quality cleanup. The v2 catalog migration
filed location/sub-scene strings (e.g. "Times Square crosswalk with
illuminated billboards", "walk-in closet with full-length mirror") under
``context_slots.lighting``. Because :func:`composition_builder._resolve_lighting`
returns ``""`` when the user did not pass an explicit ``hints.lighting``,
these motif-bearing strings never reach the rendered prompt unless the
user opens «Другой вариант» — defeating their purpose.

This script reuses the keyword regexes from
:mod:`audit_v2_styles` and:

* leaves pure-lighting entries (LIGHTING_KW dominant, no LOCATION_KW)
  alone;
* moves location-shaped entries (LOCATION_KW >= 1 and LIGHTING_KW <= 1
  and LOCATION_KW >= LIGHTING_KW) into ``background.overrides_allowed``
  (deduplicated, order preserved);
* keeps mixed / ambiguous entries in ``context_slots.lighting``
  (conservative — false positives in this script can change rendered
  prompts for every user, so we err on the side of caution).

When at least one entry is moved out of a ``flexible`` style, the
script flips ``background.lock`` to ``"semi"``. The behaviour difference
is intentional and additive: ``flexible`` lets the optional
``scene_override`` REPLACE ``background.base`` entirely, whereas ``semi``
prepends the optional ``sub_location`` ("<sub> in <base>"). For default
generations (no hints) both modes behave identically — we lose
nothing — but the semi mode now lets users surface the relocated
motif via «Другой вариант» without nuking ``background.base``.

Idempotent: re-running on already-migrated data is a no-op. The script
prints a per-style diff summary and writes ``data/styles.json``
atomically (temp + ``os.replace``). ``--dry-run`` skips the write.

Usage::

    python scripts/migrations/2026_04_prompt_quality/split_lighting_and_locations.py
    python scripts/migrations/2026_04_prompt_quality/split_lighting_and_locations.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_v2_styles import classify_lighting_entry  # noqa: E402


def _dedupe_extend(target: list[str], extras: list[str]) -> list[str]:
    """Append ``extras`` to ``target``, preserving order, dropping dupes."""
    seen = {item for item in target}
    out = list(target)
    for item in extras:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def migrate_style(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a per-style migration record (purely informational).

    Mutates ``entry`` in place when changes apply. The return value is
    used only by ``main`` for the summary print.
    """
    sid = entry.get("id", "<unknown>")
    bg = entry.setdefault("background", {})
    cs = entry.setdefault("context_slots", {})

    lights_in = list(cs.get("lighting") or [])
    if not lights_in:
        return {"id": sid, "moved": [], "kept": [], "lock_flipped": False}

    keep: list[str] = []
    move: list[str] = []
    for entry_str in lights_in:
        if not isinstance(entry_str, str):
            keep.append(entry_str)
            continue
        verdict = classify_lighting_entry(entry_str)
        if verdict == "location":
            move.append(entry_str)
        else:
            keep.append(entry_str)

    if not move:
        return {"id": sid, "moved": [], "kept": lights_in, "lock_flipped": False}

    cs["lighting"] = keep
    overrides_in = list(bg.get("overrides_allowed") or [])
    bg["overrides_allowed"] = _dedupe_extend(overrides_in, move)

    lock_flipped = False
    if (bg.get("lock") or "flexible") == "flexible":
        bg["lock"] = "semi"
        lock_flipped = True

    return {"id": sid, "moved": move, "kept": keep, "lock_flipped": lock_flipped}


def _atomic_write(path: Path, payload: str) -> None:
    """Write *payload* to *path* via a temp file + ``os.replace``."""
    tmp_dir = path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=tmp_dir, text=False)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the diff summary; do not modify data/styles.json.",
    )
    args = parser.parse_args(argv)

    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    summaries = [migrate_style(s) for s in styles]

    affected = [s for s in summaries if s["moved"]]
    flipped = [s for s in summaries if s["lock_flipped"]]
    moved_total = sum(len(s["moved"]) for s in affected)

    if not affected:
        print("No-op: every context_slots.lighting entry is already pure-lighting "
              "or already moved.")
        return 0

    print(f"Affected styles: {len(affected)} / {len(styles)}")
    print(f"Total entries relocated: {moved_total}")
    print(f"Locks flipped flexible -> semi: {len(flipped)}")
    print()
    for s in sorted(affected, key=lambda x: -len(x["moved"]))[:30]:
        flip_tag = " (lock flipped)" if s["lock_flipped"] else ""
        print(f"  {s['id']:32s}  -{len(s['moved'])} lights{flip_tag}")
    if len(affected) > 30:
        print(f"  ...and {len(affected) - 30} more.")

    if args.dry_run:
        print()
        print("Dry-run: data/styles.json NOT written.")
        return 0

    payload = json.dumps(styles, indent=2, ensure_ascii=False) + "\n"
    _atomic_write(STYLES_PATH, payload)
    print()
    print(f"Wrote {STYLES_PATH.relative_to(REPO_ROOT)} ({len(payload):,} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

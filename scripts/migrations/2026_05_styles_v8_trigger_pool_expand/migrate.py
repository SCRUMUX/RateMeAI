"""v1.71.2 — trigger_pool expansion across the photo catalogue.

Background
----------

The slot sampler picks one ``trigger_pool`` entry per generation,
and the curated-style invariant in ``tests/test_styles_v3_data.py``
requires ``len(pool) >= 3`` for the top-traffic rows. v7 closed the
hole on the CV / studio cohort (``video_call`` / ``analytics_review``
/ …) by rebuilding ``trigger_pool = [scene_anchor, *scene_overrides]``,
but the rest of the catalogue still ships ``trigger_pool=[scene_anchor]``
on ~40 rows — including the landmark dating styles where this
collapses sampler variety to zero.

This migration generalises the v7 shape to the whole catalogue:

* For every style where ``len(trigger_pool) < 3`` AND
  ``scene_overrides`` is non-empty, rebuild the pool as
  ``[scene_anchor, *unique(scene_overrides)]``. Duplicates against
  the anchor are removed.
* When a style has ``len(trigger_pool) >= 3`` it is left alone —
  curator-tuned pools (paris_eiffel, dubai_burj_khalifa, …) survive
  v8 untouched.
* When ``scene_overrides`` is empty we still rebuild from
  ``[scene_anchor]`` only — but skip the entry from the report so
  the migration log focuses on the rows actually changed.

Idempotent: any field already at the target value is left alone;
re-running the script reports ``applied=0``.

Usage::

    python scripts/migrations/2026_05_styles_v8_trigger_pool_expand/migrate.py --dry-run
    python scripts/migrations/2026_05_styles_v8_trigger_pool_expand/migrate.py
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
LOG_PATH = Path(__file__).resolve().parent / "MIGRATION_LOG.md"

_MIN_POOL_SIZE = 3
_MAX_POOL_SIZE = 8


def _atomic_write(path: Path, payload: str) -> None:
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


def _expand_pool(entry: dict[str, Any]) -> list[str]:
    """Return the (deduplicated) expanded pool, or [] if no change needed."""
    pool = [str(v).strip() for v in (entry.get("trigger_pool") or []) if isinstance(v, str) and str(v).strip()]
    if len(pool) >= _MIN_POOL_SIZE:
        return []  # already rich enough, leave alone

    anchor_raw = entry.get("scene_anchor") or entry.get("base_scene") or ""
    anchor = anchor_raw.strip() if isinstance(anchor_raw, str) else ""
    if not anchor:
        return []  # nothing to seed the pool with

    overrides = entry.get("scene_overrides") or []
    if not isinstance(overrides, list):
        overrides = []

    seen: set[str] = set()
    result: list[str] = []

    def _push(value: str) -> None:
        v = (value or "").strip()
        if not v:
            return
        key = v.lower()
        if key in seen:
            return
        seen.add(key)
        result.append(v)

    _push(anchor)
    for ov in overrides:
        if not isinstance(ov, str):
            continue
        _push(ov)
        if len(result) >= _MAX_POOL_SIZE:
            break

    if len(result) < _MIN_POOL_SIZE:
        return []  # nothing to expand, the anchor + overrides don't reach 3
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    styles = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    if not isinstance(styles, list):
        print("ERROR: data/styles.json is not a JSON array.", file=sys.stderr)
        return 2

    records: list[dict[str, Any]] = []
    changed_any = False
    for entry in styles:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("id") or "")
        mode = str(entry.get("mode") or "")
        new_pool = _expand_pool(entry)
        if not new_pool:
            continue
        before = list(entry.get("trigger_pool") or [])
        if before == new_pool:
            continue
        entry["trigger_pool"] = new_pool
        records.append(
            {"id": sid, "mode": mode, "before": len(before), "after": len(new_pool)}
        )
        changed_any = True

    applied = len(records)
    print(f"v1.71.2 trigger_pool expansion: applied={applied}")

    if not args.dry_run and changed_any:
        payload = json.dumps(styles, ensure_ascii=False, indent=2) + "\n"
        _atomic_write(STYLES_PATH, payload)
        print(f"Wrote {STYLES_PATH}")

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# v1.71.2 trigger_pool expansion",
        "",
        f"- Timestamp: `{timestamp}`",
        f"- Mode: `{'DRY-RUN' if args.dry_run else 'COMMIT'}`",
        f"- Styles touched: {applied}",
        "",
        "## Per-style report",
        "",
        "| id | mode | before | after |",
        "|---|---|---:|---:|",
    ]
    for r in sorted(records, key=lambda x: (x["mode"], x["id"])):
        lines.append(
            f"| `{r['id']}` | {r['mode']} | {r['before']} | {r['after']} |"
        )
    lines.append("")
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Log written to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

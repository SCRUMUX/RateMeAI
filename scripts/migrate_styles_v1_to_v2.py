"""Migrate ``data/styles.json`` entries from the v1 to the v2 schema.

PR3 of the style-schema-v2 migration. Additive: the script never
rewrites a whole entry — it merges a ``schema_version: 2`` block into
each selected entry while keeping the v1 fields intact. A v1 consumer
reading the post-migration JSON continues to see every field it used
to rely on; the v2 loader in :mod:`src.services.style_loader_v2`
recognises the new block and upgrades the style.

Safety rails
------------
- Output goes to ``data/styles.json`` ONLY when ``--write`` is passed;
  default mode is a dry run that emits a diff summary.
- ``--batch`` selects which entries to migrate:
    * ``count:N``         — first N entries that are still on v1,
    * ``mode:<m>``        — every v1 entry in the given mode,
    * ``ids:a,b,c``       — explicit ids (comma-separated),
    * ``glob:<pattern>``  — id prefix glob (``paris_*``, etc.),
    * ``all``             — every remaining v1 entry.
- Already-v2 entries are left untouched.
- ``--backup`` (default on) keeps a timestamped copy under
  ``data/.styles_backup/``.

Rollout
-------
Plan prescribes batches 1 → 5 → 25 → remaining with ≥4 hour canary
between each. This script produces the batches; the canary is
operational and happens outside the script.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import os
import shutil
import sys
from typing import Any


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_JSON = os.path.join(_REPO_ROOT, "data", "styles.json")
_BACKUP_DIR = os.path.join(_REPO_ROOT, "data", ".styles_backup")


def _select_entries(
    entries: list[dict[str, Any]], batch: str
) -> list[dict[str, Any]]:
    """Pick the subset to migrate according to ``--batch``."""
    v1_only = [e for e in entries if int(e.get("schema_version") or 0) < 2]

    if batch == "all":
        return v1_only

    if batch.startswith("count:"):
        n = int(batch.split(":", 1)[1])
        return v1_only[:n]

    if batch.startswith("mode:"):
        mode = batch.split(":", 1)[1]
        return [e for e in v1_only if e.get("mode") == mode]

    if batch.startswith("ids:"):
        ids = set(filter(None, (s.strip() for s in batch.split(":", 1)[1].split(","))))
        return [e for e in v1_only if e.get("id") in ids]

    if batch.startswith("glob:"):
        pat = batch.split(":", 1)[1]
        return [e for e in v1_only if fnmatch.fnmatchcase(str(e.get("id", "")), pat)]

    raise SystemExit(f"Unknown --batch value: {batch!r}")


def _v1_to_v2_block(entry: dict[str, Any]) -> dict[str, Any]:
    """Build the v2-side block for a single v1 entry.

    The v1 fields stay intact; this block is merged on top and leaves
    them alone. Conservative defaults:
    - ``weather.enabled=False`` with ``default_na=True`` — matches the
      v1 baseline (weather previously leaked through the lighting
      whitelist, rarely intended).
    - ``context_slots`` are copied across from ``allowed_variations``.
    - ``quality_identity`` is empty so the default common tail keeps
      shipping for every migrated style.
    """
    v1_allowed = entry.get("allowed_variations") or {}
    if not isinstance(v1_allowed, dict):
        v1_allowed = {"lighting": list(v1_allowed) if isinstance(v1_allowed, list) else []}

    lock_map = {
        "scene_locked": "locked",
        "semi_locked": "semi",
        "flexible": "flexible",
    }
    lock = lock_map.get(str(entry.get("type") or "flexible"), "flexible")

    context_slots: dict[str, list[str]] = {}
    for channel in ("lighting", "angle_placement", "framing", "time_of_day", "season"):
        values = v1_allowed.get(channel) or []
        if isinstance(values, list) and values:
            context_slots[channel] = list(values)

    # Default framing whitelist when the v1 entry did not declare one
    # — matches the production UI options so the UI keeps the same
    # choices post-migration.
    context_slots.setdefault("framing", ["portrait", "half_body", "full_body"])

    clothing_allowed = v1_allowed.get("clothing") or []
    background_overrides = v1_allowed.get("scene") or []

    return {
        "schema_version": 2,
        "trigger": _infer_trigger(entry),
        "background": {
            "base": str(entry.get("base_scene") or ""),
            "lock": lock,
            "overrides_allowed": list(background_overrides),
        },
        "clothing": {
            "default": str(entry.get("default_clothing") or ""),
            "allowed": list(clothing_allowed),
            "gender_neutral": True,
        },
        "weather": {
            "enabled": False,
            "allowed": [],
            "default_na": True,
        },
        "context_slots": context_slots,
        "quality_identity": {
            "base": "",
            "per_model_tail": {},
        },
    }


def _infer_trigger(entry: dict[str, Any]) -> str:
    """Best-effort trigger word extracted from the id / display label.

    Not load-bearing — the ``trigger`` is a convenience anchor used by
    the v2 wrapper when we eventually experiment with model-specific
    openers. Empty string is a valid value.
    """
    raw_id = str(entry.get("id") or "")
    if not raw_id:
        return ""
    first = raw_id.split("_", 1)[0]
    return first if first and first.isalpha() else ""


def _merge_v2(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a NEW dict with the v2 block merged on top of v1 fields."""
    v2_block = _v1_to_v2_block(entry)
    merged = dict(entry)
    merged.update(v2_block)
    return merged


def _backup(src: str) -> str:
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    dst = os.path.join(_BACKUP_DIR, f"styles_{ts}.json")
    shutil.copy2(src, dst)
    return dst


def _summarize(
    original: list[dict[str, Any]], migrated: list[dict[str, Any]]
) -> str:
    v1_count = sum(1 for e in original if int(e.get("schema_version") or 0) < 2)
    v2_count = sum(1 for e in migrated if int(e.get("schema_version") or 0) == 2)
    return (
        f"before: v1={v1_count}, v2={len(original) - v1_count} | "
        f"after:  v1={len(migrated) - v2_count}, v2={v2_count}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch",
        required=True,
        help="Which entries to migrate: count:N | mode:<m> | ids:a,b,c | glob:<p> | all",
    )
    parser.add_argument(
        "--json",
        default=_DEFAULT_JSON,
        help="Path to styles.json (default: data/styles.json)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the migrated file. Without this flag the script runs dry.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the timestamped backup copy.",
    )
    args = parser.parse_args()

    with open(args.json, "r", encoding="utf-8") as f:
        entries: list[dict[str, Any]] = json.load(f)

    selected = _select_entries(entries, args.batch)
    selected_ids = {e["id"] for e in selected}

    migrated_entries: list[dict[str, Any]] = []
    for e in entries:
        if e.get("id") in selected_ids and int(e.get("schema_version") or 0) < 2:
            migrated_entries.append(_merge_v2(e))
        else:
            migrated_entries.append(e)

    print(f"[migrate] batch={args.batch!r} selected {len(selected_ids)} entries")
    for e in selected:
        print(f"  - {e.get('mode')}/{e.get('id')} ({e.get('type', 'flexible')})")
    print(_summarize(entries, migrated_entries))

    if not args.write:
        print("[migrate] dry-run complete. Pass --write to persist.")
        return 0

    if not args.no_backup:
        backup = _backup(args.json)
        print(f"[migrate] backup saved to {backup}")

    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(migrated_entries, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[migrate] wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

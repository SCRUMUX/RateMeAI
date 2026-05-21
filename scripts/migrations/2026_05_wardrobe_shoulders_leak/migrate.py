"""May 2026 audit — strip ``shoulders fully in frame`` from wardrobe.

Background
----------

The phrase ``shoulders fully in frame`` was injected into the
``default_clothing`` / ``clothing.default.*`` strings of 40+ styles
during the May 2026 social / dating catalogue curation pass. It
masquerades as a *fit cue* ("the garment frames the shoulders
nicely") but edit-models read it as a *crop directive* — anchoring
the crop on the shoulders even when ``scene_anchor`` implies a
full-body framing.

The
:data:`src.services.style_lint._WARDROBE_POSE_LEAK_RE` regex was
extended in the same commit to flag the phrase; this migration is
the bulk-cleanup half of the pair — it removes the phrase from
the catalogue so the lint stays clean.

Substitution rules
------------------

* ``, shoulders fully in frame`` (with leading separator) is
  dropped — that is the canonical injection shape.
* Trailing ``, shoulders fully in frame.`` keeps the terminating
  period.
* If the wardrobe string was *only* the phrase (no other content),
  we leave the field untouched and report it in the migration log
  — the curator must repaint manually.

Idempotent. A re-run reports ``applied=0``.

Usage::

    python scripts/migrations/2026_05_wardrobe_shoulders_leak/migrate.py --dry-run
    python scripts/migrations/2026_05_wardrobe_shoulders_leak/migrate.py
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES_PATH = REPO_ROOT / "data" / "styles.json"
LOG_PATH = Path(__file__).resolve().parent / "MIGRATION_LOG.md"


_LEAK_RE = re.compile(
    r"\s*,\s*shoulders\s+fully\s+in\s+frame\b",
    re.IGNORECASE,
)
_LEAK_BARE_RE = re.compile(
    r"\bshoulders\s+fully\s+in\s+frame\b",
    re.IGNORECASE,
)


def _strip_leak(value: str) -> tuple[str, bool]:
    if not isinstance(value, str):
        return value, False
    if "shoulders fully in frame" not in value.lower():
        return value, False
    new_value = _LEAK_RE.sub("", value)
    new_value = _LEAK_BARE_RE.sub("", new_value)
    new_value = re.sub(r"\s+", " ", new_value).strip()
    new_value = re.sub(r"\s+([.,!?;:])", r"\1", new_value)
    new_value = re.sub(r",\s*,", ",", new_value)
    new_value = new_value.rstrip(", ").strip()
    if new_value != value:
        return new_value, True
    return value, False


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


def _process_entry(entry: dict[str, Any]) -> list[str]:
    changed: list[str] = []

    dc = entry.get("default_clothing")
    if isinstance(dc, str):
        new_dc, modified = _strip_leak(dc)
        if modified:
            entry["default_clothing"] = new_dc
            changed.append("default_clothing")

    clothing = entry.get("clothing")
    if isinstance(clothing, dict):
        default_block = clothing.get("default")
        if isinstance(default_block, dict):
            for gender_key in ("male", "female", "neutral"):
                val = default_block.get(gender_key)
                if isinstance(val, str):
                    new_val, modified = _strip_leak(val)
                    if modified:
                        default_block[gender_key] = new_val
                        changed.append(f"clothing.default.{gender_key}")
        override_block = clothing.get("override")
        if isinstance(override_block, dict):
            for season_key, season_val in list(override_block.items()):
                if not isinstance(season_val, dict):
                    continue
                for gender_key in ("male", "female", "neutral"):
                    val = season_val.get(gender_key)
                    if isinstance(val, str):
                        new_val, modified = _strip_leak(val)
                        if modified:
                            season_val[gender_key] = new_val
                            changed.append(
                                f"clothing.override.{season_key}.{gender_key}",
                            )

    return changed


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
        sid = entry.get("id", "")
        fields = _process_entry(entry)
        if fields:
            records.append({"id": sid, "fields": fields})
            changed_any = True

    print(
        f"wardrobe shoulders-leak strip: applied={len(records)} "
        f"styles_total={len(styles)}",
    )

    if not args.dry_run and changed_any:
        payload = json.dumps(styles, ensure_ascii=False, indent=2) + "\n"
        _atomic_write(STYLES_PATH, payload)
        print(f"Wrote {STYLES_PATH}")

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# 2026-05 — Wardrobe ``shoulders fully in frame`` strip",
        "",
        f"- Timestamp: `{timestamp}`",
        f"- Mode: `{'DRY-RUN' if args.dry_run else 'COMMIT'}`",
        f"- Styles touched: {len(records)}",
        "",
        "## Per-style report",
        "",
        "| id | fields touched |",
        "|---|---|",
    ]
    for r in sorted(records, key=lambda x: x["id"]):
        fields = ", ".join(r["fields"]) or "—"
        lines.append(f"| `{r['id']}` | {fields} |")
    lines.append("")
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Log written to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

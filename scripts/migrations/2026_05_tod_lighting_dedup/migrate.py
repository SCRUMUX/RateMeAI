"""May 2026 audit — ``time_of_day`` × ``lighting`` deduplication.

Background
----------

The audit of the slot-sampling pipeline surfaced a semantic overlap
between the ``ambient.time_of_day`` and ``ambient.lighting`` pools.
``"golden hour"`` and ``"blue hour"`` describe a *lighting quality*
(warm low-sun rim or cold post-sunset ambience) and are already
present in the ``lighting`` pool of every outdoor style — but they
were also duplicated into ``time_of_day`` as clock-time markers.
This pushed the slot sampler to draw the same concept on two
independent channels, which the assembler then concatenated into
the wire prompt verbatim ("golden hour, golden hour back-lit") —
the dedup pass downstream of the assembler only catches exact
back-to-back repeats inside a single channel.

Goal of this migration
----------------------

Strip ``"golden hour"`` and ``"blue hour"`` from every
``ambient.time_of_day`` pool in :file:`data/styles.json`, leaving
them only in ``ambient.lighting`` where they semantically belong.
``time_of_day`` keeps clean clock-time markers (``morning``,
``afternoon``, ``evening``, ``night``, ``sunrise``, ``sunset``,
``twilight``, ``midday``, ``early morning``, ``late afternoon``).

After the migration the
:mod:`tests.test_prompts.test_tod_lighting_dedup` pin-test enforces
that no style overlaps ``time_of_day`` × ``lighting`` on these
tokens, so a future admin edit cannot quietly re-introduce the
duplication.

Idempotent: any field already deduped is left alone; a re-run
reports ``applied=0``.

Usage::

    python scripts/migrations/2026_05_tod_lighting_dedup/migrate.py --dry-run
    python scripts/migrations/2026_05_tod_lighting_dedup/migrate.py
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


# Tokens that must NOT appear in ``ambient.time_of_day`` — they are
# lighting-quality descriptors and live in ``ambient.lighting``.
LIGHTING_TOKENS = frozenset({"golden hour", "blue hour"})


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


def _dedup_entry(entry: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return ``(removed_tokens, lighting_added)`` for one style.

    ``removed_tokens`` lists the lighting tokens stripped from
    ``ambient.time_of_day``. ``lighting_added`` lists tokens we had
    to migrate into ``ambient.lighting`` because the style only had
    them in ``time_of_day`` (defensive — production styles already
    carry them in both pools, but the migration must be safe on
    custom catalogues).
    """
    ambient = entry.get("ambient")
    if not isinstance(ambient, dict):
        return [], []

    tod = ambient.get("time_of_day")
    if not isinstance(tod, list):
        return [], []

    removed: list[str] = []
    new_tod: list[str] = []
    for value in tod:
        if isinstance(value, str) and value.strip().lower() in LIGHTING_TOKENS:
            removed.append(value)
            continue
        new_tod.append(value)
    if not removed:
        return [], []

    ambient["time_of_day"] = new_tod

    lighting_added: list[str] = []
    lighting = ambient.get("lighting")
    if isinstance(lighting, list):
        existing_lc = {
            v.strip().lower()
            for v in lighting
            if isinstance(v, str)
        }
        for token in removed:
            tl = token.strip().lower()
            if tl not in existing_lc:
                lighting.append(token)
                existing_lc.add(tl)
                lighting_added.append(token)
    return removed, lighting_added


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
        removed, lighting_added = _dedup_entry(entry)
        if removed:
            records.append(
                {
                    "id": sid,
                    "removed": removed,
                    "lighting_added": lighting_added,
                },
            )
            changed_any = True

    print(
        f"tod-lighting dedup: applied={len(records)} "
        f"styles_total={len(styles)}",
    )

    if not args.dry_run and changed_any:
        payload = json.dumps(styles, ensure_ascii=False, indent=2) + "\n"
        _atomic_write(STYLES_PATH, payload)
        print(f"Wrote {STYLES_PATH}")

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# 2026-05 — `time_of_day` × `lighting` deduplication",
        "",
        f"- Timestamp: `{timestamp}`",
        f"- Mode: `{'DRY-RUN' if args.dry_run else 'COMMIT'}`",
        f"- Styles touched: {len(records)}",
        "",
        "## Per-style report",
        "",
        "| id | removed from `time_of_day` | promoted to `lighting` |",
        "|---|---|---|",
    ]
    for r in sorted(records, key=lambda x: x["id"]):
        rm = ", ".join(f"`{t}`" for t in r["removed"]) or "—"
        added = ", ".join(f"`{t}`" for t in r["lighting_added"]) or "—"
        lines.append(f"| `{r['id']}` | {rm} | {added} |")
    lines.append("")
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Log written to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

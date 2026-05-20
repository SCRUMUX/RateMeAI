"""One-off: split src/version.py changelog comments into CHANGELOG.md.

Phase 4.1 of the Tech Debt Cleanup Roadmap. Removes ~6600 comment lines
from a module that's imported on every app/worker/bot start, leaving
only the docstring + ``APP_VERSION`` literal in ``src/version.py``.
The historical commentary is preserved verbatim in ``CHANGELOG.md`` at
the repo root so ``git log`` / GitHub Releases / on-call review keep a
single source of truth.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_PY = ROOT / "src" / "version.py"
CHANGELOG_MD = ROOT / "CHANGELOG.md"


def main() -> None:
    raw = VERSION_PY.read_text(encoding="utf-8").splitlines()
    # Line 0: docstring. Line 1: blank. Lines 2..N-2: changelog. Last: APP_VERSION.
    docstring = raw[0]
    app_version_line = raw[-1]
    body = raw[2:-1]

    # Walk top-to-bottom and group continuation lines under each header.
    header_re = re.compile(r"^# (\d+\.\d+\.\d+[a-zA-Z0-9._-]*) [\u2014\-] (.*)$")
    entries: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for line in body:
        m = header_re.match(line)
        if m:
            if current is not None:
                entries.append(current)
            version = m.group(1)
            first_line = m.group(2)
            current = (version, [first_line])
        else:
            if current is None:
                if line.strip():
                    raise RuntimeError(f"orphan changelog line: {line!r}")
                continue
            # Strip leading "# " and the visual indentation used to align
            # continuation lines with the header text.
            stripped = re.sub(r"^# ?", "", line)
            stripped = stripped.lstrip()
            current[1].append(stripped)
    if current is not None:
        entries.append(current)

    # Newest entries last in the file → reverse so CHANGELOG.md reads
    # newest-first like every other open-source changelog.
    entries.reverse()

    out_lines: list[str] = []
    out_lines.append("# Changelog")
    out_lines.append("")
    out_lines.append(
        "Version history for RateMeAI. Each release bumps "
        "``src/version.py:APP_VERSION``; the human-readable notes live "
        "here so the module stays a tiny one-liner that doesn't slow "
        "down app/worker/bot cold starts."
    )
    out_lines.append("")
    out_lines.append(
        "Style: newest first, semantic-ish ``major.minor.patch`` versioning. "
        "Pre-v1.14 history is intentionally omitted (predates the FAL "
        "rebuild)."
    )
    out_lines.append("")
    for version, body_lines in entries:
        out_lines.append(f"## {version}")
        out_lines.append("")
        text = " ".join(line.strip() for line in body_lines if line.strip())
        out_lines.append(text)
        out_lines.append("")

    CHANGELOG_MD.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    new_version_py = "\n".join(
        [
            docstring,
            "",
            "# Human-readable release notes live in ``CHANGELOG.md`` at the repo root.",
            "# Keep this module tiny: every app/worker/bot start imports it.",
            app_version_line,
            "",
        ]
    )
    VERSION_PY.write_text(new_version_py, encoding="utf-8")

    print(f"wrote {CHANGELOG_MD.name} with {len(entries)} entries")
    print(f"shrank {VERSION_PY.relative_to(ROOT)} to 5 lines")


if __name__ == "__main__":
    main()

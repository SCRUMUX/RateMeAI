"""Shadow diff: PromptEngine current lambdas vs a direct-builder fix.

Purpose
-------
PR0 of the style-schema-v2 migration plan. Measures exactly how much
promptов would change if we replace the lambdas in
``src.prompts.engine._IMAGE_PROMPT_MAP`` with the real ``ig.build_*_prompt``
functions so ``target_model`` / ``framing`` / ``gender`` propagate end-to-end.

Current behaviour (as of writing): the lambdas have a different callable
identity than the functions referenced in ``_MODE_BUILDERS_WITH_FRAMING``,
so executor arguments ``target_model`` and ``framing`` silently get
dropped on the floor. ``gender`` is also swapped with ``base_description``
inside the dating/cv/social lambdas. This script is read-only: it
never touches ``engine.py`` — it just calls both paths in-process and
records the byte-for-byte diff.

Usage
-----
    python -m scripts.shadow_diff_prompt_engine \\
        --output _diag/prompt_shadow_diff.md

The script writes a Markdown report with:

- count of (mode, style, framing, target_model, variant_id) combos
  that differ;
- per-mode summary table (% of combos differing, avg char delta);
- the first 20 concrete diffs (compact unified diff).

No network calls, no provider invocations — purely string building
via the existing prompt functions.
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from dataclasses import dataclass
from typing import Iterable

# Make ``src`` importable when running the script directly.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.models.enums import AnalysisMode  # noqa: E402
from src.prompts import image_gen as ig  # noqa: E402
from src.prompts.engine import PromptEngine  # noqa: E402


# Framing values that flow through the real pipeline (see executor
# normalization in ``src/orchestrator/executor.py`` around line 476).
FRAMINGS: tuple[str | None, ...] = (None, "portrait", "half_body", "full_body")

# A/B image models currently allowed in production. Anything outside
# this set falls back to the hybrid StyleRouter and does not go through
# PromptEngine for its prompt text.
TARGET_MODELS: tuple[str, ...] = ("gpt_image_2", "nano_banana_2")

GENDERS: tuple[str, ...] = ("male", "female")


_MODE_TO_STR: dict[AnalysisMode, str] = {
    AnalysisMode.DATING: "dating",
    AnalysisMode.CV: "cv",
    AnalysisMode.SOCIAL: "social",
}


@dataclass(frozen=True)
class Combo:
    mode: AnalysisMode
    style: str
    gender: str
    framing: str | None
    target_model: str
    variant_id: str


@dataclass
class DiffRow:
    combo: Combo
    current: str
    fixed: str

    @property
    def differs(self) -> bool:
        return self.current != self.fixed

    @property
    def char_delta(self) -> int:
        return len(self.fixed) - len(self.current)


def iter_combos() -> Iterable[Combo]:
    """Yield every (mode, style, framing, target_model, gender) combo.

    We walk the live ``STYLE_REGISTRY`` rather than a hard-coded style
    list so that any style added to ``data/styles.json`` is picked up
    automatically. Variant coverage is intentionally trimmed to the
    first variant per style (if any) — curated variants live in
    Python-only ``STYLE_VARIANTS`` and most JSON-styles have
    ``variants=()``.
    """
    for mode, mode_str in _MODE_TO_STR.items():
        keys = ig.STYLE_REGISTRY.keys_for_mode(mode_str)
        for key in sorted(keys):
            spec = ig.STYLE_REGISTRY.get(mode_str, key)
            variant_ids: list[str] = [""]
            if spec is not None and getattr(spec, "variants", ()):
                variant_ids.append(spec.variants[0].id)
            for variant_id in variant_ids:
                for gender in GENDERS:
                    for framing in FRAMINGS:
                        for target_model in TARGET_MODELS:
                            yield Combo(
                                mode=mode,
                                style=key,
                                gender=gender,
                                framing=framing,
                                target_model=target_model,
                                variant_id=variant_id,
                            )


def build_current(combo: Combo) -> str:
    """Current production path: via ``PromptEngine.build_image_prompt``.

    Because ``_IMAGE_PROMPT_MAP`` holds lambdas, the executor-level
    ``target_model`` and ``framing`` arguments are silently discarded
    and the ``gender`` position is swapped with ``base_description``.
    """
    engine = PromptEngine()
    return engine.build_image_prompt(
        mode=combo.mode,
        style=combo.style,
        base_description="",
        gender=combo.gender,
        input_hints=None,
        variant_id=combo.variant_id,
        target_model=combo.target_model,
        framing=combo.framing,
    )


def build_fixed(combo: Combo) -> str:
    """Direct-builder path: calls ``ig.build_*_prompt`` with all args.

    Equivalent to the behaviour we'd have if the lambdas in
    ``_IMAGE_PROMPT_MAP`` were replaced with the real callables.
    """
    variant = None
    if combo.variant_id:
        variant = ig.resolve_style_variant(
            _MODE_TO_STR[combo.mode], combo.style, combo.variant_id
        )

    builder = {
        AnalysisMode.DATING: ig.build_dating_prompt,
        AnalysisMode.CV: ig.build_cv_prompt,
        AnalysisMode.SOCIAL: ig.build_social_prompt,
    }[combo.mode]

    return builder(
        style=combo.style,
        base_description="",
        gender=combo.gender,
        input_hints=None,
        variant=variant,
        target_model=combo.target_model,
        framing=combo.framing,
    )


def format_diff(row: DiffRow, context_lines: int = 2) -> str:
    diff = difflib.unified_diff(
        row.current.splitlines(keepends=False),
        row.fixed.splitlines(keepends=False),
        fromfile="current",
        tofile="fixed",
        n=context_lines,
        lineterm="",
    )
    return "\n".join(diff)


def summarize(rows: list[DiffRow]) -> dict[str, dict[str, float]]:
    """Per-mode summary: total, differing, avg char delta."""
    buckets: dict[str, list[DiffRow]] = {}
    for r in rows:
        buckets.setdefault(_MODE_TO_STR[r.combo.mode], []).append(r)

    out: dict[str, dict[str, float]] = {}
    for mode, bucket in buckets.items():
        diffs = [r for r in bucket if r.differs]
        out[mode] = {
            "total": float(len(bucket)),
            "differing": float(len(diffs)),
            "pct_differing": (100.0 * len(diffs) / len(bucket)) if bucket else 0.0,
            "avg_char_delta": (
                sum(r.char_delta for r in diffs) / len(diffs) if diffs else 0.0
            ),
        }
    return out


def render_report(rows: list[DiffRow], *, max_examples: int = 20) -> str:
    lines: list[str] = []
    lines.append("# PromptEngine shadow diff (PR0)")
    lines.append("")
    lines.append(
        "Current path = `PromptEngine.build_image_prompt` via lambdas in "
        "`_IMAGE_PROMPT_MAP`. Fixed path = direct call to "
        "`ig.build_{dating,cv,social}_prompt` with full argument list "
        "(target_model + framing + real gender slot). Read-only."
    )
    lines.append("")
    lines.append(
        f"Total combinations evaluated: **{len(rows)}**. "
        f"Differing: **{sum(1 for r in rows if r.differs)}**."
    )
    lines.append("")

    summary = summarize(rows)
    lines.append("## Per-mode summary")
    lines.append("")
    lines.append("| mode | total | differing | % differing | avg Δchars |")
    lines.append("|------|-------|-----------|-------------|------------|")
    for mode in sorted(summary):
        s = summary[mode]
        lines.append(
            f"| {mode} | {int(s['total'])} | {int(s['differing'])} | "
            f"{s['pct_differing']:.1f}% | {s['avg_char_delta']:+.1f} |"
        )
    lines.append("")

    diffs = [r for r in rows if r.differs]
    lines.append(f"## First {min(max_examples, len(diffs))} concrete diffs")
    lines.append("")
    for r in diffs[:max_examples]:
        lines.append(
            "### "
            f"mode={_MODE_TO_STR[r.combo.mode]} style={r.combo.style} "
            f"gender={r.combo.gender} framing={r.combo.framing!r} "
            f"target_model={r.combo.target_model} "
            f"variant_id={r.combo.variant_id!r}"
        )
        lines.append("")
        lines.append(f"- Δchars = {r.char_delta:+d}")
        lines.append("")
        lines.append("```diff")
        lines.append(format_diff(r))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="_diag/prompt_shadow_diff.md",
        help="Path to the Markdown report (default: _diag/prompt_shadow_diff.md)",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=20,
        help="Number of concrete diff blocks to include in the report.",
    )
    parser.add_argument(
        "--fail-if-differs",
        action="store_true",
        help="Exit with status 1 when ANY combination differs (opt-in).",
    )
    args = parser.parse_args()

    rows: list[DiffRow] = []
    for combo in iter_combos():
        try:
            current = build_current(combo)
            fixed = build_fixed(combo)
        except Exception as exc:
            print(
                f"[shadow-diff] build failed for {combo!r}: {exc}",
                file=sys.stderr,
            )
            continue
        rows.append(DiffRow(combo=combo, current=current, fixed=fixed))

    report = render_report(rows, max_examples=args.max_examples)

    out_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    diffs = sum(1 for r in rows if r.differs)
    print(
        f"[shadow-diff] wrote {out_path}: {len(rows)} combos, "
        f"{diffs} differ ({(100.0 * diffs / len(rows)) if rows else 0:.1f}%)."
    )

    if args.fail_if_differs and diffs:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

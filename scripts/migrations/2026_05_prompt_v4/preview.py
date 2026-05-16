"""Dev-time preview of v4 prompts for visual sanity checks.

Stage 7 of the prompt-pipeline-v4 plan calls for a 10-sample
``paris_eiffel`` walk-through to confirm:

* The 10 prompts are genuinely different (Stage 5 pool expansion).
* Each prompt opens with the v4 preserve-first layout
  (``Place the person …`` → ``IDENTITY_PRESERVE_BLOCK`` → scene → …).
* Each prompt ends with ``PHOTOREAL_BLOCK + PASTED_ON_GUARD``.
* The total length is well under the v1 baseline (Stage 1+2).

The script does NOT call any image-generation provider — it only walks
the prompt pipeline (composition_builder + model_wrappers) so the
output is a deterministic visual diff. Cost: zero.

Usage::

    # 10 samples of paris_eiffel through the v4 pipeline
    python scripts/migrations/2026_05_prompt_v4/preview.py

    # Different style + sample count
    python scripts/migrations/2026_05_prompt_v4/preview.py \\
        --style barcelona_sagrada --samples 5

    # Compare v4 vs v1 layout side by side for one seed
    python scripts/migrations/2026_05_prompt_v4/preview.py \\
        --style paris_eiffel --samples 1 --compare
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def _build_prompt(spec, *, mode: str, style: str, seed: int) -> str:
    from src.prompts import image_gen as ig
    from src.prompts.composition_builder import build_composition_v3
    from src.prompts.model_wrappers import wrap_for_gpt_image_2

    ir = build_composition_v3(
        spec,
        mode=mode,
        change_instruction=ig._dating_social_change_instruction(mode, style),
        input_hints={},
        seed=seed,
        gender="male",
    )
    return wrap_for_gpt_image_2(ir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", default="paris_eiffel")
    parser.add_argument("--mode", default="dating")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Also build the same prompt under prompt_pipeline_v4_enabled=False"
        " so you can diff the v4 vs v1 layout for a single seed.",
    )
    args = parser.parse_args()

    from src.config import settings
    from src.prompts.image_gen import STYLE_REGISTRY
    from src.services.style_loader_v3 import register_v3_styles_from_json

    settings.style_schema_v3_enabled = True  # type: ignore[attr-defined]
    settings.prompt_pipeline_v4_enabled = True  # type: ignore[attr-defined]
    register_v3_styles_from_json()

    spec = STYLE_REGISTRY.get_v3(args.mode, args.style)
    if spec is None:
        print(
            f"v3 spec not registered: {args.mode}/{args.style}. "
            "Run scripts/migrations/2026_05_prompt_v4/migrate.py first.",
            file=sys.stderr,
        )
        return 1

    prompts: list[str] = []
    for s in range(args.samples):
        prompts.append(_build_prompt(spec, mode=args.mode, style=args.style, seed=s))

    print("=" * 80)
    print(f"v4 pipeline preview — style={args.style!r} mode={args.mode!r}")
    print(f"samples={args.samples}")
    print("=" * 80)
    for s, p in enumerate(prompts):
        print(f"\n--- seed={s} ({len(p)} chars) ---")
        print(p)
    unique = len(set(prompts))
    print()
    print(f"unique prompts: {unique}/{len(prompts)}")
    print(f"avg length:     {sum(len(p) for p in prompts) / len(prompts):.0f} chars")

    if args.compare:
        print()
        print("=" * 80)
        print("v1 rollback comparison (prompt_pipeline_v4_enabled = False)")
        print("=" * 80)
        settings.prompt_pipeline_v4_enabled = False  # type: ignore[attr-defined]
        v1_prompt = _build_prompt(spec, mode=args.mode, style=args.style, seed=0)
        print(f"\n--- v1 layout, seed=0 ({len(v1_prompt)} chars) ---")
        print(v1_prompt)
        print()
        v4_len = len(prompts[0])
        if v1_prompt:
            reduction = (len(v1_prompt) - v4_len) / len(v1_prompt) * 100
            print(f"v4 vs v1 length: {v4_len} vs {len(v1_prompt)} ({reduction:+.0f}%)")
        settings.prompt_pipeline_v4_enabled = True  # type: ignore[attr-defined]

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

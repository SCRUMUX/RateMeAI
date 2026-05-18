"""Calibrate CSL heuristic thresholds against the seed dataset.

Run::

    python -m scripts.calibrate_composition_thresholds

The script walks ``data/seed_photos/composition_labels.json``, runs both
the **heuristic classifier** (``classify_heuristic``) and — when
available — the **Pose detector** (``body_landmarks.detect_landmarks``)
on each photo, and prints a confusion matrix plus per-class precision /
recall vs the hand-labeled ground truth. A summary table makes it
obvious where the heuristic disagrees with Pose, which is exactly
where the ``csl_*`` env-var thresholds (in ``src/config.py``) need
adjustment.

Output is plain stdout — no DB / Redis writes, no metric pushes — so
the script is safe to run from a developer laptop. It does NOT
overwrite settings; the calibrator only reports the optimal threshold
band; the operator decides whether to update ``src/config.py``.

CLI flags:

  --photos-root PATH   Override the photo root (defaults to
                       ``data/seed_photos``).
  --labels PATH        Override the labels JSON (defaults to
                       ``data/seed_photos/composition_labels.json``).
  --skip-pose          Skip the Pose comparison even if MediaPipe is
                       available. Useful for "heuristic-only" reports.
  --threshold-sweep    Sweep ``face_closeup_face_ratio`` between 0.20
                       and 0.45 in 0.01 steps and print the heuristic
                       accuracy at each step.

This script is **NOT** wired into CI — calibration is a deliberate,
human-in-the-loop step before raising the ``composition_safety_enabled``
flag in a new market.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

from src.config import settings
from src.services.body_landmarks import (
    classify_from_landmarks,
    detect_landmarks,
)
from src.services.composition_safety import (
    CompositionClass,
    classify_heuristic,
)
from src.services.input_quality import _detect_faces, _mp_available

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHOTOS_ROOT = ROOT / "data" / "seed_photos"
DEFAULT_LABELS = DEFAULT_PHOTOS_ROOT / "composition_labels.json"

# Class order used for confusion matrix rows / columns. Matches the
# fail-open-safe lattice (more permissive = larger index).
_CLASSES: tuple[CompositionClass, ...] = (
    CompositionClass.FACE_CLOSEUP,
    CompositionClass.PORTRAIT,
    CompositionClass.HALF_BODY,
    CompositionClass.FULL_BODY,
    CompositionClass.UNKNOWN,
)


@dataclasses.dataclass(frozen=True)
class _Sample:
    """One row of the calibration dataset."""

    id: str
    path: Path
    ground_truth: CompositionClass


@dataclasses.dataclass
class _Prediction:
    sample_id: str
    ground_truth: CompositionClass
    heuristic: CompositionClass
    pose: CompositionClass | None  # None when MediaPipe unavailable


def _load_labels(labels_path: Path, photos_root: Path) -> list[_Sample]:
    """Read the labels manifest and resolve relative paths against
    ``photos_root``. Missing files are skipped with a warning so the
    operator can keep partial datasets without re-running the whole
    pipeline."""
    with labels_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    out: list[_Sample] = []
    for row in manifest.get("labels", []):
        rel = row.get("relative_path") or ""
        sid = row.get("id") or rel or "<unknown>"
        truth = CompositionClass.parse(row.get("ground_truth"))
        if truth is CompositionClass.UNKNOWN:
            print(f"  [skip] {sid}: invalid ground_truth", file=sys.stderr)
            continue

        path = photos_root / rel
        if not path.exists():
            print(f"  [skip] {sid}: missing file {path}", file=sys.stderr)
            continue
        out.append(_Sample(id=sid, path=path, ground_truth=truth))
    return out


def _run_heuristic_on(image: Image.Image) -> CompositionClass:
    """Apply the production heuristic to a single image.

    Re-uses :func:`src.services.input_quality._detect_faces` so the
    calibration mirrors what the live ``/api/v1/pre-analyze`` endpoint
    does — including the MediaPipe-unavailable fallback that yields
    ``UNKNOWN``."""
    if not _mp_available:
        return CompositionClass.UNKNOWN

    arr = np.array(image.convert("RGB"))
    faces = _detect_faces(arr)
    if not faces:
        return CompositionClass.UNKNOWN
    face = faces[0]
    x1, y1, x2, y2 = (int(c) for c in face.bbox.tolist())
    h, w = arr.shape[:2]
    face_w = max(1, x2 - x1)
    face_h = max(1, y2 - y1)
    face_area_ratio = float(face_w * face_h) / float(max(1, w * h))
    return classify_heuristic(
        face_bbox=(x1, y1, x2, y2),
        face_area_ratio=face_area_ratio,
        width=w,
        height=h,
        face_closeup_face_ratio=settings.csl_face_closeup_face_ratio,
        face_closeup_space_below=settings.csl_face_closeup_space_below,
        portrait_face_ratio=settings.csl_portrait_face_ratio,
        portrait_space_below=settings.csl_portrait_space_below,
        half_body_space_below=settings.csl_half_body_space_below,
    )


def _run_pose_on(image: Image.Image) -> CompositionClass | None:
    """Apply the Pose path. ``None`` means "MediaPipe Pose declined"."""
    arr = np.array(image.convert("RGB"))
    lm = detect_landmarks(arr)
    if lm is None:
        return None
    return classify_from_landmarks(lm)


def _predict_all(samples: Iterable[_Sample], skip_pose: bool) -> list[_Prediction]:
    preds: list[_Prediction] = []
    for s in samples:
        try:
            with Image.open(s.path) as im:
                im.load()
                heuristic = _run_heuristic_on(im)
                pose = None if skip_pose else _run_pose_on(im)
        except Exception as exc:
            print(f"  [skip] {s.id}: failed to read ({exc})", file=sys.stderr)
            continue
        preds.append(
            _Prediction(
                sample_id=s.id,
                ground_truth=s.ground_truth,
                heuristic=heuristic,
                pose=pose,
            )
        )
    return preds


def _confusion(
    preds: list[_Prediction],
    field: str,
) -> dict[tuple[CompositionClass, CompositionClass], int]:
    """Return a (truth, predicted) → count mapping. ``field`` must be
    ``"heuristic"`` or ``"pose"``."""
    out: dict[tuple[CompositionClass, CompositionClass], int] = Counter()
    for p in preds:
        predicted = getattr(p, field)
        if predicted is None:
            continue
        out[(p.ground_truth, predicted)] += 1
    return out


def _print_confusion(
    title: str,
    matrix: dict[tuple[CompositionClass, CompositionClass], int],
) -> None:
    print(f"\n=== {title} ===")
    if not matrix:
        print("  (no samples)")
        return
    header = f"{'truth\\pred':<14}" + "".join(f"{c.value:<14}" for c in _CLASSES)
    print(header)
    for truth in _CLASSES:
        row = f"{truth.value:<14}"
        for pred in _CLASSES:
            row += f"{matrix.get((truth, pred), 0):<14}"
        print(row)


def _print_accuracy(title: str, preds: list[_Prediction], field: str) -> None:
    total = sum(1 for p in preds if getattr(p, field) is not None)
    correct = sum(
        1
        for p in preds
        if getattr(p, field) is not None and getattr(p, field) == p.ground_truth
    )
    pct = (100.0 * correct / total) if total else 0.0
    print(f"\n{title}: {correct}/{total} = {pct:.1f}% accuracy")


def _print_disagreements(preds: list[_Prediction]) -> None:
    rows = [p for p in preds if p.pose is not None and p.heuristic != p.pose]
    if not rows:
        return
    print("\n=== Heuristic vs Pose disagreements ===")
    for p in rows:
        print(
            f"  {p.sample_id:<30} truth={p.ground_truth.value:<13} "
            f"heuristic={p.heuristic.value:<13} pose={p.pose.value}"
        )


def _threshold_sweep(samples: list[_Sample]) -> None:
    """Sweep ``face_closeup_face_ratio`` and print accuracy at each step."""
    print("\n=== Threshold sweep on face_closeup_face_ratio ===")
    print(f"{'threshold':<12}{'accuracy':<12}{'closeup_recall':<18}")
    images: list[tuple[CompositionClass, np.ndarray, tuple, float, int, int]] = []
    for s in samples:
        try:
            with Image.open(s.path) as im:
                im.load()
                arr = np.array(im.convert("RGB"))
        except Exception:
            continue
        faces = _detect_faces(arr) if _mp_available else []
        if not faces:
            continue
        face = faces[0]
        x1, y1, x2, y2 = (int(c) for c in face.bbox.tolist())
        h, w = arr.shape[:2]
        face_w = max(1, x2 - x1)
        face_h = max(1, y2 - y1)
        face_area_ratio = float(face_w * face_h) / float(max(1, w * h))
        images.append(
            (s.ground_truth, arr, (x1, y1, x2, y2), face_area_ratio, w, h)
        )

    for thr in [round(0.20 + 0.01 * i, 2) for i in range(26)]:
        correct = 0
        closeup_truth = 0
        closeup_hit = 0
        for truth, _arr, bbox, ratio, w, h in images:
            pred = classify_heuristic(
                face_bbox=bbox,
                face_area_ratio=ratio,
                width=w,
                height=h,
                face_closeup_face_ratio=thr,
            )
            if pred == truth:
                correct += 1
            if truth is CompositionClass.FACE_CLOSEUP:
                closeup_truth += 1
                if pred is CompositionClass.FACE_CLOSEUP:
                    closeup_hit += 1
        n = len(images) or 1
        rec = (100.0 * closeup_hit / closeup_truth) if closeup_truth else 0.0
        print(
            f"{thr:<12}{(100.0 * correct / n):<12.1f}{rec:<18.1f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--photos-root", type=Path, default=DEFAULT_PHOTOS_ROOT)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--skip-pose", action="store_true")
    parser.add_argument("--threshold-sweep", action="store_true")
    args = parser.parse_args()

    if not args.labels.exists():
        print(f"labels file not found: {args.labels}", file=sys.stderr)
        return 2

    print(f"Loading labels: {args.labels}")
    samples = _load_labels(args.labels, args.photos_root)
    if not samples:
        print(
            "No usable samples found — populate data/seed_photos/ with "
            "real JPEGs matching the manifest and re-run.",
            file=sys.stderr,
        )
        return 1
    print(f"Loaded {len(samples)} labeled samples")

    print(f"MediaPipe Face available: {_mp_available}")

    preds = _predict_all(samples, skip_pose=args.skip_pose)
    print(f"Processed {len(preds)}/{len(samples)} samples")

    h_conf = _confusion(preds, "heuristic")
    _print_confusion("Heuristic confusion matrix", h_conf)
    _print_accuracy("Heuristic", preds, "heuristic")

    if not args.skip_pose:
        p_conf = _confusion(preds, "pose")
        _print_confusion("Pose confusion matrix", p_conf)
        _print_accuracy("Pose", preds, "pose")
        _print_disagreements(preds)

    if args.threshold_sweep:
        _threshold_sweep(samples)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Conditional GFPGAN face pre-restoration (v1.17).

Thin coordinator that decides whether to run GFPGAN on the user's
uploaded photo *before* it is sent to the main FLUX.2 Pro Edit
generation. GFPGAN is a face-only restoration model; running it on
every input would "over-grooming" perfectly good photos (loss of
micro-asymmetry, waxy skin). So we activate it only for clearly
sub-par inputs where the face restoration demonstrably lifts
identity_match downstream.

Activation rules (conservative):

* feature flag ``settings.gfpgan_preclean_enabled`` must be true
* ``InputQualityReport.can_generate`` must be true (i.e. the basic
  input gate accepted the photo — we do not silently "save" rejected
  inputs with GFPGAN, that would hide real issues from the user)
* either ``blur_face < 120`` or ``blur_full < 150`` (Laplacian
  variance thresholds — empirically the point at which FLUX.2's face
  output starts picking up input grain and focus issues)

On success the caller receives the restored bytes. On ANY failure
(FAL transport, NSFW flag, decode error, disabled flag, inputs too
good) the caller receives the ORIGINAL bytes unchanged, plus a
structured log entry. Pre-restoration is optional by design — it
must never take down the main generation path.
"""

from __future__ import annotations

import logging
from typing import Any

from src.config import settings
from src.providers.image_gen.fal_gfpgan import FalGfpganRestorer
from src.services.input_quality import InputQualityReport

logger = logging.getLogger(__name__)

# Activation thresholds. Kept here (not in config) because they are
# part of the algorithm, not operator knobs. Tweaking them without
# code review risks swinging 20–30 % of traffic between "pre-cleaned"
# and "not pre-cleaned" with no metric trail.
BLUR_FACE_THRESHOLD = 120.0
BLUR_FULL_THRESHOLD = 150.0


def should_prerestore(
    report: InputQualityReport | None,
    *,
    feature_enabled: bool | None = None,
) -> bool:
    """Decide whether GFPGAN should run on this input.

    ``feature_enabled=None`` (default) reads ``settings.gfpgan_preclean_enabled``
    at call time. Pass an explicit boolean in unit tests.
    """
    enabled = (
        bool(feature_enabled)
        if feature_enabled is not None
        else bool(getattr(settings, "gfpgan_preclean_enabled", False))
    )
    if not enabled:
        return False
    if report is None:
        return False
    if not getattr(report, "can_generate", False):
        return False

    blur_face = float(getattr(report, "blur_face", -1.0) or -1.0)
    blur_full = float(getattr(report, "blur_full", -1.0) or -1.0)

    face_blurry = 0 <= blur_face < BLUR_FACE_THRESHOLD
    full_blurry = 0 <= blur_full < BLUR_FULL_THRESHOLD
    return face_blurry or full_blurry


async def prerestore_if_needed(
    image_bytes: bytes,
    report: InputQualityReport | None,
    *,
    restorer: FalGfpganRestorer | Any | None = None,
    feature_enabled: bool | None = None,
    face_bbox: tuple[int, int, int, int] | None = None,  # noqa: ARG001 — reserved
) -> tuple[bytes, dict]:
    """Run GFPGAN pre-clean if the input fits the activation rules.

    The optional ``face_bbox`` parameter is reserved for forward
    compatibility with v1.20's single-detect pipeline — the current
    ``fal-ai/gfpgan`` endpoint operates on the full image and does not
    accept a bbox, so we thread the value through without using it.
    When a future GFPGAN mode supports bbox-scoped restoration the
    parameter is already plumbed through the call chain.

    Returns ``(bytes, info)`` where:
    - ``bytes`` is the (possibly restored) image to hand off to the
      main generation step; equals ``image_bytes`` on every skip or
      failure path.
    - ``info`` is a small structured dict suitable for logging /
      result_dict injection:
        * ``applied``: True if we actually ran GFPGAN and kept the
          output.
        * ``skipped_reason``: one of ``"disabled"``, ``"clean_input"``,
          ``"invalid_report"``, ``""`` (on a successful run).
        * ``error``: last error message if the provider failed.
        * ``blur_face`` / ``blur_full``: echoed from the report for
          downstream dashboards.

    The function never raises — any exception is swallowed and folded
    into ``info["error"]``; ``bytes`` falls back to the original.
    """
    info: dict[str, Any] = {
        "applied": False,
        "skipped_reason": "",
        "error": "",
    }
    if report is not None:
        info["blur_face"] = float(getattr(report, "blur_face", -1.0) or -1.0)
        info["blur_full"] = float(getattr(report, "blur_full", -1.0) or -1.0)

    if not image_bytes:
        info["skipped_reason"] = "empty_input"
        return image_bytes, info

    if not should_prerestore(report, feature_enabled=feature_enabled):
        effective_flag = (
            bool(feature_enabled)
            if feature_enabled is not None
            else bool(getattr(settings, "gfpgan_preclean_enabled", False))
        )
        if report is None:
            info["skipped_reason"] = "invalid_report"
        elif not effective_flag:
            info["skipped_reason"] = "disabled"
        elif not getattr(report, "can_generate", False):
            info["skipped_reason"] = "input_rejected"
        else:
            info["skipped_reason"] = "clean_input"
        return image_bytes, info

    if restorer is None:
        api_key = getattr(settings, "fal_api_key", "") or ""
        if not api_key:
            info["skipped_reason"] = "no_api_key"
            return image_bytes, info
        try:
            restorer = FalGfpganRestorer(
                api_key=api_key,
                model=getattr(
                    settings,
                    "gfpgan_model",
                    "fal-ai/gfpgan",
                ),
                api_host=getattr(
                    settings,
                    "fal_api_host",
                    "https://queue.fal.run",
                ),
            )
        except Exception as exc:
            info["error"] = f"restorer_init_failed: {exc}"
            return image_bytes, info

    try:
        restored = await restorer.restore(image_bytes)
    except Exception as exc:
        logger.warning(
            "GFPGAN pre-clean failed, keeping original input (%s)",
            exc,
        )
        info["error"] = str(exc)
        return image_bytes, info

    if not restored or len(restored) < 100:
        info["error"] = "restorer_returned_empty_bytes"
        return image_bytes, info

    info["applied"] = True
    logger.info(
        "GFPGAN pre-clean applied: blur_face=%.1f blur_full=%.1f "
        "input_bytes=%d output_bytes=%d",
        info.get("blur_face", -1.0),
        info.get("blur_full", -1.0),
        len(image_bytes),
        len(restored),
    )
    return restored, info


__all__ = [
    "BLUR_FACE_THRESHOLD",
    "BLUR_FULL_THRESHOLD",
    "should_prerestore",
    "prerestore_if_needed",
]

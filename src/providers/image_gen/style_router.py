"""Style-aware image-gen router (v1.18 hybrid pipeline).

Composite ``ImageGenProvider`` that picks a backend per request based on
``params["generation_mode"]``:

- ``identity_scene``  → PuLID (face crop + prompt → new scene)
- ``scene_preserve``  → Seedream v4 Edit (full photo + prompt → edited scene)
- missing / unknown   → fallback (usually FLUX.2 Pro Edit for safety)

Additionally it:

- Attempts the face crop for ``identity_scene`` requests via
  :func:`src.services.face_crop.crop_face_for_pulid`; if the crop
  fails (no face, tiny face, MediaPipe unavailable), it transparently
  falls back to the ``scene_preserve`` backend so the user still gets
  a usable image.
- Emits metrics for observability:
    * ``ratemeai_image_gen_backend_total{backend, style_mode}``
    * ``ratemeai_pulid_face_crop_failed_total{reason}``
    * ``ratemeai_style_mode_override_total{from_mode, to_mode, reason}``

The router never silently swallows generation errors — each backend
raises as usual and the caller (executor) decides on retry.
"""
from __future__ import annotations

import logging

from src.providers.base import ImageGenProvider
from src.services.face_crop import (
    FaceCropReason,
    crop_face_for_pulid,
)

logger = logging.getLogger(__name__)


class StyleRouter(ImageGenProvider):
    """Delegating image-gen provider that picks the right backend per call.

    Parameters
    ----------
    pulid : ImageGenProvider | None
        PuLID (or compatible) provider used for ``identity_scene`` mode.
        If ``None``, identity_scene requests fall through to ``seedream``.
    seedream : ImageGenProvider | None
        Seedream v4 Edit (or compatible edit) provider used for
        ``scene_preserve`` mode. Also the fallback when the face crop
        fails for an ``identity_scene`` request.
    fallback : ImageGenProvider
        Last-resort provider used when neither of the above is
        available or when ``generation_mode`` is unknown/missing. In
        production this is FLUX.2 Pro Edit (same as v1.17 pipeline).
    """

    def __init__(
        self,
        *,
        pulid: ImageGenProvider | None,
        seedream: ImageGenProvider | None,
        fallback: ImageGenProvider,
    ):
        if fallback is None:
            raise ValueError("StyleRouter requires a non-None fallback provider")
        self._pulid = pulid
        self._seedream = seedream
        self._fallback = fallback

    async def close(self) -> None:
        for p in (self._pulid, self._seedream, self._fallback):
            if p is None:
                continue
            try:
                await p.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _pick_backend(
        self,
        generation_mode: str,
    ) -> tuple[ImageGenProvider, str]:
        """Return ``(provider, backend_label)`` for the given mode.

        ``backend_label`` is one of ``"pulid"``, ``"seedream"``,
        ``"fallback"``. Used in log lines and Prometheus labels.
        """
        if generation_mode == "identity_scene" and self._pulid is not None:
            return self._pulid, "pulid"
        if generation_mode == "scene_preserve" and self._seedream is not None:
            return self._seedream, "seedream"
        # Missing mode or missing dedicated backend → fallback provider.
        return self._fallback, "fallback"

    @staticmethod
    def _record_backend(backend: str, style_mode: str) -> None:
        try:
            from src.metrics import IMAGE_GEN_BACKEND

            IMAGE_GEN_BACKEND.labels(
                backend=backend or "unknown",
                style_mode=style_mode or "unknown",
            ).inc()
        except Exception:
            logger.debug("metrics unavailable", exc_info=True)

    @staticmethod
    def _record_crop_failure(reason: str) -> None:
        try:
            from src.metrics import PULID_FACE_CROP_FAILED

            PULID_FACE_CROP_FAILED.labels(reason=reason or "unknown").inc()
        except Exception:
            logger.debug("metrics unavailable", exc_info=True)

    @staticmethod
    def _record_mode_override(
        from_mode: str, to_mode: str, reason: str,
    ) -> None:
        try:
            from src.metrics import STYLE_MODE_OVERRIDE

            STYLE_MODE_OVERRIDE.labels(
                from_mode=from_mode or "unknown",
                to_mode=to_mode or "unknown",
                reason=reason or "unknown",
            ).inc()
        except Exception:
            logger.debug("metrics unavailable", exc_info=True)

    # ------------------------------------------------------------------
    # ImageGenProvider.generate
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        reference_image: bytes | None = None,
        params: dict | None = None,
    ) -> bytes:
        params = dict(params or {})
        requested_mode = str(
            params.pop("generation_mode", "") or ""
        ).strip() or "identity_scene"

        # ``identity_scene`` needs a cropped face; do it once here so
        # every retry the executor fires reuses the crop.
        effective_mode = requested_mode
        face_bytes: bytes | None = None
        if requested_mode == "identity_scene" and self._pulid is not None:
            # Allow a caller (tests, override) to pre-supply the crop.
            pre_supplied = params.pop("pulid_face_crop", None)
            if (
                isinstance(pre_supplied, (bytes, bytearray))
                and pre_supplied
            ):
                face_bytes = bytes(pre_supplied)
            elif reference_image:
                crop = crop_face_for_pulid(reference_image)
                if crop.image_bytes:
                    face_bytes = crop.image_bytes
                else:
                    self._record_crop_failure(
                        crop.reason or FaceCropReason.NO_FACE,
                    )
                    logger.warning(
                        "StyleRouter: face crop failed reason=%s, "
                        "falling back to scene_preserve",
                        crop.reason,
                    )
                    effective_mode = "scene_preserve"
                    self._record_mode_override(
                        from_mode=requested_mode,
                        to_mode=effective_mode,
                        reason=f"face_crop_{crop.reason or 'failed'}",
                    )
            else:
                # No reference image at all: PuLID cannot run without a
                # face. Fall back to the scene-preserve path too.
                self._record_crop_failure(FaceCropReason.INVALID_IMAGE)
                effective_mode = "scene_preserve"
                self._record_mode_override(
                    from_mode=requested_mode,
                    to_mode=effective_mode,
                    reason="no_reference_image",
                )

        backend, label = self._pick_backend(effective_mode)
        self._record_backend(label, effective_mode)

        if label == "pulid":
            # PuLID takes the face crop as its reference, NOT the full
            # photo. If this is a retry the crop may already be in
            # params; otherwise we've just produced it above.
            gen_ref = face_bytes or reference_image
            logger.info(
                "StyleRouter → PuLID (mode=%s, requested=%s, face_bytes=%d)",
                effective_mode, requested_mode, len(gen_ref or b""),
            )
            return await backend.generate(prompt, gen_ref, params)

        # scene_preserve OR fallback: pass full photo through.
        logger.info(
            "StyleRouter → %s (mode=%s, requested=%s, ref_bytes=%d)",
            label, effective_mode, requested_mode,
            len(reference_image or b""),
        )
        return await backend.generate(prompt, reference_image, params)

    # ------------------------------------------------------------------
    # Introspection (for factory logs + tests)
    # ------------------------------------------------------------------

    def backend_summary(self) -> dict[str, str]:
        """Return human-readable names of the three backends."""
        return {
            "pulid": type(self._pulid).__name__ if self._pulid else "—",
            "seedream": (
                type(self._seedream).__name__ if self._seedream else "—"
            ),
            "fallback": type(self._fallback).__name__,
        }


__all__ = ["StyleRouter"]

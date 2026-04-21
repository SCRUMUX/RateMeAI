"""Версия релиза — увеличивайте при выкладке на сервер и держите app/worker/bot на одной версии."""

# 1.13.3 — Reve: strict per-endpoint parameter whitelist (create/edit/remix)
#          and removal of unsupported wire keys (test_time_scaling,
#          postprocessing, mask_image, mask_region, use_edit, aspect_ratio
#          on edit) that were causing INVALID_PARAMETER_VALUE on every call;
#          prompt template rebuilt around two compact anchors (PRESERVE /
#          QUALITY), single natural paragraph, hard-capped at 1200 chars so
#          the wire body stays well within model limits while keeping
#          identity, anatomy, fine detail and sharp non-blurred backgrounds;
#          aspect-ratio for document styles and optional 2x upscale for
#          large-face crops now done locally via PIL (crop_to_aspect +
#          upscale_lanczos) instead of forwarding to Reve.
APP_VERSION = "1.13.3"

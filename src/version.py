"""Версия релиза — увеличивайте при выкладке на сервер и держите app/worker/bot на одной версии."""

# 1.14.0 — Architecture rebuild: (1) hard cleanup — removed prompt_ab framework,
#          Reve create/remix endpoints, test_time_scaling/aspect_ratio wire
#          params, dead postprocess_for_realism helpers and commented-out
#          adaptive planner hooks; consolidated error/tracing helpers into
#          src/orchestrator/{errors,trace}.py. (2) Reserved-code isolation —
#          moved multi-pass planner, model router and execute_plan into
#          src/orchestrator/advanced/ (inactive, documented in
#          docs/architecture/reserved.md); segmentation.py marked reserved;
#          mock providers relocated to src/providers/_testing/. (3) FLUX.1
#          Kontext [pro] via FAL.ai integrated as the new default image-gen
#          provider for face-preserving edits (dating/cv/social/emoji) —
#          $0.04/image, queue API with sync_mode, retries mirror Reve policy,
#          privacy/consent guard + identity VLM-gate untouched. Auto mode
#          prefers FAL_API_KEY over REVE_API_TOKEN, Reve retained as
#          fallback; Replicate stays dormant and is not auto-selected.
APP_VERSION = "1.14.0"

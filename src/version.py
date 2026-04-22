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
# 1.14.1 — FLUX hotfix: use status_url/response_url from the FAL submit
#          response instead of synthesising them from the model path.
#          For multi-segment apps like ``fal-ai/flux-pro/kontext`` the
#          synthesised ``/requests/{id}/status`` route returns HTTP 405,
#          which broke the post-deploy image-gen-probe smoke test on
#          1.14.0. Fallback URL builder kept as last-resort for legacy
#          apps that omit the fields.
# 1.14.2 — Fix silent identity-gate bypass + explicit risk UX.
#          Root cause: Gemini (via OpenRouter) occasionally wrapped its
#          ``compare_images`` payload in a ``[{...}]`` list, which made
#          ``_parse_json`` return a list, crashed ``_get_quality_metrics``
#          with ``AttributeError: 'list' object has no attribute 'get'``,
#          reset the quality cache to ``{}``, and let ``run_gates`` silently
#          treat identity_match=None as a pass — shipping mismatched photos
#          without any warning. Fixes:
#            * ``_parse_json`` now unwraps single-item dict lists and raises
#              ``ValueError`` for other non-dict shapes.
#            * ``_get_quality_metrics`` uses a ``_check_failed`` sentinel
#              and surfaces ``quality_check_failed=True`` in the report.
#            * Executor converts that flag into ``identity_unverified=True``
#              plus a visible soft warning instead of silent pass.
#            * ``QUALITY_CHECK_PROMPT`` prepended with explicit "Return a
#              SINGLE JSON OBJECT" instruction.
#          UX additions (no auto-retries, no hard blocks — just choice):
#            * Pre-gen: bot detects style × reference mismatch (head-crop
#              selfie + full-body style) and offers "Reupload" / "Continue
#              with risk" before running /analyze.
#            * Post-gen: when ``identity_unverified`` or
#              ``identity_match < soft_threshold``, bot follows up with a
#              "Try another photo" / "Keep as is" keyboard.
#          Prompt fixes: PRESERVE_PHOTO split into face-only and pose+face
#          variants, picked by ``StyleSpec.needs_full_body``; head-crop
#          framing hint injected when a full-body style meets a tight crop.
# 1.14.3 — Positive-framing prompt refresh. Rewrote PRESERVE / QUALITY
#          anchors and all style strings to BFL Kontext best practices:
#          positive framing only (no "no X" / "without X" / "avoid X" /
#          "don't X"), explicit skin tone and head-to-shoulders proportion
#          lock in every prompt, power-words for identity preservation
#          ("while maintaining", "exact same", "same person from the
#          reference photo"). Concrete facial markers ("steady gaze",
#          "raised eyebrow", "half-smile") replace abstract tokens
#          ("energy", "vibe", "aura", "magnetic") that FLUX Kontext cannot
#          parse. Removed the repeated filler "rendered crisply and
#          clearly resolved" from 14 landmark styles. Emoji prompt now
#          opens with "cartoon-styled version of the same person" and
#          locks "exact facial proportions and skin tone". Validator
#          whitelist (``_ALLOWED_NEGATIVES``) reduced to the empty set
#          and the detector widened to catch ``without`` / ``avoid`` /
#          ``don't`` — any future negative framing hard-fails
#          ``validate_style()``.
# 1.15.0 — Style variants for diversity (single-image, no extra cost).
#          Each non-document style (dating, cv, social) now carries 4
#          ``StyleVariant`` entries that rotate scene / lighting / props /
#          camera / clothing accent while keeping ``PRESERVE_PHOTO`` and
#          ``QUALITY_PHOTO`` identity anchors untouched. The former
#          "Улучшить" action is repurposed into "🎲 Другой вариант":
#          callbacks migrated from ``enhance:*`` to ``variant:*`` (old
#          prefix aliased for one release), resolution goes through
#          ``StyleVariationService`` with a Redis-backed 24h anti-repeat
#          memory per (user, mode, style); the pool auto-resets after
#          exhaustion. Document styles skip variant resolution and fall
#          back to a fresh random seed (same compositional discipline).
#          FAL provider defaults ``seed`` to a cryptographically random
#          value when the caller doesn't pin one, giving extra diversity
#          for free. Validator walks every variant with the same
#          positive-framing / banned-phrase rules as the base style, and
#          ``PROMPT_MAX_LEN=1200`` still holds with ≥1 char of headroom
#          in the worst case. Tests: ``test_style_variants.py``,
#          ``test_variation.py``, ``test_variant_button.py`` and an
#          extension to ``test_style_spec_hygiene.py``.
APP_VERSION = "1.15.0"

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
# 1.16.0 — FLUX.2 Pro Edit migration + 2 MP portrait output + UX fixes
#          for "Другой вариант".
#          Image-gen provider hard cutover: ``fal-ai/flux-2-pro/edit``
#          replaces ``fal-ai/flux-pro/kontext`` as the default and as
#          the ``auto`` winner whenever FAL_API_KEY is set. The Kontext
#          provider class (``FalFluxImageGen``) stays in-tree for one
#          release as a single-env-flag rollback target
#          (``IMAGE_GEN_PROVIDER=fal_flux``). FLUX.2 was picked over
#          Kontext after the v1.15.0 quality regression (blurred faces
#          on head-crop × full-body styles): Kontext Pro is
#          hard-capped at ~1 MP with no ``image_size`` control; FLUX.2
#          accepts ``image_size`` (preset enum or custom
#          ``{width, height}``) up to 4 MP.
#          Output resolution is now per-style via a new
#          ``StyleSpec.output_aspect`` field. Default mapping:
#            * document styles (passport / visa / driver_license /
#              photo_3x4 etc.) → ``square_hd`` @ 1024×1024 (1 MP,
#              composition matters, detail secondary — cheaper).
#            * headshot / dating / social / cv non-doc /
#              ``needs_full_body`` → ``portrait_4_3`` @ 1280×1600
#              (≈2 MP, face ≥400–500 px on long side).
#          ``resolve_output_size(spec)`` in ``src/prompts/image_gen.py``
#          emits the concrete ``{width, height}`` passed to the
#          provider in ``extra["image_size"]``; the executor logs the
#          resolved MP per call.
#          Pricing: FLUX.2 Pro Edit bills $0.03 for the first MP +
#          $0.015/MP (round-up) thereafter. New config knobs:
#          ``fal2_model``, ``fal2_output_mp``,
#          ``model_cost_fal_flux2_first_mp``,
#          ``model_cost_fal_flux2_extra_mp``. Prometheus
#          ``ratemeai_fal_calls_total`` now labels by ``model`` to
#          split Kontext vs Flux2; cost observer uses
#          ``estimate_image_gen_cost_usd(provider_name, image_size)``.
#          Prompt hygiene: the contradictory "Framing note — keep
#          close-up crop, do not extend the body" branch for
#          ``needs_full_body`` × head-crop inputs is gone. It was a
#          Kontext-1MP workaround that, with FLUX.2 at 2 MP,
#          demonstrably produced "yoga in blazer" outputs by pinning
#          the reference clothing/framing against the scene. Identity
#          is now carried by ``PRESERVE_PHOTO_FACE_ONLY`` alone.
#          Bot UX: fixed the "Другой вариант" loop that stalled after
#          the first accept of the style × reference risk warning.
#          ``on_confirm_risk`` now records the accept in a per-user
#          Redis set (``ratemeai:risk_accepted:{user_id}``, TTL 30 min,
#          cleared on photo reupload) and
#          ``_maybe_warn_style_reference_mismatch`` short-circuits for
#          any already-accepted (mode, style). ``on_confirm_risk``
#          also propagates the next un-seen ``variant_id`` so the
#          first post-accept run isn't identical to the pre-accept
#          preview.
#          Executor: removed the Reve-legacy ``use_edit`` flag from the
#          ``extra`` payload; it was dead weight for the FAL providers
#          anyway (multi-pass path keeps it unchanged).
#          Tests: ``test_fal_flux2.py`` covers body shape / image_urls
#          list / image_size enum+custom / random seed / 429-5xx-NSFW
#          paths; ``test_style_output_size.py`` pins the per-style
#          output-aspect contract (documents=1 MP, everything else=2 MP);
#          ``test_factory_image_gen.py`` updated for new auto default
#          and explicit fal_flux2 provider branch;
#          ``test_full_body_prompt_adaptation.py`` revised to reflect
#          the framing-note removal.
APP_VERSION = "1.16.0"

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
# 1.17.0 — Identity-stable generation bundle (prompt hardening + VLM
#          retry + conditional GFPGAN pre-clean + Real-ESRGAN final
#          upscale + adaptive image size for full-body × small face).
#          No biometric embeddings collected at any stage; identity
#          preservation remains driven purely by the existing VLM
#          quality gate.
#
#          Prompt hardening (src/prompts/image_gen.py):
#            * PRESERVE_PHOTO / PRESERVE_PHOTO_FACE_ONLY rewritten with
#              stronger identity anchors — "unmistakably recognizable",
#              "identical face (bone structure, eye shape and color,
#              nose, mouth, jawline, ears, hairline, hair color and
#              parting)", "same natural pores and micro-asymmetry".
#            * PRESERVE_PHOTO_FACE_ONLY dropped the "natural full-body
#              pose fitting the scene" phrase that gave FLUX too much
#              licence — now "body pose fitting the new scene", letting
#              the scene description drive the pose without inviting a
#              plastic rewrite of the body.
#            * New IDENTITY_LOCK_SUFFIX appended to every non-document
#              prompt (positive framing only, under 80 chars budget).
#            * Dating/social change instructions now include "exact
#              same facial features, bone structure" in both full-body
#              and close-up branches.
#
#          VLM-driven identity retry (src/orchestrator/executor.py):
#            * When the first FLUX pass returns identity_match below
#              settings.identity_match_threshold (numeric score, not a
#              VLM exception), single_pass re-runs generate() with a
#              fresh random seed and keeps whichever candidate has the
#              higher score.
#            * Capped at settings.identity_retry_max_attempts (default
#              1) additional calls.
#            * quality_check_failed=True still short-circuits the retry
#              — there's no numeric signal to optimise against.
#            * New config knobs: IDENTITY_RETRY_ENABLED (default on) /
#              IDENTITY_RETRY_MAX_ATTEMPTS=1.
#            * New Prometheus metrics: IDENTITY_RETRY_TRIGGERED
#              (Counter, labels: mode, result=[success|still_fail]);
#              GENERATION_ATTEMPTS (Histogram, labels: mode, buckets
#              1–4); FAL_CALLS gets an extra step label `identity_retry`
#              for cost attribution.
#            * cost_breakdown now itemises the retry as a separate
#              step when it actually ran.
#            * Budget impact: +$0.007 average at a 15 % trigger rate.
#
#          Adaptive output size (src/prompts/image_gen.py):
#            * resolve_output_size(spec, face_area_ratio=None) now
#              downgrades full-body styles with a tiny face
#              (face_area_ratio < 0.10) from the default 2 MP portrait
#              to 1 MP square_hd. FLUX.2 at 2 MP on full-body tends to
#              spend its attention budget on scenery; at 1 MP the face
#              gets a larger slice, Real-ESRGAN brings the resolution
#              back. Existing callers (face_area_ratio=None) keep the
#              previous 2 MP behaviour.
#
#          Conditional GFPGAN pre-clean (new providers/service):
#            * New httpx client FalGfpganRestorer (fal-ai/gfpgan),
#              mirroring the FAL queue wire-protocol used by FLUX.2.
#            * New service ``prerestore_if_needed`` activates GFPGAN
#              only when the input is clearly blurry
#              (blur_face < 120 OR blur_full < 150) and
#              input_quality.can_generate is true. Any provider
#              failure folds back to the original bytes — the pre-
#              clean is never load-bearing.
#            * AnalysisPipeline._execute_inner runs the pre-clean
#              between _preprocess and _executor.single_pass.
#            * VLM identity comparison is intentionally performed
#              against the (possibly pre-cleaned) bytes; GFPGAN does
#              not relocate facial landmarks, so identity_match is
#              still a meaningful signal.
#            * Feature flag GFPGAN_PRECLEAN_ENABLED (default OFF on
#              first deploy — flipped on via Railway env post-smoke).
#            * Cost: ~$0.002 per applied case, ~20–30 % activity
#              rate → ≈+$0.0005/image on average.
#
#          Real-ESRGAN final upscale (new provider / executor hook):
#            * New httpx client FalRealEsrganUpscaler
#              (fal-ai/real-esrgan, scale clamped to {2,3,4}).
#            * _maybe_real_esrgan_upscale replaces the sync PIL LANCZOS
#              x2 step when real_esrgan_enabled is on and face_area_ratio
#              >= 0.15. Any provider failure falls back to upscale_lanczos
#              (then to the raw bytes as a last resort).
#            * Feature flag REAL_ESRGAN_ENABLED (default OFF on first
#              deploy).
#            * Cost: ~$0.002 per applied case, ~70 % activity rate →
#              ≈+$0.0014/image on average.
#
#          Config surface (src/config.py, .env.example):
#            * New fields: identity_retry_enabled,
#              identity_retry_max_attempts, gfpgan_preclean_enabled,
#              gfpgan_model, real_esrgan_enabled, real_esrgan_model,
#              model_cost_fal_gfpgan, model_cost_fal_real_esrgan.
#
#          Tests: test_preserve_text (identity-anchor invariants +
#          length budget + IDENTITY_LOCK_SUFFIX); test_identity_retry
#          (five cases covering trigger, no-improvement keep-original,
#          quality_check_failed short-circuit, feature flag off,
#          already-passing score); test_fal_gfpgan / test_fal_esrgan
#          (queue body shape + happy path + error semantics);
#          test_face_prerestore (activation rules + provider-failure
#          fallback).
#
#          Target budget (average): ~$0.053/image — still under the
#          $0.06 soft cap. Worst case (retry + GFPGAN + ESRGAN):
#          ~$0.099 — very rare.
# 1.17.1 — Default-flag flip + adaptive-size safety gate + provider
#          startup log, driven by the "faces still look bad, and why is
#          it still Kontext?" post-1.17.0 field report.
#          * config.py: gfpgan_preclean_enabled and real_esrgan_enabled
#            default to True. The 1.17.0 ship-OFF was intended as a
#            smoke-rollout, but without these the adaptive 1 MP
#            full-body branch (introduced the same release) was
#            producing visibly softer faces than the pre-1.17 2 MP
#            LANCZOS path. Any provider failure still folds back to
#            LANCZOS (or the original bytes), so the defaults remain
#            strictly additive.
#          * prompts/image_gen.resolve_output_size: the adaptive 1 MP
#            square branch for full-body × tiny-face now reads
#            settings.real_esrgan_enabled at call time. When ESRGAN
#            is disabled we stay on 2 MP portrait — without a
#            diffusion-aware upscaler downstream 1024×1024 regresses
#            perceived face quality. Circular-import-safe via a local
#            import guarded by a bare except.
#          * providers/factory.get_image_gen: logs one high-signal
#            INFO line with the selected provider class, model, auto
#            vs explicit reason, and the state of the new feature
#            flags. Answers "is Railway actually running fal_flux2 or
#            fal_flux (Kontext)?" at a grep, rather than a redeploy.
#          * Tests: test_executor_mask._base_settings and
#            test_executor_identity_unverified._base_settings now pin
#            the new flags to False so the legacy LANCZOS /
#            single-attempt assertions keep covering exactly that
#            branch. No other test changes — all 2222 pass.
# 1.18.0 — PuLID-first hybrid pipeline on fal.ai. New default
#          ``IMAGE_GEN_STRATEGY=hybrid``: identity-scene styles
#          (creative dating/social/CV, ~70 % of traffic) route to
#          ``fal-ai/pulid`` (FLUX Lightning + ID adapter, ~$0.006 per
#          call) and run as text-to-image from a face crop, so the
#          model never has to "edit" the reference; scene-preserve
#          styles (documents, "keep my own photo") route to
#          ``fal-ai/bytedance/seedream/v4/edit`` ($0.03) which replaces
#          FLUX.2 Pro Edit for those cases. CodeFormer
#          (``fal-ai/codeformer``) polishes the face on every
#          generation output. Legacy FLUX.2 Pro Edit is kept as the
#          ``fallback`` provider in the StyleRouter and as the full
#          legacy strategy behind ``IMAGE_GEN_STRATEGY=legacy``.
#          Weighted-average cost target: ≈$0.022/image (≤ $0.025 cap).
#
#          New providers (src/providers/image_gen/):
#            * ``fal_pulid.py`` — ``FalPuLIDImageGen`` wrapping
#              ``fal-ai/pulid`` with reference_images + id_scale +
#              pulid_mode + num_inference_steps (4 Lightning default).
#            * ``fal_seedream.py`` — ``FalSeedreamImageGen`` wrapping
#              ``fal-ai/bytedance/seedream/v4/edit`` with image_urls +
#              enhance_prompt_mode + enable_safety_checker (no
#              output_format / safety_tolerance — Seedream rejects
#              those fields).
#            * ``fal_codeformer.py`` — ``FalCodeFormerRestorer`` for
#              face polish (fidelity 0.5, upscale 2x).
#            * ``style_router.py`` — ``StyleRouter`` composite
#              ``ImageGenProvider`` that picks PuLID / Seedream /
#              fallback per request from ``params["generation_mode"]``.
#              Handles face-crop failure by degrading an
#              ``identity_scene`` request to Seedream so the user
#              still receives an image.
#            * ``_fal_queue_base.py`` — ``FalQueueClient`` mixin with
#              the shared submit / poll / fetch / decode + data-URL +
#              error-parser helpers. PuLID / Seedream / CodeFormer all
#              inherit from it; legacy ``fal_flux2.py`` / ``fal_flux.py``
#              / ``fal_gfpgan.py`` / ``fal_esrgan.py`` are left on their
#              own queue logic for stability (no hot-path refactor
#              outside the new code).
#
#          Style typing (src/prompts/style_spec.py,
#          src/prompts/style_variants.py):
#            * ``StyleSpec.generation_mode: Literal[
#                "identity_scene", "scene_preserve"]`` with
#              ``detect_generation_mode`` defaulting every non-document
#              / non-"keep my own photo" style to identity_scene.
#            * Prompt builder splits into two branches:
#              ``identity_scene`` (lean scene description + solo-subject
#              anchor + IDENTITY_SCENE_QUALITY — no PRESERVE_PHOTO /
#              head-to-body clauses because the ID adapter already
#              locks the face and repeating identity tokens starves
#              Lightning's scene budget); ``scene_preserve`` keeps the
#              v1.17 PRESERVE_PHOTO + QUALITY_PHOTO + IDENTITY_LOCK
#              stack unchanged.
#            * ``StyleVariant.concept_signature`` + ``_ROTATION_POOL``
#              + ``_pad_variants`` guarantee ≥6 conceptually distinct
#              variants per style (no more "same concept, different
#              wording" rotations).
#
#          Face crop (src/services/face_crop.py): extracts the primary
#          face, pads 30 %, squares, resizes to 1024×1024 JPEG. Reuses
#          the existing MediaPipe detector from ``input_quality``;
#          failure modes (no face, tiny face, decode error) surface as
#          typed reasons and drive the router's automatic degradation.
#
#          Executor (src/orchestrator/executor.py):
#            * ``single_pass`` threads ``generation_mode`` from
#              ``StyleSpec`` into ``ImageGenProvider.generate(params=...)``
#              so the StyleRouter can route correctly.
#            * ``_apply_codeformer_post`` runs after the main
#              generation (under ``codeformer_enabled``).
#            * Retry loop for ``identity_match < soft_threshold``
#              strengthens PuLID params (``pulid_mode="extreme style"``,
#              ``id_scale=1.0``, ``num_inference_steps=8``) and records
#              ``STYLE_MODE_OVERRIDE``.
#            * ``_estimate_backend_cost`` derives the effective per-call
#              cost from the StyleSpec's generation_mode for StyleRouter
#              deployments (PuLID $0.006 vs Seedream $0.03).
#
#          Config (src/config.py / .env.example): new ``image_gen_strategy``
#          (``hybrid`` default / ``legacy`` / ``pulid_only``), PuLID /
#          Seedream / CodeFormer feature flags + model identifiers +
#          hyperparameters, plus ``model_cost_fal_pulid``,
#          ``model_cost_fal_seedream``, ``model_cost_fal_codeformer_per_mp``.
#
#          Metrics (src/metrics.py): ``IMAGE_GEN_BACKEND``
#          (Counter, labels: backend, style_mode), ``GENERATION_COST_USD``
#          (Histogram, labels: backend), ``PULID_FACE_CROP_FAILED``
#          (Counter, labels: reason), ``STYLE_MODE_OVERRIDE`` (Counter,
#          labels: from_mode, to_mode, reason).
#
#          Rollout: Phase A — hybrid default on dev + canary to
#          ``rate_limit_exempt_usernames`` only. Phase B — monitor
#          GENERATION_COST_USD histogram 48 h, confirm weighted
#          average < $0.025 and no identity_match regression vs 1.17.1.
#          Phase C — flip default strategy to ``hybrid`` for all
#          users; legacy FLUX.2 reachable via
#          ``IMAGE_GEN_STRATEGY=legacy`` for rollback.
#
#          Tests: ``test_fal_pulid.py`` / ``test_fal_seedream.py`` /
#          ``test_fal_codeformer.py`` (body builders, clamping,
#          required-reference errors); ``test_style_router.py``
#          (routing mapping, face-crop fallback, backend summary);
#          ``test_face_crop.py`` (empty / no-face / tiny-face /
#          multi-face / degenerate-bbox cases);
#          ``test_executor_generation_mode.py`` (mode pass-through +
#          backend label propagation); ``test_hybrid_pipeline_integration.py``
#          (end-to-end on mocks for identity_scene + scene_preserve +
#          face-crop-failure degradation); all prompt / positive-framing
#          / length-budget suites updated for the two-branch prompt
#          template. 2270+ tests pass.
# 1.19.0 — PuLID quality fix. v1.18 shipped with Lightning defaults
#          (4 inference steps, CFG 1.2, id_scale 0.8, 30 % crop padding,
#          no negative_prompt, SOLO_SUBJECT anchor in POSITIVE prompt)
#          which together produced duplicate subjects, floating bodies
#          and "wrong face" outputs on anything more complex than a
#          plain studio shot. Fixes:
#
#            * ``fal_pulid.FalPuLIDImageGen`` now ships a concise
#              ``negative_prompt`` covering the v1.18 failure modes
#              (two people / reflection-as-person / morphed face /
#              deformed fingers); override via
#              ``params['negative_prompt']`` or the constructor.
#            * Default quality preset: steps 4→25, guidance 1.2→3.5,
#              id_scale 0.8→1.0. Step-clamp widened 12→50, guidance
#              clamp 1.5→10.0. Pricing moved from $0.006 to $0.015.
#            * ``max_sequence_length: 512`` added to the body — the
#              API default of 128 was truncating our ~1200-char
#              scene+clothing prompts at ~500 chars.
#            * Retry escalation rewritten: ``pulid_mode`` stays on
#              ``fidelity`` (NOT ``extreme style`` — that mode weakens
#              identity per the fal-ai/pulid schema), and the retry
#              instead raises id_scale (1.2), steps (35) and guidance
#              (5.0) via new ``pulid_retry_*`` settings.
#
#          Prompt builder (src/prompts/image_gen.py):
#            * Removed ``SOLO_SUBJECT_ANCHOR`` from the positive
#              identity_scene prompt. Its "one person / single subject
#              / five fingers" tokens were actively reinforcing the
#              duplicate-subject concept under low CFG. Those
#              constraints now live in the PuLID negative_prompt where
#              they actually help.
#            * identity_scene opener rephrased to mention the subject
#              once ("reference subject") instead of twice ("reference
#              person ... the person"), trimming another trigger for
#              duplicate-face generations.
#
#          Face crop (src/services/face_crop.py):
#            * ``_DEFAULT_PADDING_RATIO`` 0.30 → 0.12. The previous
#              padding pulled half the hair, shoulders and background
#              into the crop and diluted PuLID's ID embedding — a
#              direct contributor to the "generic face" drift.
#            * ``_DEFAULT_CROP_SIZE`` 1024 → 768. PuLID resizes to
#              336 px internally; smaller JPEG payload, same identity.
#
#          Output sizing (src/prompts/image_gen.py):
#            * New ``_PULID_PIXEL_SIZE`` table at ~1 MP. identity_scene
#              styles now generate at 896×1152 (portrait), 768×1344
#              (16:9), 1024×1024 (square) instead of the 2 MP table.
#              PuLID is trained on ~1 MP and 2 MP at low step counts
#              was visibly producing composite artefacts. Real-ESRGAN
#              x2 restores delivery resolution downstream.
#            * ``resolve_output_size`` now accepts
#              ``generation_mode=...`` and picks the right table.
#
#          CodeFormer (src/orchestrator/executor.py + config.py):
#            * Skips identity_scene by default
#              (``codeformer_for_identity_scene=false``) — PuLID
#              25-step outputs are sharp enough that CodeFormer was
#              net-damaging on identity.
#            * Skips retries by default (``codeformer_on_retry=false``)
#              — retry is about identity recovery, not sharpness.
#            * Skips tiny faces (``codeformer_min_face_ratio=0.05``)
#              — polish is imperceptible at that scale and costs ~$0.01.
#            * ``codeformer_fidelity`` 0.5 → 0.85 (close-to-input).
#            * ``codeformer_upscale_factor`` 2.0 → 1.0 — no more
#              double-upscale with Real-ESRGAN.
#          Net effect on CodeFormer invoice: ~85 % reduction (most
#          requests now skip it entirely).
#
#          Config rollout:
#            * ``image_gen_strategy`` default flipped to ``hybrid`` in
#              code. The ``legacy`` canary branch stays only as a
#              manual rollback escape hatch. v1.18 had shipped with a
#              ``legacy`` default that defeated the entire hybrid
#              pipeline until an env override was applied manually.
#
#          Expected per-image economics (average):
#            identity_scene (PuLID)    : $0.015 PuLID + $0.002 ESRGAN
#                                        = $0.017
#            scene_preserve (Seedream) : $0.030 + $0.004 CodeFormer
#                                        + $0.002 ESRGAN = $0.036
#            weighted (70/30 split)    : ~$0.023 / image — still
#                                        below the $0.025 ceiling.
# 1.19.1 — HOTFIX: v1.19.0 shipped with ``max_sequence_length: 512``
#          injected into every fal-ai/pulid request, but that field is
#          not in the PuLID input schema (it's a FLUX.1 text-to-image
#          knob). FAL's Pydantic validator rejected it with HTTP 422
#          on every identity_scene generation, breaking the whole
#          hybrid pipeline end-to-end.
#
#          Fix: removed the ``max_sequence_length`` key from the
#          PuLID body builder, the constructor, the factory wiring,
#          the config setting and ``PULID_MAX_SEQUENCE_LENGTH`` from
#          ``.env.example``. Added a regression test
#          (``test_body_does_not_ship_max_sequence_length``) to catch
#          re-introduction. All other v1.19.0 fixes (25-step preset,
#          negative_prompt, 1 MP image_size, tighter face crop,
#          CodeFormer gating, retry escalation) remain unchanged —
#          they are orthogonal to the broken key and were not in
#          effect because every call was failing at validation before
#          ever reaching the sampler.
# 1.19.3 — Harden image-gen post-deploy smoke + sync hybrid env to
#          Railway + make PuLID init fatal in production.
#
#          Background: v1.19.2 unbroke the schema-level HTTP 422 that
#          was bricking prod identity_scene generation, but the CI
#          smoke test still failed — this time because the probe was
#          feeding fal-ai/pulid a solid-colour synthetic JPEG that has
#          no detectable face, so facexlib replied with HTTP 400
#          "no face detected". That is symptomatic of a deeper gap:
#          the smoke test never actually exercised the identity-scene
#          code path on any release.
#
#          src/api/v1/_fixtures/probe_face.py (new): bundles a 256×256
#          JPEG of a StyleGAN face (no real person) as an inline
#          base64 blob. facexlib detects the face reliably; the
#          fixture is ~15 KB and adds no network / storage dependency
#          to the probe.
#
#          src/api/v1/internal.py: ``image_gen_probe`` now accepts a
#          ``mode`` query parameter (``identity_scene`` or
#          ``scene_preserve``, default ``scene_preserve``). The
#          identity_scene branch uses the new face fixture; both
#          branches pass ``params={"generation_mode": mode}`` to
#          ``image_gen.generate`` so StyleRouter deployments route to
#          the correct backend. Docstring now documents the hybrid
#          pipeline instead of the retired Reve provider.
#
#          .github/workflows/ci.yml:
#            * Drops the v1.14-era ``IMAGE_GEN_PROVIDER=fal_flux``
#              pin and the ``REVE_MAX_RETRIES`` sync. Reve has been
#              dead since v1.14; pinning fal_flux silently defeated
#              the v1.18+ hybrid StyleRouter.
#            * Syncs ``IMAGE_GEN_STRATEGY=hybrid`` and the
#              PULID_ENABLED / SEEDREAM_ENABLED / CODEFORMER_ENABLED /
#              REAL_ESRGAN_ENABLED / GFPGAN_PRECLEAN_ENABLED feature
#              flags to app + worker on every deploy so Railway env
#              can never drift behind code expectations.
#            * Missing ``FAL_API_KEY`` is now a hard error rather
#              than a "fallback to Reve" warning.
#            * ``Live provider smoke`` fires TWO image-gen probes
#              (scene_preserve + identity_scene), not one. A PuLID
#              schema regression like v1.19.0/.1 would have blocked
#              the deploy on first push instead of shipping broken.
#
#          .github/workflows/diag-image-gen-probe.yml: header comment
#          updated to reflect the two-mode probe and the hybrid
#          pipeline; removed the stale Reve wording.
#
#          src/providers/factory.py: ``_build_style_router`` now
#          re-raises ``_build_fal_pulid()`` failures when
#          ``is_production`` AND strategy ∈ {hybrid, pulid_only}.
#          Silent degrade-to-Seedream was the reason identity-scene
#          traffic could be completely broken without the service
#          ever noticing.
#
#          Net effect: any future change that breaks the PuLID
#          schema, removes FAL_API_KEY, or drops the hybrid strategy
#          on Railway is now blocked at the "Live provider smoke"
#          step before the release finalises.
# 1.19.2 — HOTFIX: v1.19.0/.1 kept the "quality" PuLID preset
#          (num_inference_steps=25, guidance_scale=3.5, retry 35/5.0)
#          on the false premise that fal-ai/pulid accepts the full
#          FLUX range. It does not — the public schema is strictly
#          Lightning:
#            loc=['body','num_inference_steps']  max=12
#            loc=['body','guidance_scale']       max=1.5
#          so every identity_scene call returned HTTP 422 ("phase=
#          result") and the CI image-gen-probe failed on every deploy.
#
#          Fix: re-tightened the clamps in
#          ``src/providers/image_gen/fal_pulid.py`` — constructor AND
#          ``_build_body`` — to ``steps ≤ 12`` / ``1.0 ≤ guidance ≤
#          1.5``; lowered defaults in ``src/config.py`` to
#          ``pulid_steps=4``, ``pulid_guidance_scale=1.2``,
#          ``pulid_retry_steps=8``, ``pulid_retry_guidance_scale=1.4``
#          (inside the Lightning band yet still escalating on retry);
#          mirrored in ``.env.example``. Cost stays at ~$0.015/image
#          because PuLID bills per GPU-second and these are the same
#          Lightning configs the original model card uses.
#
#          Regression guards: three new tests in
#          ``tests/test_providers/test_fal_pulid.py``
#          (``test_body_clamps_steps_to_lightning_max``,
#          ``test_body_clamps_guidance_to_lightning_max``,
#          ``test_body_defaults_honour_pulid_lightning_schema``) plus
#          a new ``tests/test_config.py``
#          (``test_pulid_defaults_within_lightning_schema``) fail
#          immediately if anyone ever tries to re-widen the defaults
#          again.
# 1.20.0 — Pipeline refactor: honest backend metrics, single face detect,
#          unified FAL queue client, Reve/Replicate outcode removed.
#
#          1) StyleRouter now publishes the real routed backend label
#             via ``contextvars.ContextVar("ratemeai_routed_backend")``.
#             ``_estimate_backend_cost`` and the executor metric
#             sites read that label instead of guessing from
#             ``generation_mode`` — so when the router degrades
#             ``identity_scene → scene_preserve`` (face crop failure),
#             ``ratemeai_generation_cost_usd{backend=...}`` and
#             ``ratemeai_image_gen_backend_total`` reflect the Seedream
#             call that actually ran, not the PuLID one we asked for.
#             ``IMAGE_GEN_BACKEND`` is emitted exclusively by the
#             router now; the executor only publishes it for legacy
#             direct-provider deployments. ``FAL_CALLS`` (both
#             single_pass and identity_retry steps) is keyed on the
#             routed backend so PuLID retries finally show up in
#             Grafana.
#
#          2) ``fal_flux``, ``fal_flux2``, ``fal_gfpgan`` and
#             ``fal_esrgan`` now subclass ``FalQueueClient``; ~600
#             lines of duplicated submit/poll/fetch/decode logic are
#             gone. ``FalAPIError`` / ``FalRateLimitError`` /
#             ``FalContentViolationError`` moved into the base module
#             (re-exported from ``fal_flux`` for one release).
#
#          3) ``src.providers.factory.get_image_gen`` no longer wires
#             Reve or Replicate. Stale ``IMAGE_GEN_PROVIDER=reve|
#             replicate`` values silently remap to ``auto`` with a
#             warning log — ``ReveImageGen`` / ``ReplicateImageGen``
#             modules stay in repo for rollback tests. Metric
#             ``ratemeai_reve_calls_total`` renamed to
#             ``ratemeai_image_gen_calls_total``; ``REVE_CALLS``
#             Python symbol kept as a one-release alias.
#
#          4) Single face-detection per request. ``InputQualityReport``
#             now carries ``face_bbox`` from MediaPipe;
#             ``crop_face_for_pulid`` accepts the bbox and skips the
#             detector when supplied. The executor threads the bbox
#             through ``params["face_bbox"]``; StyleRouter strips and
#             forwards it to the crop step. Cold-path budget: 1 ×
#             MediaPipe per request instead of up to 3.
#
#          5) Comment cleanup — executor, prompts, input_quality,
#             smoke-live / diag-image-gen-probe / diag-recent-errors
#             workflows no longer mention Reve as a live dependency.
#
#          Regressions: new tests
#          ``test_routed_backend_contextvar_reflects_pulid_path``,
#          ``test_routed_backend_contextvar_reflects_fallback_on_crop_failure``,
#          ``test_routed_backend_contextvar_reflects_scene_preserve_path``,
#          ``test_cost_estimation_follows_routed_backend`` in
#          ``tests/test_providers/test_style_router.py``;
#          ``test_face_bbox_arg_skips_mediapipe_call`` and
#          ``test_face_bbox_arg_degenerate_returns_no_face`` in
#          ``tests/test_services/test_face_crop.py``; factory tests
#          updated to cover the legacy-value remap.
APP_VERSION = "1.20.0"

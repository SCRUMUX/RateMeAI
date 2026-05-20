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
# 1.21.0-ab — A/B test: Nano Banana 2 Edit vs GPT Image 2 Edit, additive.
#          The v1.18 hybrid StyleRouter pipeline (PuLID / Seedream /
#          FLUX.2 Pro Edit + CodeFormer / ESRGAN / GFPGAN) is frozen
#          and stays bit-for-bit unchanged. The A/B surface is a
#          strictly additive code path activated per-request when the
#          web UI sends ``image_model`` in the analyze form. Missing
#          / unknown values drop through to the default pipeline. The
#          whole feature turns off via ``AB_TEST_ENABLED=false`` —
#          the endpoint keeps its 202 contract, the UI pills become
#          inert, and no Railway code change is required.
#
#          New providers (src/providers/image_gen/):
#            * ``fal_nano_banana.py`` — ``FalNanoBanana2Edit`` wrapping
#              ``fal-ai/nano-banana-2/edit`` (Google Gemini 3.1 Flash
#              Image). Quality → ``resolution`` enum: low=``0.5K``
#              ($0.06), medium=``1K`` ($0.08, default), high=``2K``
#              ($0.12). Uses ``aspect_ratio="auto"`` so the model infers
#              aspect from the reference portrait — the schema has no
#              ``image_size`` field (only ``resolution`` + ``aspect_ratio``).
#              Single image per call so cost is 1-call = 1-image.
#            * ``fal_gpt_image_2.py`` — ``FalGptImage2Edit`` wrapping
#              ``openai/gpt-image-2/edit`` (OpenAI ChatGPT Images 2.0
#              via fal). Forwards ``quality`` verbatim (low ≈$0.03,
#              medium ≈$0.07, high ≈$0.18). ``image_size`` is a
#              square multiple of 16 per tier (1024 / 1536 / 2048).
#              No ``seed`` field on the GPT Image 2 schema — we never
#              send one.
#          Both inherit from ``_fal_queue_base.FalQueueClient`` for
#          free submit / poll / fetch / decode + retry / NSFW
#          semantics, same as every other FAL provider.
#
#          Structured prompt adapter (src/prompts/ab_prompt.py):
#            * ``build_structured_prompt(mode, style, gender, variant,
#              model)`` auto-assembles the 8-block layout
#              (Subject / Scene / Style / Lighting / Camera / Identity
#              & Realism / Enhancement / Output) from existing
#              ``StyleSpec`` + ``StyleVariant`` fields. No rewrite of
#              the ~130 existing variants.
#            * Model-specific wrappers: GPT Image 2 emits the
#              ``Change: / Preserve: / Constraints:`` triptych
#              recommended by the fal GPT Image 2 prompting guide;
#              Nano Banana 2 emits the structured natural paragraph
#              with an explicit ``Keep facial features exactly the
#              same as the reference image.`` identity anchor.
#            * ``AB_PROMPT_MAX_LEN=1500`` cap — both models handle
#              longer prompts than FLUX Lightning, so the limit is
#              wider than ``PROMPT_MAX_LEN=1200`` of the hybrid path.
#
#          API surface (src/api/v1/analyze.py): ``create_analysis``
#          accepts ``image_model`` + ``image_quality`` Form fields.
#          Whitelist: ``{"nano_banana_2", "gpt_image_2"}`` and
#          ``{"low", "medium", "high"}``; unknown values drop on the
#          floor. Quality fills from ``AB_DEFAULT_QUALITY=medium``
#          when caller omits it. ``Task.context["image_model"]`` is
#          the only thing the executor reads.
#
#          Executor routing (src/orchestrator/executor.py):
#            * ``single_pass`` has one additive ``if ab_active`` branch
#              at the top. When engaged it resolves the per-model
#              provider via ``get_ab_image_gen(model_key)`` (cached
#              per key), builds the prompt through
#              ``build_structured_prompt``, and injects ``quality``
#              into the provider params. Every other step (identity
#              retry, CodeFormer polish, ESRGAN upscale, VLM gate)
#              runs unchanged — the quality gates don't care which
#              generator produced the bytes.
#            * On provider init error (missing FAL key, unknown
#              model) the branch degrades back to the default
#              ``self._image_gen`` and the request never fails
#              upstream.
#            * Cost metrics: ``estimate_ab_image_gen_cost_usd`` +
#              ``ab_backend_label`` emit a composite label
#              ``nano_banana_2:medium`` / ``gpt_image_2:high`` on the
#              existing ``ratemeai_generation_cost_usd`` + ``IMAGE_GEN_CALLS``
#              metrics — no new Prometheus dimensions.
#
#          Frontend (web/src/components/wizard/StepGenerate.tsx,
#          AppContext.tsx, data/ab-models.ts): two pill rows above
#          "Запустить генерацию". Model: [Стандарт] [Nano Banana 2]
#          [GPT Image 2]. Quality appears only when a non-standard
#          model is selected; price hint rendered under the pills.
#          Selection persists in ``localStorage`` (``ailook_ab_model``
#          / ``ailook_ab_quality``); clearing them restores the
#          default path. ``api.analyze`` takes an ``options`` object
#          now so new knobs don't bloat the positional signature.
#
#          Diagnostics: ``/api/v1/internal/diagnostics/image-gen-probe``
#          accepts ``provider={styled_router|nano_banana_2|gpt_image_2}``
#          and ``quality`` query params; CI "Live provider smoke"
#          fires two additional low-quality probes post-deploy
#          (~$0.05 extra per Railway deploy) so a regression in
#          either A/B provider fails the release pipeline the way
#          PuLID regressions already do.
#
#          Tests: ``test_fal_nano_banana.py`` / ``test_fal_gpt_image_2.py``
#          (body shape, quality-tier mapping, error paths, reference
#          requirement); ``test_factory_ab_image_gen.py`` (dispatch +
#          caching + missing-key handling); ``test_ab_prompt.py``
#          (8-block invariants, GPT triptych, Nano Banana identity
#          anchor, length budget, gender sensitivity, unknown-mode
#          fallback); ``test_executor_ab_path.py`` (default path
#          untouched when AB fields absent; feature flag off; AB
#          branch engages correct provider; provider init error
#          falls back); ``test_analyze_ab.py`` (form whitelist,
#          feature flag gating). 2151+ unit tests pass unchanged.
#
#          Rollback recipe: ``AB_TEST_ENABLED=false`` on Railway
#          hides the whole surface server-side; clearing
#          ``localStorage.ailook_ab_model`` restores the default
#          pipeline for an individual user. The frozen hybrid
#          pipeline remains the default — no data migration, no
#          feature cleanup, just a flag flip.
# 1.22.0 — A/B path becomes the default surface. The v1.18 hybrid
#          StyleRouter (PuLID / Seedream / FLUX.2 + CodeFormer /
#          ESRGAN / GFPGAN) still lives in the codebase as a
#          single-env-flag rollback (``AB_TEST_ENABLED=false``),
#          but every UI-visible request now goes to Nano Banana 2
#          or GPT Image 2 with an explicit quality tier. Summary:
#
#          1) Backend defaults (src/config.py):
#             * ``ab_default_model="gpt_image_2"`` (new) and
#               ``ab_default_quality="low"`` (was ``"medium"``).
#               GPT Image 2 @ low is the cheapest reliable option
#               on fal (~$0.02/image at 1024²) and is the new OOTB
#               default for every user. Empty/unknown form values
#               fall through to these constants in
#               ``src/api/v1/analyze.py``.
#
#          2) Nano Banana 2 quality floor raised (src/providers/
#             image_gen/fal_nano_banana.py): the ``low`` tier was
#             producing 512-px outputs (``resolution="0.5K"``),
#             which is below our production minimum. The new
#             quality map is ``low=1K / medium=2K / high=4K``
#             (1024 / 2048 / 4096 px long edge) at fal's official
#             pricing of $0.08 / $0.12 / $0.16 per image. Schema
#             still uses ``resolution`` + ``aspect_ratio="auto"``
#             (no ``image_size`` field).
#
#          3) Frontend (web/src/components/wizard/StepGenerate.tsx,
#             context/AppContext.tsx, lib/api.ts): removed the
#             "Стандарт" pill. The model row now renders only the
#             two A/B pills and the quality row is always visible.
#             Default state on first visit is Model=GPT Image 2 +
#             Quality=Low; localStorage still overrides selection
#             on return visits. ``api.analyze`` unconditionally
#             sends ``image_model`` + ``image_quality`` — any
#             request from the web is guaranteed to land on an A/B
#             provider when the feature flag is on.
#
#          4) The legacy hybrid path is reachable ONLY via the
#             ``AB_TEST_ENABLED=false`` Railway flag (no UI
#             affordance). Executor branch gating, CodeFormer /
#             ESRGAN / GFPGAN orchestration and the StyleRouter
#             class itself are unchanged — this release is a UI /
#             default flip, not a pipeline rewrite.
#
#          Tests: ``test_analyze_ab.py`` updated to expect the
#          new defaults when A/B fields are absent; Nano Banana
#          body tests flipped to 1K / 2K / 4K; frontend build
#          passes with the tightened ``AbImageModel`` type (no
#          ``null``). All 2151+ unit tests still pass.
# 1.22.1 — Hotfix: RU edge was stripping ``image_model`` /
#          ``image_quality`` on the edge→primary hop, so every
#          request that landed on ailookstudio.ru fell through
#          to the legacy StyleRouter despite the user picking
#          Nano Banana 2 / GPT Image 2 in the web UI.
#
#          Fix threads A/B selection through the three missing
#          hops:
#            * ``src/api/v1/analyze.py`` — ``_handle_edge_analysis``
#              now accepts ``image_model`` + ``image_quality`` and
#              forwards them into ``remote_ai.submit_and_wait``
#              (pre-seeded from the already-normalized ctx so the
#              primary can't receive an empty string).
#            * ``src/services/remote_ai.py`` — both
#              ``submit_task`` and ``submit_and_wait`` added
#              ``image_model`` / ``image_quality`` kwargs and the
#              JSON payload carries them alongside the existing
#              policy/market/trace metadata.
#            * ``src/api/v1/internal.py`` —
#              ``RemoteAnalysisRequest`` schema extended with the
#              two new fields and ``process_analysis_remote``
#              mirrors the ``/analyze`` fallback (empty / unknown
#              value → ``settings.ab_default_model`` /
#              ``settings.ab_default_quality``) before
#              ``build_task_context`` so the worker always sees
#              an explicit A/B selection on edge traffic too.
#
#          Legacy primaries keep ignoring the extra JSON fields,
#          so this change is forward/backward compatible across
#          rolling deploys. ``AB_TEST_ENABLED=false`` still fully
#          rolls back to the hybrid StyleRouter.
# 1.23.0 — Face-fidelity adaptation for Nano Banana 2 and GPT Image 2.
#          The v1.22 A/B cutover exposed three regressions in prod:
#          (1) GPT Image 2 at ``quality=high`` routinely produced a
#          result that the edge proxy never delivered because its 180-
#          second poll ceiling was shorter than the primary's end-to-
#          end time (generation + VLM gate). (2) Nano Banana 2 at
#          ``quality=medium`` fired a second FAL call through the
#          legacy PuLID identity-retry — that retry escalated
#          ``pulid_mode`` / ``id_scale`` which NB2 silently ignores,
#          doubling cost and latency for no gain. (3) NB2 outputs kept
#          drifting on the face even though it's nominally an
#          identity-preserving edit model, because the executor still
#          piped every A/B output through CodeFormer (general face
#          restoration), Real-ESRGAN (x2 upscale that added artefacts
#          on an already-4K image) and GFPGAN preclean (which rewrote
#          the reference face *before* the edit model ever saw it).
#
#          v1.23 is a targeted pipeline + prompt adaptation that keeps
#          the legacy StyleRouter code path bit-for-bit untouched
#          (still available via ``AB_TEST_ENABLED=false``) and only
#          changes behaviour when the A/B branch is active.
#
#          1) Face-fidelity pipeline (src/orchestrator/pipeline.py,
#             src/orchestrator/executor.py):
#               * GFPGAN preclean is SKIPPED on the A/B path — NB2 /
#                 GPT-2 both work better when they see the user's
#                 unaltered reference.
#               * CodeFormer post and Real-ESRGAN upscale are SKIPPED
#                 on the A/B path. NB2 emits clean 1K–4K output and
#                 GPT-2 up to 2560 at native resolution; the legacy
#                 polish stages only re-render features and add JPEG
#                 artefacts.
#               * Identity-retry loop is gated behind the new
#                 ``ab_identity_retry_enabled`` flag (defaults to
#                 ``False``). The legacy retry shipped PuLID-only
#                 parameters that NB2 / GPT-2 strip, so the second
#                 call cost money without fixing identity. Legacy
#                 StyleRouter path keeps its own
#                 ``identity_retry_enabled`` flag — they're
#                 independent.
#               * The ``generation_mode`` key (PuLID vs Seedream
#                 semantics) is stripped from the A/B provider
#                 params for clean observability.
#
#          2) GPT Image 2 — standard sizes
#             (src/providers/image_gen/fal_gpt_image_2.py):
#               * Replaced the forced non-standard squares (1024² /
#                 1536² / 2048²) with OpenAI's officially-supported
#                 sizes: 1024×1024, 1024×1536 portrait, 1536×1024
#                 landscape, 2560×1440 2K. The 2048² combination was
#                 never on the supported list and had unstable
#                 latency on ``high`` — a direct contributor to the
#                 edge-timeout regression.
#               * Provider now honours an explicit ``image_size``
#                 from the executor (StyleSpec-aware) and snaps any
#                 off-list caller-supplied size onto the nearest
#                 whitelist entry.
#
#          3) Nano Banana 2 — Gemini reasoning lock
#             (src/providers/image_gen/fal_nano_banana.py):
#               * ``thinking_level="high"`` is sent on the medium /
#                 high quality tiers. The reasoning-guided edit is
#                 the single biggest lever in the fal.ai / Google
#                 prompting guides for holding the reference face
#                 together at higher resolutions. ``low`` keeps fast
#                 non-reasoning mode for speed.
#               * ``safety_tolerance="4"`` and
#                 ``limit_generations=True`` are now pinned
#                 explicitly so payloads are reproducible for
#                 metrics and the model never silently emits extra
#                 intermediate frames.
#               * Executor derives a valid ``aspect_ratio`` enum
#                 from the StyleSpec output size (``_aspect_ratio_
#                 enum_for_size``) and forwards it, so NB2 stops
#                 reframing 4K outputs into square and cropping the
#                 head out.
#
#          4) Prompts — model-specific rewrites
#             (src/prompts/ab_prompt.py):
#               * NB2 wrapper rewritten from the 8-block stack to a
#                 concise 3-paragraph prose prompt (identity anchor /
#                 change description / explicit change-vs-preserve
#                 split). Gemini 3.1 Flash Image deprioritises
#                 labelled stacks — the prose form is what Google's
#                 and fal.ai's own guides recommend. Anchor phrase
#                 "Do not alter the person's face in any way." is
#                 now first, followed by the scene description and
#                 closed with a preserve inventory. Anti-plastic-
#                 skin clause (``NANO_BANANA_SKIN_CLAUSE``) appended
#                 to keep pores / micro-imperfections.
#               * GPT-2 wrapper extends the Preserve/Constraints
#                 triptych with explicit anchors per the OpenAI
#                 "Generate images with high input fidelity"
#                 cookbook: eye shape, nose bridge, jawline,
#                 hairline, expression, framing in ``GPT_PRESERVE_
#                 BASE``; "no face change, no airbrushing, no
#                 plastic skin" in ``GPT_CONSTRAINTS``.
#               * ``ab_prompt_max_len`` bumped from 1500 → 2000 to
#                 keep the longer Preserve/Constraints intact on
#                 styles with rich scene descriptions.
#
#          5) Edge polling timeout (src/services/remote_ai.py):
#               * ``_POLL_MAX_SECONDS`` 180 → 300. Covers NB2
#                 thinking-high and GPT-2 high end-to-end.
#               * ``httpx.AsyncClient`` read timeout 120s → 240s.
#               * Frontend polling is already 300s so no web change
#                 needed.
#
#          Config / env:
#               * New ``ab_identity_retry_enabled`` (default
#                 ``False``) + ``AB_IDENTITY_RETRY_ENABLED=false``
#                 in ``.env.example``.
#               * ``ab_prompt_max_len`` default 1500 → 2000.
#
#          Expected effect:
#               * NB2 faces stop drifting — no more CodeFormer re-
#                 render, no GFPGAN preclean, thinking-high lock on
#                 medium/high.
#               * GPT-2 high stops timing out on the edge; uses
#                 standard sizes so latency is predictable.
#               * Cost per A/B request drops ~1.5-2× on medium/high
#                 (one provider call instead of a retry + a Real-
#                 ESRGAN upscale + a CodeFormer polish).
#               * Legacy StyleRouter path: completely unchanged.
#
#          Tests: ``test_fal_gpt_image_2`` rewritten for the size
#          whitelist + sanitizer; ``test_fal_nano_banana`` adds
#          thinking_level / safety_tolerance / limit_generations
#          assertions; ``test_ab_prompt`` rewritten for the new
#          prose NB2 form + extended GPT-2 anchors;
#          ``test_executor_ab_path`` adds two guard cases
#          (CodeFormer/Real-ESRGAN skipped; identity-retry
#          skipped on low identity_match). All 2376 tests pass.
#
# v1.24.0 — real-fix release: the "AttributeError: 'dict' object has
#          no attribute 'append'" shown in the production toast was the
#          root cause of NB2 / GPT-2 generations failing, not the
#          timeout / invalid_parameter theory from v1.23. Fixed here
#          along with a batch of UX gripes the user flagged (wizard
#          snap-back, top-up button, error-state CTAs, paid CI smoke,
#          payment re-auth) and a simplification of the NB2 quality
#          tier ladder.
#
#          1) Pipeline A/B trace bug (src/orchestrator/pipeline.py):
#               * ``if ab_active:`` branch was writing
#                 ``trace.setdefault("steps", []).append({...})``. But
#                 ``trace["steps"]`` is initialised as ``{}`` (a dict
#                 keyed by step name — see ``_trace_step`` /
#                 ``orchestrator/trace.py``), so ``setdefault`` returned
#                 the existing dict and ``.append`` raised on every A/B
#                 call. Switched to writing the face_prerestore entry
#                 to the dict directly, matching the pattern used
#                 everywhere else in the file.
#               * Regression test: ``test_ab_path_records_face_
#                 prerestore_without_crashing`` in
#                 ``tests/test_orchestrator/test_pipeline.py`` — runs
#                 the pipeline through the A/B path and asserts
#                 ``trace["steps"]`` stays a dict with the expected
#                 ``face_prerestore`` entry.
#
#          2) NB2 quality tiers dropped 4K
#             (src/providers/image_gen/fal_nano_banana.py):
#               * ``_QUALITY_TO_RESOLUTION`` low=1K / medium=2K /
#                 high=2K (was 4K). ``_thinking_level_for_quality``
#                 returns "high" only for ``high`` tier (medium now
#                 runs fast mode). Progression is now cheap/fast
#                 (1K) → more detail (2K) → more care for the face
#                 (2K + reasoning).
#               * 4K added latency + cost with no perceptible realism
#                 gain in testing; ``thinking_level=high`` at 2K is
#                 the single biggest identity-preservation lever the
#                 NB2 endpoint exposes.
#               * Pricing / UI labels updated accordingly
#                 (``config.py`` high cost 0.16 → 0.12,
#                 ``web/src/data/ab-models.ts`` labels and tier hints).
#
#          3) CI post-deploy provider smoke removed
#             (.github/workflows/ci.yml):
#               * The single "Live provider smoke" step burned
#                 ~$0.15/deploy on 4 FAL image-gen probes + 1
#                 synthetic OpenRouter probe, and its ``provider-
#                 probe`` subcheck hit OpenRouter vision on every
#                 push — the first v1.24.0 deploy went red because
#                 ``vision_plain`` returned a transient 504 three
#                 times in a row even though the actual deploy was
#                 healthy.
#               * The block was fully extracted. Deploy responsibility
#                 ends at ``/health`` (confirms our container serves
#                 the right version). External-provider liveness is
#                 covered by the dedicated ``smoke-live.yml`` hourly
#                 workflow, and ad-hoc verification uses
#                 ``diag-provider-probe.yml`` /
#                 ``diag-synthetic-analyze.yml`` /
#                 ``diag-image-gen-probe.yml`` (workflow_dispatch).
#                 One responsibility per workflow; transient upstream
#                 errors no longer block deploys.
#
#          4) Frontend UX fixes (web/):
#               * NavBar "Пополнить баланс" — swapped
#                 ``<Link to="/#тарифы">`` (which react-router-dom
#                 does not scroll to) for a button that navigates to
#                 ``/`` then scrolls the #тарифы section into view —
#                 same pattern already used in StepGenerate's
#                 ``goToPricing``.
#               * AppPage wizard — the useEffect that force-set
#                 ``currentStep = 'generate'`` on any generation
#                 state (isGenerating / currentTask /
#                 generatedImageUrl / pending / error) now fires only
#                 on the false→true transition, so the user can
#                 navigate back to previous steps once a task starts.
#               * StepGenerate failure panel — three CTAs instead of a
#                 single retry button: "Попробовать ещё раз",
#                 "Другое фото", and (when ``noCreditsError`` is set
#                 or the message matches кредит/баланс/no_credits)
#                 "Пополнить баланс". Error text is surfaced above the
#                 buttons instead of relying on the global toast.
#               * PaymentSuccess — detects missing localStorage token
#                 on mount (cross-origin / Telegram-webview case) and
#                 offers one-tap Telegram re-auth via ``startOAuth``
#                 instead of silently bouncing the user to /app.
#
#          Config / env:
#               * ``MODEL_COST_FAL_NANO_BANANA_HIGH`` default 0.16 →
#                 0.12 (2K pricing, matches medium).
#
#          Tests: All 2377 pytest tests pass (one new regression test
#          in ``test_pipeline.py`` over the 2376 baseline). NB2 tests
#          updated for the new tier map; ``test_executor_ab_path``
#          cost expectation updated for the new ``high`` price.
#          TypeScript check (``tsc --noEmit``) clean.
#
# v1.24.2 — fal pipeline rescue: fixes the ``http=404 phase=status
#          Path /requests/{id}/status not found`` the user reported
#          after the v1.24 A/B roll-out, restores real A/B routing
#          that had silently been forcing every request through
#          GPT-2, makes fallback symmetric so Nano Banana-first
#          requests get retried on GPT-2 (not just the other way
#          around), and surfaces image-gen errors in the TG bot so
#          failures stop looking like bare text replies.
#
#          Root cause — combination of two interlocking bugs:
#
#          1) ``src/providers/image_gen/_fal_queue_base.py``:
#             ``_fallback_status_url`` / ``_fallback_result_url``
#             were doing ``"/".join(parts[:2])``, which silently
#             truncated ``fal-ai/nano-banana-2/edit`` to
#             ``fal-ai/nano-banana-2`` (and any other 3+ segment
#             app: ``openai/gpt-image-2/edit``,
#             ``fal-ai/bytedance/seedream/v4/edit``, ...). When
#             ``FAL_API_HOST`` was not explicitly set to
#             ``queue.fal.run`` (see #2), FAL's submit response
#             arrived *without* ``status_url`` / ``response_url``,
#             forcing us into this synthesiser — which then pointed
#             poll GETs at a non-existent prefix and got 404 on
#             every single request.
#             Fix: rebuild both URLs from the FULL ``self._model``
#             so every segment round-trips. Added a one-off
#             ``logger.warning`` with the actual URL on 404 inside
#             ``_poll_until_done`` so future regressions are a
#             ``grep`` away instead of a two-hour incident.
#
#          2) ``src/config.py``: default ``fal_api_host`` was
#             ``https://fal.run`` (the *sync* endpoint). Any deploy
#             where the env var wasn't explicitly set fell back to
#             sync, whose submit response does not carry
#             ``status_url`` / ``response_url`` — that's what
#             pushed us into the broken synthesiser above. Switched
#             default to ``https://queue.fal.run`` to match
#             ``.env.example`` and the test fixtures, which were
#             already using it.
#
#          3) ``src/orchestrator/executor.py``: the ``ab_active``
#             branch put only ``quality`` and ``aspect_ratio`` in
#             the provider ``extra`` dict — never
#             ``image_model``. ``UnifiedImageGenProvider._pick_backend``
#             reads ``params["image_model"]`` to route; without
#             that key it deterministically returned ``model_a``
#             (GPT-2). So every "Nano Banana 2" request from the
#             web client actually went to GPT-2 first and only
#             reached NB2 via the catch-exception fallback — two
#             FAL calls per request, wrong model answering the
#             happy path, correct model answering the 404. Now the
#             key is forwarded and routing matches user intent on
#             the first hop.
#
#          4) ``src/providers/image_gen/unified.py``: the catch
#             branch only handled ``provider is self._model_a``, so
#             once #3 was fixed and Nano Banana 2 could actually
#             be the primary provider, its failures would bubble up
#             unhandled (GPT-2 was never tried). Rewrote the fallback
#             to pick the *other* model regardless of which side
#             the user chose; specialised providers (PuLID /
#             Seedream / Rave) keep their legacy "no A/B backstop"
#             behaviour and still re-raise.
#
#          5) ``src/bot/handlers/results.py``: when generation
#             failed, the TG bot silently dropped the image and
#             sent only analysis text, so users couldn't tell
#             whether the service lost their photo, they ran out
#             of credits, or the model choked. New
#             ``_no_image_reason_line`` helper mirrors the web
#             client (``web/src/context/AppContext.tsx``): reads
#             ``result["no_image_reason"]`` +
#             ``result["image_gen_error_message"]`` and appends a
#             one-line user-facing explanation to both
#             ``_send_enhanced`` and ``_send_emoji`` outputs
#             (covers ``no_credits`` / ``generation_error`` /
#             ``upgrade_required`` / ``not_applicable``). The line
#             is only added when no generated image is actually
#             attached, so successful paths stay identical.
#
#          6) ``src/bot/handlers/mode_select.py`` (line 711): the
#             bot's POST to ``/api/v1/analyze`` had a 30 s
#             timeout, but real A/B generation can burn ~45-90 s
#             (FAL queue wait + NB2/GPT-2 inference + our post-
#             pipeline). Healthy runs were being cut off at the
#             HTTP layer, the bot gave up, and the user saw the
#             status bubble freeze. Raised to 120 s (matches
#             ``fal_request_timeout``). Also left a TODO next to
#             ``form_data`` for wiring ``image_model`` /
#             ``image_quality`` from any future bot-side A/B
#             picker — today the server falls back to
#             ``ab_default_model`` which is correct but ignores
#             user preference.
#
#          Tests (all new or refreshed, every suite green):
#               * ``tests/test_providers/test_fal_queue_base.py``
#                 (new) — 7 URL-builder tests covering 2/3/5-segment
#                 appIds including explicit ``/edit`` subpath
#                 preservation and host/model trailing-slash
#                 normalisation.
#               * ``tests/test_providers/test_fal_nano_banana.py``,
#                 ``test_fal_gpt_image_2.py`` — added "submit
#                 without ``status_url``" regression: fake FAL
#                 returns bare ``request_id``, the poll GETs must
#                 land on the FULL appId including ``/edit``.
#               * ``tests/test_providers/test_unified_provider.py``
#                 — added explicit GPT-2 routing, symmetric B→A
#                 fallback, param preservation across fallback,
#                 routed-backend context var updates after
#                 fallback, and a PuLID-does-not-backstop guard.
#               * ``tests/test_orchestrator/test_executor_ab_routing.py``
#                 (new) — ``ab_active`` propagates
#                 ``image_model=nano_banana_2`` and
#                 ``image_model=gpt_image_2``; ``ab_active=False``
#                 leaves ``params`` untouched (hybrid path
#                 unchanged).
#
#          Risk / rollback:
#               * #2 changes the default host. Railway / prod
#                 already pin ``FAL_API_HOST=https://queue.fal.run``
#                 in ``.env`` so live traffic is untouched; the
#                 only ENV that shifts is a fresh deploy with no
#                 override, which previously 404'd anyway.
#               * #3 flips routing from "always GPT-2 on the happy
#                 path" to "whatever the user picked". Cost
#                 accounting and backend labels already follow
#                 ``ab_image_model`` so Grafana / billing lines
#                 move automatically.
#               * #4 is additive — existing A→B tests keep passing;
#                 the new B→A path only fires on errors.
# 1.25.0 — Prompt-audit pass + quality lock.
#          Goal: stabilise A/B generation quality by removing prompt
#          contradictions without rearchitecting the pipeline. Changes:
#            • PRESERVE_PHOTO / PRESERVE_PHOTO_FACE_ONLY rewritten —
#              dropped "identical", "original pose", "body proportions",
#              and the five-fingers clause. Identity clause is now a
#              single positive block (features + bone structure +
#              eye shape/color + skin tone with pores + hair + face
#              shape). Full-body variant adds "Body pose naturally fits
#              the new scene" so we stop telling FLUX to keep the pose
#              it is also being told to change.
#            • QUALITY_PHOTO / IDENTITY_SCENE_QUALITY — "sharp from
#              subject to background" retired in favour of "natural
#              depth of field: subject sharp, background slightly
#              soft" (matches the 50mm-lens look the styles target).
#            • New CAMERA_PHOTO (50mm / eye-level / rectilinear /
#              undistorted) and ANATOMY_PHOTO (head-to-body ratio +
#              natural proportions) anchors. All positive-framed so
#              they pass ``_has_disallowed_negative`` in style_spec.
#            • ``_build_mode_prompt`` A/B tail unified — gpt_image_2
#              and nano_banana_2 now share the same
#              PRESERVE → QUALITY → CAMERA → ANATOMY sequence instead
#              of two divergent blocks + IDENTITY_LOCK_SUFFIX echo.
#            • ``_dating_social_change_instruction`` and
#              ``build_cv_prompt`` (non-doc path) trimmed to
#              background/clothing/pose composition — the identity
#              repeats now live once, inside PRESERVE.
#            • Quality lock: API (``/analyze``) coerces
#              ``image_quality`` to ``"medium"`` regardless of input;
#              web client fixes ``imageQuality`` state to
#              ``"medium"`` and hides the pill selector in
#              StepGenerate. Two renders × one optimal quality tier.
#            • Tests updated: test_preserve_text,
#              test_full_body_prompt_adaptation (distinct-strings
#              assertion), test_image_gen_prompt (sharp-scene
#              assertion), test_positive_framing
#              (change_instruction focuses on composition),
#              test_analyze_ab (expects medium on all inputs).
#
#          Risk / rollback: prompt-level only; no provider-contract
#          changes, no cost change (still 2 renders, medium tier).
#          Rollback = revert this commit.
#
# 1.25.1 — Scene lighting integration anchor.
#          Adds ``LIGHT_INTEGRATION_PHOTO`` — "Scene lighting
#          integration: the scene's ambient light and color temperature
#          naturally illuminate the subject's face, hair and clothing,
#          with highlights, shadows and color cast consistent with the
#          background." Inserted in the A/B tail of
#          ``_build_mode_prompt`` between QUALITY_PHOTO and CAMERA_PHOTO
#          (after the general "realistic lighting" primer in QUALITY,
#          before the geometric anchors). Deliberately skipped for the
#          CV document branch (DOC_PRESERVE / DOC_QUALITY) — ID-style
#          photos want flat studio lighting, not scene integration.
#
#          Why this placement avoids identity conflict: PRESERVE_PHOTO
#          is separated from the new anchor by QUALITY_PHOTO (~180
#          chars), so "skin tone" (identity, melanin/undertone) and
#          "color cast" (illumination on top of skin) are far enough
#          apart in the prompt that the model does not read them as
#          contradicting each other. Phrasing is positive-only and
#          passes the ``_has_disallowed_negative`` guard.
#
#          Also ships ``scripts/grant_credits.py`` — idempotent admin
#          CLI that grants ``image_credits`` to a user located by
#          (provider, username | first_name | external_id). Inserts
#          a ``CreditTransaction(tx_type='admin_grant')`` audit row
#          in the same commit. Reachable from production via the
#          ``admin · grant credits`` workflow_dispatch workflow
#          (uses the existing ``RAILWAY_TOKEN`` secret to pull
#          ``DATABASE_PUBLIC_URL`` from the Railway Postgres service).
# 1.25.6 — Mount /internal router on edge too. Previously the
#          router was gated by ``not settings.uses_remote_ai``, so
#          edge (COMPUTE_MODE=remote) returned 404 for every
#          /api/v1/internal/* path — including the admin
#          grant-credits / list-identities endpoints we rely on
#          for VK + Yandex credit adjustments. Edge has its own
#          Postgres; admin routes just need DB access, which is
#          available locally. INTERNAL_API_KEY gate is unchanged,
#          so the exposure surface is identical to primary.
# 1.25.5 — Admin workflows gain a ``target`` input (``primary`` |
#          ``edge``). Primary routes to ``RAILWAY_API_URL`` (global
#          Railway backend). Edge routes to ``RU_PUBLIC_BASE_URL``
#          (self-hosted RU server) — same ``INTERNAL_API_KEY`` gate
#          either way, since ``deploy-ru`` syncs the key into
#          ``.env.ru``. Needed because VK / Yandex registrations
#          live on the edge DB, not primary: without a target
#          switch, grants to those users landed on phantom rows on
#          the primary instance. No endpoint-side change.
# 1.25.4 — Admin grant-credits: email-based lookup + provider-agnostic
#          match against ``profile_data.email`` across google / vk_id /
#          apple / yandex identities. ``_fmt_candidate`` now surfaces
#          ``profile_email`` so the list-identities diagnostic can
#          disambiguate users without re-running the grant. Amount
#          cap raised 10_000 → 100_000 for bulk admin top-ups.
#          ``admin-grant-credits.yml`` workflow takes an ``email``
#          input; ``admin-list-identities.yml`` extends the provider
#          whitelist to ``yandex`` / ``ok`` / ``phone``.
# 1.25.3 — Admin diagnostic endpoint ``GET /api/v1/internal/admin/list-identities``
#          for disambiguating lookups when ``admin/grant-credits``
#          returns ``not_found`` / ``ambiguous``. Returns recent
#          users for a given provider with profile_data snippets,
#          credits and ``user_id``. Gated by the same
#          ``X-Internal-Key`` as the rest of ``/internal``.
# 1.25.2 — Admin credit-grant HTTP endpoint.
#          Adds ``POST /api/v1/internal/admin/grant-credits`` (gated
#          by ``X-Internal-Key``) that mirrors
#          ``scripts/grant_credits.py`` for environments where the
#          Postgres TCP proxy is not publicly reachable (the case on
#          this Railway project — the managed Postgres only exposes
#          ``postgres.railway.internal``). The endpoint resolves a
#          user by (provider, username | first_name | external_id),
#          applies the balance delta, and writes a
#          ``CreditTransaction(tx_type='admin_grant')`` audit row in
#          the same transaction. Returns one of
#          ``granted | dry_run | not_found | ambiguous``.
#
#          Consumed by ``.github/workflows/admin-grant-credits.yml``:
#          the workflow no longer needs ``DATABASE_PUBLIC_URL`` or
#          the Railway CLI on the runner — it just posts the grant
#          payload to ``$RAILWAY_API_URL/api/v1/internal/...`` using
#          the existing ``INTERNAL_API_KEY`` secret. Two independent
#          layers of access control (repo-admin-gated
#          workflow_dispatch + X-Internal-Key) are preserved.
# 1.26.0 — Photo pipeline v2 fixes: storage counter + download, framing
#          as prompt-only, per-style «Другой вариант», cross-server
#          /storage peer fallback, A/B UI relabel.
#
#          1) Storage UX (src/api/v1/tasks.py + web):
#             * ``list_tasks`` теперь фильтрует задачи по
#               ``_image_available`` до того, как считает ``total_count``,
#               поэтому счётчик в NavBar больше не расходится с тем,
#               что открывает ``StorageModal``. Был баг «кнопка
#               хранилища открывает пустую модалку» — причина была в
#               том, что ``total_count`` считался sql-уровнем, а items
#               фильтровались в Python.
#             * ``StepGenerate.tsx`` ушёл с ``<a href download>`` на
#               ``fetch+blob`` с in-place сообщением «Не удалось
#               скачать файл» при 404 (тот самый ``{"detail":"Not
#               found"}`` из прод-репорта).
#
#          2) Framing как директива промпта, не размер
#             (src/prompts/image_gen.py + engine.py + orchestrator):
#             * ``resolve_output_size`` больше не переключает
#               ``output_aspect`` по ``framing`` — размер теперь
#               определяется только стилем + PuLID-эвристиками.
#               Раньше portrait→square_hd / half_body→portrait_4_3 /
#               full_body→portrait_16_9 ломали формат файла независимо
#               от стиля, и пользователь, выбравший «портрет»,
#               получал квадрат.
#             * ``PromptEngine.build_image_prompt`` принимает
#               ``framing``; ``_build_mode_prompt`` добавляет короткую
#               «Framing: head-and-shoulders close-up» / «half-body
#               from the waist up» / «full body head-to-toe» директиву.
#               Для документных стилей директива не добавляется —
#               там композиция фиксирована вендором.
#             * ``pipeline._execute_inner`` достаёт ``framing`` и
#               ``user_input_hints`` из task context и передаёт в
#               ``executor.single_pass`` явными kwargs. ``single_pass``
#               мерджит ``input_quality.to_prompt_hints()`` с
#               пользовательскими hints (user > quality-gate), раньше
#               они перезатирались метриками из input-гейта и
#               модалка «Другой вариант» молча ничего не меняла.
#             * Edge→primary пропаганда: ``remote_ai.submit_task/
#               submit_and_wait``, ``_handle_edge_analysis`` и
#               ``internal.process_analysis_remote`` теперь форвардят
#               ``framing`` + ``input_hints``. До этого RU-edge
#               выкидывал оба поля при проксировании на primary.
#             * ``web/src/context/AppContext.tsx`` добавил ``framing``
#               в deps у ``useCallback(generate)`` — иначе фронт
#               замыкался на первое значение ``framing='portrait'``
#               и не отправлял последующие выборы.
#
#          3) Модалка «Другой вариант» — per-style поля, перевод,
#             применение (src/prompts/style_spec.py +
#             services/style_loader.py + prompts/variation_engine.py +
#             web/src/components/wizard/StyleSettingsModal.tsx):
#             * ``StructuredStyleSpec.allowed_variations``: плоский
#               ``list[str]`` заменён на ``dict[str, list[str]]``
#               (каналы ``lighting`` / ``scene`` / ``clothing`` /
#               ``framing``). ``style_loader`` перестал плющить эту
#               структуру — отдаёт 1-в-1 из ``data/styles.json``.
#             * ``VariationEngine.apply_variation`` переписан на новую
#               схему: ``lighting`` проверяется по
#               ``allowed_variations["lighting"]``,
#               ``scene_override`` — только для ``FLEXIBLE`` +
#               непустого канала ``scene``, ``clothing_override`` —
#               только если канал ``clothing`` непуст. Введён
#               ``strict`` флаг: curated ``StyleVariant`` из ротации
#               идёт с ``strict=False`` (авторское ревью), а
#               пользовательские hints — с ``strict=True`` (строгая
#               per-channel валидация). ``_build_mode_prompt`` теперь
#               действительно вызывает этот движок для A/B-пути.
#             * ``StyleSettingsModal.tsx`` перекрашен в
#               ``gradient-border-card glass-card`` (как
#               ``StorageModal``), добавил RU-словари (golden hour
#               → «Золотой час», portrait → «Портрет», …), условный
#               рендер полей (``options[key]?.length > 0``) и
#               заголовок «Настройки стиля · <name>». Теперь стиль
#               «Эйфелева башня» показывает только ракурс и свет,
#               ``flexible`` — scene / clothing сверху.
#             * ``dump_styles`` обновлён под dict-формат.
#
#          4) A/B UI-labels (web/src/data/ab-models.ts +
#             StepGenerate.tsx):
#             * ``nano_banana_2`` → «Обычный режим» (1 кредит),
#               ``gpt_image_2`` → «Премиум» (2 кредита). Новый
#               ``formatAbCredits(model)`` с корректной русской
#               плюрализацией («1 кредит» / «2 кредита» /
#               «5 кредитов»). Списание на бэкенде остаётся 1 кредит
#               в ``_reserve_credit_for`` — тариф «Премиум 2
#               кредита» пока UI-обещание, реальное списание будет
#               отдельным PR через reserve/refund цепочку.
#
#          5) Cross-server /storage peer fallback (src/main.py +
#             src/config.py):
#             * ``serve_storage`` после неудачных local/Redis/DB b64
#               теперь дергает соседний инстанс: primary идёт в
#               ``edge_peer_url``, edge — в
#               ``remote_ai_backend_url`` (каждый знает адрес
#               соседа). Запрос авторизуется по ``X-Internal-Key``;
#               получатель узнаёт peer-запрос по тому же header'у и
#               НЕ делает рекурсивный fallback, чтобы избежать
#               пинг-понга.
#             * Финальный 404 для браузера теперь отдаёт читаемый
#               HTML «Файл не найден, истёк 24-часовой срок
#               хранения», а не голый JSON. API-клиенты (Accept:
#               application/json) получают прежний JSON.
#             * Новый config-field ``edge_peer_url: str = ""`` +
#               ``EDGE_PEER_URL=`` в ``.env.example``. Пустое
#               значение = fallback выключен (legacy-поведение).
#
#          Тесты: ``tests/test_prompts/test_variation_engine.py``
#          (новый, 8 кейсов на per-channel валидацию),
#          ``tests/test_prompts/test_image_gen_prompt.py`` (+3 кейса
#          на framing-директивы и независимость от размера),
#          ``tests/test_orchestrator/test_executor_ab_routing.py``
#          (+3 кейса на прокидывание framing / user_input_hints +
#          мердж hints), ``tests/test_api/test_analyze_ab.py``
#          (+2 кейса на persist ``framing`` / ``input_hints`` в
#          task.context + невалидный JSON). Все 1712 тестов
#          проходят, ruff clean, tsc clean.
#
#          Рollback: Phase 1-3 — чистые feature-edits, revert
#          коммита. Phase 4 огорожен ``if settings.edge_peer_url:``,
#          без env-переменной — старое поведение.
# 1.26.1 — Patch: swap A/B labels + universal face-only anchor.
#
#          1) A/B labels swap (web/src/data/ab-models.ts):
#             * ``gpt_image_2`` теперь первым в списке с лейблом
#               «Обычный режим» (1 кредит), ``nano_banana_2`` — вторым
#               как «Премиум» (2 кредита). До этого маппинг был
#               обратным: пользователи жаловались, что по нажатию
#               «Обычный» в логах FAL видно вызов Nano Banana. Default
#               на бэке (``src/config.py::ab_default_model``) уже был
#               ``gpt_image_2`` — он совпал с новым «Обычным» без
#               правок бэка. Роутинг в ``unified.py`` / ``factory.py``
#               по ключу модели не менялся, swap чисто
#               UI-косметический (но устраняет product-смысловое
#               расхождение). Стоимость списания остаётся 1 кредит
#               за любой режим (отложенный billing, см. 1.26.0).
#
#          2) Универсальный face-only anchor + drop pose-clamp
#             (src/prompts/image_gen.py):
#             * ``_dating_social_change_instruction`` убрал
#               «Keep the original pose and framing» в non-full-body
#               ветке. Full-body (yoga/beach/…) уже был без clamp.
#             * ``build_cv_prompt`` убрал «Keep the original pose» в
#               non-doc ветке. Document styles (passport_rf /
#               visa_us / photo_3x4 / …) продолжают идти через
#               ``is_doc`` ветку с DOC_PRESERVE + DOC_QUALITY +
#               фиксированной ``Composition:`` — им pose-clamp нужен
#               по требованиям ID-фото.
#             * ``_build_mode_prompt`` в A/B-пути всегда эмитит
#               ``PRESERVE_PHOTO_FACE_ONLY`` (раньше для close-up
#               стилей ставил ``PRESERVE_PHOTO``, который косвенно
#               блокировал позу). Лицо фиксируется жёстко везде
#               одинаково; поза и кадр определяются сценой +
#               ``framing_line`` из шага 3 wizard'а.
#             * Константа ``PRESERVE_PHOTO`` сохранена в модуле —
#               её ещё использует legacy non-A/B path и тест
#               ``test_preserve_text.py``; мы не «сливаем» два
#               разных анкера в один.
#
#          Мотивация: в v1.26 пользовательский framing (портрет /
#          полрост / полный рост) пробрасывался по всей цепочке edge
#          → primary → pipeline → PromptEngine и добавлялся
#          директивой «Framing: …» в промпт. Но в том же промпте
#          выше стояла жёсткая фраза «Keep the original pose and
#          framing» (для non-full-body стилей), что буквально
#          запрещало модели менять кадр. Получалось два
#          взаимоисключающих сигнала, и в большинстве случаев
#          модель отдавала приоритет первому — пользовательский
#          framing молча игнорировался. Теперь клампа нет, и
#          framing управляет композицией без конфликта с
#          изначальным кадром реферанса.
#
#          Тесты: ``test_full_body_prompt_adaptation.py`` — тест
#          close-up стиля инвертирован (теперь без pose-clamp).
#          ``test_image_gen_prompt.py`` — добавлен
#          параметризованный тест (7 стилей × 3 framing) на
#          отсутствие «original pose»/«original framing» и
#          присутствие PRESERVE_PHOTO_FACE_ONLY + регресс-гард
#          для passport_rf/visa_us/photo_3x4 (DOC_PRESERVE +
#          Composition на месте).
#
#          Rollback: обе правки — чистые feature-reverts. Swap
#          лейблов — revert web/src/data/ab-models.ts; pose-clamp
#          — revert двух строк в ``_dating_social_change_instruction``
#          / ``build_cv_prompt`` и ветки в ``_build_mode_prompt``.
# 1.26.2 — Hotfix: primary storage survival (хранилище 0 / фото
#          исчезает после перезагрузки).
#
#          Root cause: ``/api/v1/analyze`` на primary UI-потоке всегда
#          ставил в ``task.context.policy_flags`` флаг
#          ``delete_after_process=True`` (src/api/v1/analyze.py:447).
#          Worker после ``COMPLETED`` честно уважал этот флаг в
#          ``_cleanup_ephemeral_artifacts`` и удалял Redis-кеш
#          ``ratemeai:gen_image:global:<task_id>`` + файл
#          ``generated/<user>/<task>.jpg`` с локального диска.
#
#          На Railway primary развернут как три отдельных сервиса
#          (``app``, ``worker``, ``bot``, см. ``ci.yml`` строки 245-249)
#          без общего volume. Значит файл, записанный worker'ом на
#          его эфемерный диск, ``app``-контейнер не видел никогда —
#          единственный канал выдачи картинки пользователю был
#          Redis-кеш, который cleanup стирал через секунды после
#          COMPLETED. База base64 (DB fallback) писалась только при
#          двойном отказе Redis-staging — то есть в happy-path
#          никогда. Итог: ``/api/v1/tasks`` → ``_image_available``
#          возвращал False → галерея 0, превью возвращало 404 → в
#          ``StepGenerate.tsx`` клик по фото открывал ``StorageModal``,
#          а тот с ``items.length===0`` показывал «Пока нет генераций»
#          — именно та «модалка», на которую жаловался пользователь.
#
#          Fix — минимальный и не ломающий edge-контракт:
#            * ``src/api/v1/analyze.py``: ``delete_after_process=True``
#              → ``False``. Edge → primary поток (``RemoteAIService`` /
#              ``/internal/process-analysis``) по-прежнему шлёт
#              ``delete_after_process=True`` в payload, а
#              ``build_policy_flags`` уважает уже существующий ключ
#              и не перетирает его дефолтом — edge-семантика
#              сохранена. Primary-картинка живёт штатные 72 ч в
#              Redis + чистится ``privacy_gc_cron`` через 24 ч.
#            * ``src/workers/tasks.py``: staging-блок переписан так,
#              что ``generated_image_b64`` **всегда** попадает в
#              ``analysis_result`` (и дальше — в ``task.result`` в
#              DB), не только как аварийный fallback. Это третий,
#              самый надёжный канал для ``_image_available`` и
#              ``/storage/`` endpoint'а — картинка переживает и
#              рестарт worker-контейнера (эфемерный диск), и
#              evict Redis-ключа (``allkeys-lru``).
#            * ``src/api/v1/tasks.py::get_task``: стрипаем
#              ``generated_image_b64`` из ``TaskResponse`` — клиенту
#              эти ~200 КБ b64 на каждом polling-запросе не нужны,
#              фронт забирает картинку напрямую через
#              ``/storage/`` endpoint. ``/internal/task/{id}/status``
#              не задет — edge получает b64 в отдельном
#              ``generated_image_b64`` поле ``RemoteTaskStatusResponse``.
#
#          Почему предыдущие правки (1.26.0 peer-fallback /
#          total_count filter) не помогли: первая не спасала при
#          двойном cleanup (peer тоже выполнил delete), вторая
#          честно показывала «0» вместо фантомного счётчика, но
#          корень не трогала. 1.26.2 возвращает картинку в
#          хранилище целиком.
#
#          Тесты:
#            * ``tests/test_workers/test_process_analysis.py`` —
#              два новых кейса: primary-flow НЕ дёргает
#              ``storage.delete`` / ``redis.delete`` по
#              gen_image-ключу; worker всегда пишет b64 в
#              ``task.result`` в happy-path (с верификацией
#              ``base64.b64decode == bytes``).
#            * ``tests/test_api/test_analyze.py`` — два новых
#              кейса: UI-flow создаёт task c
#              ``policy_flags.delete_after_process=False``; GET
#              ``/api/v1/tasks/{id}`` после COMPLETED не отдаёт
#              ``generated_image_b64`` наружу.
#            * Существующий ``test_process_analysis_cleans_
#              ephemeral_artifacts_when_policy_requires`` остался
#              зелёным — edge-путь не изменён.
#
#          Rollback: одна строка в ``src/api/v1/analyze.py``
#          (``False`` → ``True``) возвращает старое поведение.
#          Правки в worker и ``get_task`` изолированы и могут
#          жить отдельно, но без них primary-картинка снова не
#          переживёт рестарт / evict.
# 1.27.0 — Style-schema v2 production cutover. Всю воркфлоу
#          «image generation» переведём на slot-based стили
#          (``schema_version: 2``) с явными каналами weather /
#          time_of_day / season / clothing / background и
#          модельно-специфичными quality/identity хвостами. Фаза
#          "big-bang на один деплой, без канарейки" по запросу
#          пользователя.
#
#          1) Data migration (data/styles.json, 100/100 entries):
#             * ``scripts/migrate_styles_v1_to_v2.py --batch all
#               --write`` мигрирует все 100 стилей на
#               ``schema_version: 2``. Бэкапы времянки дропаются
#               в ``data/.styles_backup/`` (gitignored); миграция
#               идемпотентна, повторный прогон no-op.
#             * Новые поля per-entry: ``trigger`` (основной текст
#               сцены), ``context_slots`` (``lighting`` /
#               ``framing`` / etc.), ``weather`` (enabled + allowed
#               + default_na), ``clothing`` (default + allowed +
#               gender_neutral), ``background`` (base + lock +
#               overrides_allowed), ``quality_identity`` (пустой
#               блок — заполняется с per-model wrapper'ом). v1
#               поля сохранены для fallback.
#
#          2) Prompt composition (src/prompts/style_schema_v2.py +
#             composition_builder.py + model_wrappers.py):
#             * ``StyleSpecV2`` dataclass с explicit slots.
#             * ``build_composition(spec, mode, model, gender,
#               input_hints, variant_id)`` собирает
#               ``CompositionIR`` из trigger + context slots +
#               variation (через VariationEngineV2) + background
#               lock. IR потом упаковывается в финальную строку
#               per-model через wrapper (``wrap_for_gpt_image_2``
#               / ``wrap_for_nano_banana_2``) — каждая модель
#               получает свой quality/identity хвост без ветвления
#               в общем builder'е.
#
#          3) Executor branch (src/orchestrator/executor.py):
#             * ``single_pass`` теперь сначала пробует
#               ``PromptEngine.build_image_prompt_v2(...)``, который
#               заходит в v2-путь только если: а) флаг
#               ``unified_prompt_v2_enabled=True``, б) стиль
#               зарегистрирован как ``StyleSpecV2`` в v2-registry
#               (``register_v2_styles_from_json``). Иначе возвращает
#               ``None`` → fallback на legacy
#               ``build_image_prompt(...)`` бит-в-бит без изменений.
#             * Двойная защита: даже если v2-registry пуст или
#               JSON битый — executor гарантированно отработает по
#               v1, production генерация не прерывается.
#
#          4) Variation engine v2 (src/prompts/variation_engine_v2.py):
#             * ``apply_variation_v2`` с раздельными каналами
#               (weather / time_of_day / season / background_type)
#               вместо старой whitelist-логики. Старый
#               ``VariationEngine`` (conflates weather с lighting)
#               остался как fallback для v1-стилей; на v2-стилях
#               за движок отвечает флаг
#               ``variation_engine_v2_enabled=True``.
#             * ``generate_next_variant_hints(spec, previous_hints,
#                 history_size)`` — интеллектуальная подстановка
#               следующего варианта: rotate через каналы, избегая
#               повтора последних N.
#
#          5) Catalog API v2 (src/services/style_catalog.py +
#             src/api/v1/catalog.py):
#             * ``GET /api/v1/catalog/styles?mode=...&schema=v2``
#               возвращает плоский список стилей с
#               ``schema_version: 2``.
#             * ``GET /api/v1/catalog/options?style=<id>&schema=v2``
#               возвращает structured slots: ``trigger``,
#               ``context_slots``, ``weather`` (enabled/allowed/
#               default_na), ``clothing`` (default/allowed/gender_
#               neutral), ``background`` (base/lock/overrides_
#               allowed). Легко питает будущую «Другой вариант»
#               UI с раздельными переключателями.
#             * Без параметра ``?schema=v2`` (legacy) API продолжает
#               возвращать v1-формат — фронт до миграции не
#               ломается.
#
#          6) Feature flags (src/config.py + .env.example): все
#             три v2-флага ``STYLE_SCHEMA_V2_ENABLED``,
#             ``UNIFIED_PROMPT_V2_ENABLED``,
#             ``VARIATION_ENGINE_V2_ENABLED`` дефолтно = True.
#             Тривиальный rollback: выставить нужный флаг в
#             ``False`` в Railway / ``.env.ru`` и перезапустить
#             сервис — executor моментально валится на v1 без
#             ревёрта кода.
#
#          7) CI/CD — pin флагов (.github/workflows/ci.yml):
#             * Railway env-sync (``rl_set`` loop) повторно
#               выставляет три v2-флага в ``true`` на
#               ``app``/``worker`` при каждом деплое — защита от
#               ручного override'а в dashboard.
#             * Также пройдёт ``railway variables delete
#               PROMPT_ENGINE_MAP_FIX`` — флаг удалён, остаток в
#               env мусорит логи.
#             * RU edge deploy (``sync_env``) делает то же самое с
#               ``/opt/ratemeai/.env.ru``: пишет три v2-флага в
#               ``true``, выпиливает ``PROMPT_ENGINE_MAP_FIX``.
#
#          8) V1 cleanup (чисто dead code):
#             * ``src/prompts/ab_prompt.py`` удалён — A/B-промпты
#               теперь строит ``PromptEngine`` → v2 pipeline.
#             * ``tests/test_prompts/test_ab_prompt.py``,
#               ``tests/test_prompts/test_engine_map_fix.py``,
#               ``tests/test_prompts/test_engine_characterization.py``
#               удалены.
#             * ``_IMAGE_PROMPT_MAP`` и
#               ``_prompt_engine_map_fix_enabled`` helper удалены
#               из ``src/prompts/engine.py``. ``build_image_prompt``
#               теперь делает прямой dispatch в
#               ``_DIRECT_IMAGE_BUILDERS`` (баг с теряющимися
#               framing/target_model из-за лямбд исправлен
#               окончательно).
#             * ``src/config.py``: удалены поля
#               ``prompt_engine_map_fix`` и ``ab_prompt_max_len``.
#             * Dead-on-prod но alive-in-tree (покрыты тестами,
#               работают как safety net на случай битого JSON):
#               ``src/prompts/image_gen.py::_build_mode_prompt``,
#               ``src/services/style_loader.py``,
#               ``src/prompts/style_variants.py``. Докстринги
#               обновлены, план удаления — в
#               ``docs/CLEANUP_STYLE_V2.md``.
#
#          9) .gitignore: добавлены ``_diag/`` (артефакты
#             ``scripts/shadow_diff_prompt_engine.py``) и
#             ``data/.styles_backup/`` (таймстемпированные
#             снэпшоты от миграционного скрипта).
#
#          Тесты: 1953 passed (один раз после каждого шага
#          cleanup), ruff clean. Новые файлы:
#          ``tests/test_prompts/test_schema_v2_parity.py``
#          (v1 ↔ v2 промпты должны давать идентичный вывод для
#          базовых inputs — гарантия того, что v2 ничего не
#          ломает на старых стилях),
#          ``tests/test_prompts/test_variation_engine_v2.py``
#          (раздельные каналы + генерация next-variant hints),
#          ``tests/test_services/test_style_migration_v2.py``
#          (idempotency, conservative defaults, батч-режимы).
#
#          Rollback plan (инкрементальный, без ревёрта кода):
#            * Полный откат v2-пайплайна: на обоих сервисах
#              (Railway app+worker + RU edge) выставить
#              ``UNIFIED_PROMPT_V2_ENABLED=false`` и
#              перезапустить. Executor уйдёт в v1 branch,
#              ``data/styles.json`` с ``schema_version: 2``
#              по-прежнему читается через v1-конвертер в
#              ``style_loader.get_structured_specs()``.
#            * Откат регистрации v2-стилей (если
#              ``style_loader_v2`` как-то повреждает
#              ``STYLE_REGISTRY``): ``STYLE_SCHEMA_V2_ENABLED=false``,
#              v2-registry остаётся пустым, v1 fallback на 100 %.
#            * Откат variation engine (если новая логика каналов
#              даёт странный output): ``VARIATION_ENGINE_V2_ENABLED=
#              false``, composition_builder вернётся к старому
#              ``VariationEngine`` внутри v2-пути.
#
#          Edge contract / worker contract / external API: без
#          изменений. Frontend: v2-эндпоинты опциональны
#          (``?schema=v2``), default остаётся v1 JSON — UI
#          можно мигрировать отдельным PR, когда готов дизайн
#          для «Другой вариант» с раздельными каналами.
# 1.27.1 — Catalog tech-debt cleanup + admin panel for styles.
#          Серия из 10 коммитов на main; пользовательский контракт
#          без изменений, всё edge/bot/worker остаётся совместимым,
#          но изнутри каталог стилей теперь живёт в одном месте —
#          ``data/styles.json`` — и редактируется через UI.
#
#          1) Hotfix удалённого ``influencer`` (588c24f). Стиль
#             был выпилен ещё в v1.26.x cleanup'е, но оставались
#             ссылки в SOCIAL_STYLES / variants — заменены на
#             ``influencer_urban``. Без этого хелпер
#             ``style_variants`` падал на старых записях, где
#             пользователь когда-то выбрал ``influencer``.
#
#          2) One-shot migrations (b6b12ff, b00a240) перенесены
#             в ``scripts/migrations/2026_04_catalog_cleanup/``,
#             ``data/styles.json`` пересохранён единым каноном
#             (schema_version: 2 везде, дедуплицированные id),
#             из ``image_gen.SOCIAL_STYLES/CV_STYLES/PERSONALITIES``
#             и ``style_variants.SOCIAL_VARIANTS`` вычищены
#             ID удалённых стилей — мёртвый fallback больше не
#             всплывает в логах ``Unknown style id``.
#
#          3) Scenario styles (2a24bb2). Часть стилей теперь
#             помечается полем ``scenario`` в JSON: они не
#             попадают в основной каталог
#             (``GET /api/v1/catalog/styles``) и доступны только
#             через сценарии (онбординг, A/B-эксперименты). Новые
#             хелперы ``get_scenario_styles_json[_v2]`` +
#             фильтр в ``get_catalog_json[_v2]``. Frontend
#             (``web/src/scenarios/config.ts`` + Storage/Review
#             модалки) ходит за этим списком отдельно.
#
#          4) Admin panel (0232bb3 + 556ed80 + f7ee2ab). Новый
#             whitelist-gate ``ADMIN_USER_IDS`` (см.
#             ``src/api/v1/admin/auth.py`` — пустой whitelist =
#             замок для всех; безопасный production default),
#             атомарный store на ``data/styles.json``
#             (``os.replace`` + ``threading.Lock`` +
#             timestamped backup в ``data/.styles_backup/``),
#             CRUD-эндпоинты ``GET/POST/PUT/DELETE
#             /api/v1/admin/styles`` со схемой v1+v2 и
#             ``_validate_v2_shape`` (server-side enforcement
#             для ``background.base``, ``clothing.default``,
#             ``quality_identity.base``). Web-UI на
#             ``/admin/styles`` (React, slot-based редактор,
#             dirty-state guard через ``window.confirm``,
#             inline валидация v2-полей).
#
#          5) Bot catalog hot-reload (8078f2c, 922777e).
#             Хардкод ``STYLE_CATALOG`` (~850 строк Python dict)
#             в ``src/services/style_catalog.py`` заменён на
#             ``_BotCatalogProxy`` поверх ``load_styles_from_json()``.
#             Прокси кэширует список стилей; админский endpoint
#             вызывает ``style_store.invalidate_caches()``,
#             которая дёргает ``STYLE_CATALOG._invalidate()`` —
#             бот моментально подхватывает изменения админки
#             без рестарта. Интерфейс прокси совместим со
#             старым dict (``.get``, ``__getitem__``, ``.items``)
#             — все потребители не поменялись.
#
#          6) Premium unlocks seed (922777e). Скрипт
#             ``scripts/migrations/2026_04_catalog_cleanup/
#             seed_premium_unlocks.py`` (одноразовый) проставил
#             ``unlock_after_generations: 3..5`` десяти стилям:
#             ``business_executive``, ``casual_chic_pro``,
#             ``coffee_shop_premium``, ``culinary_artisan``,
#             ``evening_elegance``, ``executive_traveler``,
#             ``gallery_curator``, ``professional_warm``,
#             ``rooftop_evening``, ``vinyl_lounge``. Замок lock'ов
#             остался жив (FNV-fallback из web выпилен в
#             8c11024 — теперь UI считывает поле напрямую из
#             API и не выдумывает блокировки).
#
#          7) Frontend sync (8c11024). ``StylesSheet`` /
#             ``StyleSettingsModal`` /
#             ``Simulation``/``StorageModal`` подключены к
#             scenario-API; legacy FNV-fallback убран,
#             ``CatalogStyleEntry`` единый source-of-truth.
#
#          Тесты: 1953 passed (включая новые
#          ``tests/test_api/test_admin_styles.py``,
#          ``tests/test_api/test_catalog.py``,
#          ``tests/test_services/test_style_migration_v2.py``).
#          Test-isolation fix: фикстура ``isolated_styles_file``
#          в ``test_admin_styles.py`` теперь сбрасывает
#          ``STYLE_CATALOG._invalidate()`` и
#          ``style_loader._STYLES_CACHE`` на teardown — без этого
#          предыдущий тест с временным styles.json оставлял
#          пустой кэш и валил ``enhancement_advisor`` с
#          ``ZeroDivisionError``.
#
#          Rollback: серия чисто аддитивная, кроме админского
#          UI/API. В случае проблем достаточно
#          ``git revert 922777e..588c24f`` (10 коммитов) — все
#          файлы schema-v2 совместимы с v1.27.0.
# 1.27.2 — Prompt content cleanup + bot is now an *always-GPT*
#          client. Адресует две независимые жалобы из v1.27.1:
#
#          1) Promp main motif missing. v2-миграция случайно
#             разложила scene-данные так, что ключевой мотив стиля
#             («зеркало», «таймс-сквер crosswalk», «walk-in closet
#             with full-length mirror») попадал не в
#             ``background.base``, а в ``context_slots.lighting``.
#             ``composition_builder._resolve_lighting`` возвращает
#             ``""``, когда пользователь не открывал «Другой
#             вариант», поэтому мотив тихо вылетал из default-
#             промпта (Times Square без неонов, Эйфелева без башни,
#             зеркало без зеркала). Скрипт-аудит
#             ``scripts/migrations/2026_04_prompt_quality/
#             audit_v2_styles.py`` нашёл 117 / 126 стилей с
#             location-shaped строками в lighting; миграция
#             ``split_lighting_and_locations.py`` перенесла 395
#             таких записей в ``background.overrides_allowed``
#             (с дедупликацией и порядком), а ``lock=flexible``
#             у 87 стилей переключился на ``"semi"`` —
#             ``_resolve_scene`` теперь склеивает «<sub_location>
#             in <base>» вместо REPLACE, default-рендер не
#             меняется, а через «Другой вариант» мотив
#             reachable как sub-location. Идемпотентно;
#             ре-запуск — no-op. Регрессионный тест
#             ``tests/test_prompts/test_v2_motif_in_prompt.py``
#             фиксирует, что ``Times Square``, ``Venetian`` и
#             ``Eiffel`` присутствуют в дефолтных промптах.
#             Out of scope (трекается в ``audit_report.md`` для
#             ручной правки через ``/admin/styles``):
#             ``mirror_aesthetic.background.base`` всё ещё
#             описан без слова «mirror»; пустой
#             ``quality_identity.base`` у всех 126 стилей
#             (legacy ``QUALITY_PHOTO`` уже покрывает —
#             косметика).
#
#          2) Bot occasionally rendered Nano Banana 2 even
#             though Telegram UI не показывает A/B-пикер. Корень
#             — ``mode_select._submit_analysis`` не клал
#             ``image_model`` в multipart, и сервер падал на
#             ``settings.ab_default_model``. Дефолт правильный
#             (``gpt_image_2``), но ручная правка Railway
#             dashboard или флип ``AB_TEST_ENABLED=false``
#             (фолбэк на PuLID) тихо отправляла бот-трафик
#             мимо GPT. Архитектурный фикс — declare policy
#             at the call site: ``form_data['image_model'] =
#             'gpt_image_2'`` в боте + defense-in-depth pin в
#             ``ci.yml`` (``AB_TEST_ENABLED=true`` +
#             ``AB_DEFAULT_MODEL=gpt_image_2`` для app/worker
#             в том же for-loop, что и v2-флаги — heals
#             dashboard drift на каждом деплое). Веб-клиент
#             сохраняет Premium/NB2 toggle и остаётся
#             единственным каналом, где можно опт-ин в Nano
#             Banana 2. Static AST-тест
#             ``tests/test_bot/test_mode_select_form_data.py``
#             ловит любую попытку откатить policy.
#
#          Rollback: миграция данных аддитивная (lighting не
#          теряется — переезжает в overrides_allowed), бот-патч
#          и CI-pin тривиально откатываются. ``git revert``
#          трёх коммитов c1..c3 возвращает v1.27.1 поведение.
# 1.27.3 — Пользовательские параметры из «Другой вариант» теперь
#          реально влияют на промпт, одежда учитывает пол,
#          нераспознанные значения мягко подменяются, а не
#          теряются. Три точечных изменения, без перестройки
#          пайплайна сборки промпта.
#
#          1) Integration gaps. (a) ``composition_builder._resolve_scene``
#             и ``variation_engine_v2.apply_variation_v2`` для
#             ``BackgroundLockLevel.SEMI`` теперь принимают
#             ``scene_override`` как эквивалент ``sub_location``
#             (модалка отправляет именно ``scene_override``,
#             бэкенд раньше его молча дропал). (b) Executor
#             перенёс merge framing-а: ``input_hints['framing']``
#             перебивает аргумент ``framing`` (значение из
#             модалки побеждает значение шага «Выберите стиль»).
#             (c) В модалке появился explicit-чип
#             «По умолчанию» в секции framing, чтобы пользователь
#             понимал, что пустой выбор = унаследовать из шага.
#
#          2) Gender-aware clothing. ``ClothingSlot.default``
#             стал dict-ом ``{male, female, neutral}``;
#             ``StyleSpecV2.clothing_for(gender)`` отдаёт
#             gender-specific строку с фолбэком на
#             ``neutral`` → first non-empty. ``style_loader_v2``
#             принимает оба формата (str → нормализуется в
#             dict с одинаковыми значениями), ``style_catalog``
#             отдаёт админу dict. Миграционный скрипт
#             ``scripts/migrations/2026_04_gender_clothing/
#             seed_clothing_dict.py`` (dry-run + apply, atomic
#             ``os.replace``) перевёл все 126 v2-стилей и
#             прошил hand-curated женские варианты для 20
#             очевидно гендерных стилей (Burj Khalifa,
#             Brooklyn Bridge, Times Square, Yacht и т.п.).
#             Админка ``StylesAdminPage`` получила три
#             отдельных поля ``default_male / female /
#             neutral`` + обновлённую валидацию (хотя бы одно
#             непустое).
#
#          3) Soft substitution + post-generation hint.
#             ``CompositionIR.substitutions: list[dict]``
#             накапливает записи ``{channel, requested,
#             applied}``. ``_resolve_lighting / weather /
#             scene / clothing`` (и зеркально
#             ``apply_variation_v2``) при ``strict=True`` и
#             непустом whitelist делают
#             ``random.choice(whitelist)`` вместо тихого
#             ``return ""``. Свободные каналы (clothing без
#             ``allowed``, ``scene_override`` в FLEXIBLE без
#             whitelist) пропускают пользовательский текст
#             как есть. Executor конвертирует записи в
#             русские сообщения через
#             ``_format_substitution_notice_ru`` и кладёт в
#             ``result_dict['generation_warnings']``.
#             ``web/src/lib/api.ts`` экспортирует
#             ``readGenerationWarnings`` и ``TaskResultBody``;
#             ``StepGenerate`` рендерит amber-нотис над
#             результатом, когда замены были.
#
#          Тесты: 4 новых файла — ``test_clothing_gender``,
#          ``test_soft_substitution``, ``test_modal_overrides``,
#          ``test_executor_warnings``. Существующий
#          ``test_variation_engine_v2::
#          test_weather_rejected_when_not_in_allowed_strict``
#          переименован в ``..._substituted_...`` и теперь
#          проверяет soft-substitution вместо drop. Полный
#          test-suite зелёный (1582 + 4 новых файла).
#
#          Бот не трогаем — подсказка о подстановке только
#          в Web по выбору пользователя; бот продолжает
#          использовать pinned ``image_model=gpt_image_2``.
#
#          Rollback: серия аддитивная. (a) loader v2 по-прежнему
#          принимает str-форму clothing.default, (b) executor
#          warnings — append-only, (c) substitutions — поле
#          IR с default ``[]``. ``git revert`` четырёх коммитов
#          возвращает v1.27.2 поведение полностью.
# 1.28.0 — Prompt-pipeline-overhaul (May 2026). Five-stage rebuild
#          of the style → prompt path that fixes three production
#          defects in one go: (a) silent failure of "Improve from
#          storage" on purged generations, (b) "У зеркала" style
#          producing prompts without the word "mirror", and (c)
#          ten different users getting identical first generations
#          because the v2 variation engine only randomised when the
#          user pinned a hint.
#
#          Stage 0 — Hot UX fixes (additive, no schema change).
#            * ``web/src/pages/AppPage.tsx::handleImproveFromStorage``
#              now distinguishes 404 / non-image / network failures
#              and surfaces a concrete RU message via
#              ``app.setError`` instead of swallowing in ``catch``.
#            * ``web/src/lib/sanitize.ts::humanizeApiError`` parses
#              the structured ``detail.message`` / ``detail.suggestion``
#              from /pre-analyze before falling back to the generic
#              cleanup, so INVALID_IMAGE / NO_FACE / FACE_TOO_SMALL
#              all show the actual reason.
#            * ``web/src/components/StorageModal.tsx`` disables
#              «Улучшить» / «Скачать» on purged items with a tooltip.
#            * ``src/prompts/composition_builder.py``: new
#              ``_with_suffix`` helper kills the "warm light lighting"
#              stutter, and ``_ensure_trigger_in_scene`` appends
#              ``spec.trigger`` if it's missing from the resolved
#              scene — immediate fix for the ten Category-D styles
#              flagged by ``audit_report.md``.
#            * ``web/src/context/AppContext.tsx`` exposes
#              ``setError`` to consumers (was internal).
#
#          Stage 1 — StyleSpec v3 + SlotSampler (additive, gated by
#          ``style_schema_v3_enabled``, default OFF in code; flipped
#          via Railway env var post-deploy for safe rollback).
#            * New ``src/prompts/style_schema_v3.py`` —
#              ``StyleSpecV3`` with ``trigger_pool: tuple[str, ...]``
#              (≥1 entry, immutable headline motif), ``scene_anchor``
#              (lighting/weather-free baseline), ``AmbientPools``
#              (lighting / weather / time_of_day / season / materials
#              / framing_hint), and ``ResolvedSlots`` for what the
#              sampler actually rolled.
#            * New ``src/prompts/slot_sampler.py`` —
#              ``sample(spec, hints, *, seed) -> ResolvedSlots``.
#              Picks trigger from the pool every generation; rolls
#              each ambient channel from its pool when the user did
#              not pin a hint (this is the diversity fix); soft-
#              substitutes out-of-pool user values and records the
#              substitution for the executor warnings bucket.
#            * ``StyleRegistry`` extended with ``_v3_by_key`` map
#              and ``register_v3`` / ``get_v3`` / ``has_v3``
#              helpers.
#            * New ``src/services/style_loader_v3.py`` — reads only
#              ``schema_version: 3`` rows; rejects empty
#              ``trigger_pool``; materialises legacy ``trigger``
#              into a one-element pool when curated formulations
#              are missing.
#            * ``src/prompts/composition_builder.py::build_composition_v3``
#              consumes ``StyleSpecV3``, runs the sampler, builds
#              ``CompositionIR`` and asserts the trigger is in
#              ``scene_line`` (defence in depth).
#            * ``src/prompts/engine.py::build_image_prompt_v2`` accepts
#              ``seed`` and ``out_resolved_slots``; prefers v3 spec
#              when registered + flag on, falls back to v2 path
#              otherwise.
#            * Tests: ``test_slot_sampler.py`` (determinism, pool
#              membership, override precedence, soft substitution),
#              ``test_v3_composition.py`` (engine wiring, fallback),
#              ``test_style_loader_v3.py`` (loader gating).
#
#          Stage 2 — Migration script + curation. Every v2 row in
#          ``data/styles.json`` rewritten to ``schema_version: 3``
#          while preserving every v2 field for backward-compat.
#            * ``scripts/migrations/2026_05_styles_v3/migrate.py``
#              auto-derives ``scene_anchor`` (strips lighting via
#              ``_INLINE_LIGHTING_PATTERNS``), ``trigger_pool``
#              (defaults to ``[scene_anchor]``), ``ambient`` pools
#              (from ``context_slots`` / weather / heuristic
#              ``_TIME_OF_DAY_HINTS``).
#            * ``scripts/migrations/2026_05_styles_v3/curated.json``
#              hand-written rich pools for 15 headline styles
#              (mirror_aesthetic, paris_eiffel, dubai_burj_khalifa,
#              nyc_times_square, etc.) — 3-6 trigger formulations
#              each, expanded ambient and scene_overrides.
#            * Loaders made permissive: ``style_loader_v2._to_v2``
#              and ``style_catalog._v2_slots_from_raw`` accept both
#              ``schema_version: 2`` and ``: 3`` rows, so the v2
#              code path keeps producing a valid view from the
#              migrated catalog (no flag-day for unmigrated callers).
#            * New ``src/services/style_catalog._v3_slots_from_raw``
#              + ``get_style_options_v3``; ``/api/v1/catalog/styles/
#              {id}/options?schema=v3`` returns the full v3 payload
#              (trigger_pool, scene_anchor, scene_overrides,
#              ambient.*, clothing, framing); endpoint downgrades
#              gracefully to v2 / v1 if the row isn't v3.
#            * Tests: ``test_styles_v3_data.py`` pins schema-level
#              invariants (every row has trigger_pool ≥1, scene
#              _anchor non-empty, ambient block well-shaped, ≥3
#              triggers for curated styles); regression budget
#              ``MAX_DIRTY_SCENE_ANCHORS=45`` for residual
#              lighting/time tokens left by mixed phrases.
#
#          Stage 3 — UI per-slot control + seed reroll.
#            * ``src/api/v1/analyze.py`` accepts optional ``seed``
#              form field; ``src/orchestrator/pipeline.py`` reads
#              ``ctx['seed']`` and threads it to the executor; the
#              executor passes ``seed`` + a fresh ``out_resolved
#              _slots`` dict into ``build_image_prompt_v2`` and
#              copies the populated dict into
#              ``result_dict['resolved_slots']``.
#            * ``web/src/components/wizard/StyleSettingsModal.tsx``
#              rewritten for v3: read-only «Триггер» badge with
#              «Всегда в кадре. Изменить нельзя.» tooltip;
#              «Авто (рандом)» option for lighting / weather /
#              time_of_day / season pill groups; scene + clothing
#              free-text overrides with quick-pick chips. Channels
#              with empty pools are hidden so the modal never shows
#              a dead control. v2 / v1 payloads project onto the
#              same StyleOptions shape (downgrade-safe).
#            * ``web/src/components/wizard/StepGenerate.tsx``: the
#              «Другой вариант» button now triggers
#              ``handleReroll`` — generates a fresh 32-bit seed
#              client-side, keeps the user's last hints, and
#              resubmits. Separate «Настройки» button opens the
#              modal. ``ResolvedSlotsBadges`` (stacked variant)
#              renders «Что выбрано в этой генерации» under the
#              live image.
#            * ``web/src/lib/api.ts`` exposes ``ResolvedSlots``
#              type; ``analyze`` accepts ``seed?: number``;
#              ``getStyleOptions`` switched to ``?schema=v3``.
#            * ``AppContext.generate`` accepts ``seed`` parameter.
#            * Tests: ``test_executor_seed_and_resolved_slots.py``
#              pins the executor → engine → result_dict thread.
#
#          Stage 4 — Legacy cleanup + docs.
#            * ``src/prompts/variation_engine_v2.py`` marked
#              ``.. deprecated::`` (kept on disk for rollback).
#            * ``audit_report.md`` updated: every category gets a
#              «Resolution» column pointing at the new tests.
#            * New ``docs/prompt-pipeline-v3.md`` — author guide,
#              pipeline topology (Mermaid), how-to-add-a-style,
#              backwards-compat rules, per-channel UX contract.
#            * New ``test_v3_motif_in_prompt.py`` exercises ALL
#              126 styles × 5 seeds (630 generations) and asserts
#              the trigger lands in every prompt; uses the same
#              ``compress_prompt`` as production so filler-word
#              stripping doesn't false-positive.
#
#          Follow-up A1 — ``resolved_slots`` in history payload.
#            * ``src/models/schemas.py::TaskHistoryItem`` gets
#              ``resolved_slots: dict | None``; ``src/api/v1/
#              tasks.py`` projects ``Task.result['resolved_slots']``
#              through a whitelist (trigger / lighting / weather /
#              time_of_day / season / clothing) with a 240-char
#              cap, dropping analyst-grade fields like
#              ``random_picks`` / ``substitutions``.
#            * ``web/src/components/ResolvedSlotsBadges.tsx``
#              shared between ``StepGenerate`` (stacked variant)
#              and ``StorageModal`` (inline variant — dense
#              chips + overflow counter + tooltip).
#            * ``web/src/lib/api.ts``: new ``ResolvedSlots`` type
#              and optional ``resolved_slots`` field on
#              ``TaskHistoryItem``.
#            * Tests: ``test_tasks_resolved_slots.py`` (8 unit
#              tests on the projection helper).
#
#          Rollback strategy:
#            * Code edges with ``style_schema_v3_enabled=False``
#              by default — even after merge, the v3 code path is
#              dormant until env var ``STYLE_SCHEMA_V3_ENABLED=true``
#              is flipped on Railway. Quick-revert: set the env
#              var back to false, redeploy services.
#            * ``data/styles.json`` keeps every v2 field intact;
#              ``style_loader_v2._to_v2`` accepts schema_version 3
#              and produces a valid v2 view, so unrelated callers
#              that have not learned v3 still work.
#            * ``variation_engine_v2`` left on disk and reachable —
#              not removed in this release.
#            * ``git revert`` of this version + flipping the
#              Railway env var to false returns 1.27.3 behaviour
#              fully.
#
#          Test counts: 1966 backend tests pass (was 1601 at
#          1.27.3); 7 new test files added in the overhaul plus
#          1 file for follow-up A1. Frontend: ``tsc -b && vite
#          build`` clean, 499 modules.
# 1.29.0 — Style audit + admin curation tooling. Closes the loop
#          opened by 1.28: the v3 pipeline introduced randomised
#          ambient channels but had no operator surface for
#          deciding WHICH channels apply per style. The headline
#          symptom: ``mirror_aesthetic`` (an indoor style) was
#          surfacing «Сезон» pills with two values because the
#          ambient.season pool happened to be non-empty after the
#          migration auto-derivation. There was no way to fix it
#          without hand-editing data/styles.json.
#
#          Schema additions (additive, backwards-compatible):
#            * ``StyleSpecV3.available_channels: tuple[str, ...]``
#              — explicit whitelist of channels the user can
#              configure. Empty tuple = "не курировано", legacy
#              "non-empty pool ⇒ enabled" heuristic kicks in
#              (preserves 1.28 behaviour for the 126 styles
#              already on disk). Allowed values:
#              ``CONFIGURABLE_CHANNELS`` (lighting, weather,
#              time_of_day, season, framing, clothing,
#              scene_override).
#            * ``StyleSpecV3.location_type: str`` — coarse
#              classifier (``indoor`` / ``outdoor`` / ``mixed`` /
#              ``document``) consumed by the lint engine. The
#              sampler ignores it; the loader auto-derives it
#              from ``scene_anchor`` keywords when the JSON
#              entry leaves it blank, so 126-style migration
#              isn't required to start using lint.
#            * ``StyleSpecV3.is_channel_enabled(channel) -> bool``
#              encapsulates the curated/uncurated decision so
#              both sampler and modal share the contract.
#
#          Sampler:
#            * ``slot_sampler.sample`` now consults
#              ``spec.is_channel_enabled`` for each ambient
#              channel; gated channels resolve to ``""`` even
#              when the user passes a hint (defence in depth
#              against legacy clients that bypass the modal).
#
#          Lint engine — new ``src/services/style_lint.py``:
#            * ``lint_style(raw)`` returns a list of structured
#              issues. Codes: ``TRIGGER_DIRTY`` (warning;
#              framing/lighting/weather/season tokens leaking
#              into trigger), ``INDOOR_SEASON`` /
#              ``INDOOR_WEATHER`` (error; indoor styles can't
#              expose those), ``DOCUMENT_AMBIENT`` (error;
#              document styles use neutral lighting),
#              ``SEASON_INCOMPLETE`` (warning; pool < 4
#              seasons), ``EMPTY_POOL`` (error; channel enabled
#              but ambient pool empty), ``UNKNOWN_CHANNEL`` /
#              ``UNKNOWN_LOCATION`` (error; schema typos).
#            * ``find_conflicts(raw_styles, similarity_cutoff=2)``
#              returns ``{duplicate_labels, similar_labels,
#              duplicate_ids}``. Label normalisation strips
#              leading emoji and lowercases; similarity uses a
#              bounded Levenshtein with cutoff to keep the scan
#              O(N²) but cheap on the 200-row catalog.
#
#          Admin API — new endpoints in
#          ``src/api/v1/admin/styles.py``:
#            * ``GET /api/v1/admin/styles/lint`` — bulk lint,
#              returns ``{style_id: [issues]}`` for non-clean
#              rows.
#            * ``GET /api/v1/admin/styles/{id}/lint`` — single
#              style, used by the editor's debounced live banner.
#            * ``GET /api/v1/admin/styles/conflicts`` — naming
#              conflict report for the ConflictsAdminPage.
#            * Validation extended: ``_validate_admin_shape``
#              rejects unknown channels in
#              ``available_channels`` and bogus
#              ``location_type`` values with HTTP 422 before
#              the file is touched.
#
#          Admin frontend:
#            * ``web/src/pages/admin/StylesAdminPage.tsx``
#              extended with: lint summary banner (errors +
#              warnings + dirty count), per-row lint badge
#              (green «clean» / red «NE» / amber «NW»),
#              "Show only with issues" filter, header link to
#              the conflicts page, third tab in the editor
#              ("v3 / channels") with location_type dropdown,
#              7-channel checkbox grid, trigger_pool array
#              editor (add/remove rows with live
#              TRIGGER_DIRTY warnings inline), scene_anchor +
#              scene_overrides editors, 4 ambient pool inputs
#              (greyed when channel disabled), "Fill 4
#              seasons" shortcut, debounced live lint banner
#              above the form.
#            * New ``web/src/pages/admin/ConflictsAdminPage.tsx``
#              at ``/admin/conflicts`` — three sections
#              (duplicate labels, similar labels with
#              Levenshtein distance column, duplicate IDs);
#              clickable rows for jump-to-editor.
#            * ``web/src/lib/api.ts`` — new types
#              ``AdminLintIssue`` / ``AdminLintReport`` /
#              ``AdminConflictReport`` and helpers
#              ``lintAllAdminStyles`` /
#              ``lintOneAdminStyle`` /
#              ``listAdminStyleConflicts``;
#              ``StyleOptionsV3Payload`` gains
#              ``available_channels`` and ``location_type``.
#            * ``web/src/App.tsx`` registers the new
#              ``/admin/conflicts`` route.
#
#          User-facing modal:
#            * ``StyleSettingsModal`` reads
#              ``options.availableChannels`` from the v3
#              payload. When non-empty the modal hides every
#              channel that is NOT in the list (regardless of
#              pool contents). Empty list = legacy fallback
#              kept intact. Direct fix for the
#              ``mirror_aesthetic`` symptom: the moment the
#              operator drops ``season`` from
#              ``available_channels``, the «Сезон» pill group
#              disappears for end-users without a redeploy.
#
#          Tests (newly added):
#            * ``test_services/test_style_lint.py`` — 19 unit
#              tests covering every issue code + clean cases +
#              all three conflict buckets (Cyrillic +
#              emoji-prefix normalisation included).
#            * ``test_prompts/test_slot_sampler_channels.py``
#              — 6 tests pinning the curated/fallback contract
#              (mirror_aesthetic-style indoor-without-season
#              case is the headline assertion).
#            * ``test_api/test_admin_lint.py`` — 7 tests
#              covering bulk + single lint, conflict report
#              shape, and the admin validation gates.
#            * ``test_styles_v3_data.py`` extended with two
#              tests for ``available_channels`` /
#              ``location_type`` shape on disk.
#
#          Documentation:
#            * ``docs/prompt-pipeline-v3.md`` gains
#              "Available channels" and "Admin curation
#              workflow" sections.
#            * New ``docs/admin-styles.md`` — operator guide
#              covering catalog navigation, every lint code
#              with severity table, conflicts report, and
#              common workflows ("add new outdoor style" / "fix
#              mirror_aesthetic" / "after editing JSON by
#              hand").
#
#          Out of scope for this release (deliberately):
#            * Curation of the 126 existing styles — done by
#              operators through the new admin UI, separate
#              follow-up. ``available_channels=[]`` on those
#              rows means "не курировано" and the legacy
#              behaviour kicks in.
#            * Postgres-backed style storage — JSON remains
#              the source of truth.
#            * Universal admin auth — still relies on the
#              ``ADMIN_USER_IDS`` whitelist.
#
#          Rollback:
#            * ``available_channels: tuple[str, ...] = ()``
#              defaults to the legacy heuristic, so even if
#              every other change is reverted but somebody
#              already saved curated values, the runtime is
#              unaffected.
#            * Admin endpoints live in their own router prefix
#              and are gated by ``require_admin``; they do not
#              touch the user-facing pipeline.
#            * ``git revert`` of this version returns 1.28.0
#              behaviour without data loss.
#
#          Test counts: 2002 backend tests pass (was 1966 at
#          1.28.0); +34 from the new lint / sampler-channels /
#          admin-lint suites and the v3 schema-data extensions.
#          ``ruff`` clean, ``tsc -b && vite build`` clean
#          (500 modules).
# 1.30.0 — Bulk curation pass for data/styles.json. The 1.29.0
#          admin tooling shipped with 0/126 styles actually
#          curated — ``available_channels`` and ``location_type``
#          were unset on every row, so the slot sampler kept
#          falling back to the legacy "non-empty pool ⇒ enabled"
#          heuristic and ``mirror_aesthetic`` continued to expose
#          a 2-value «Сезон» pill group to users despite being
#          an indoor style. This release closes that gap.
#
#          One-shot data migration in
#          ``scripts/migrations/2026_05_styles_curation/``:
#            * ``audit.py`` — read-only diagnostic, prints
#              dirty-style counts + lint code histogram +
#              conflict report.
#            * ``migrate.py`` — applies the curated defaults
#              deterministically. Per style: classify
#              ``location_type`` (document / indoor / outdoor /
#              mixed via the loader's ``_infer_location_type``
#              with extended id-based hints), pick
#              ``available_channels`` from the per-location
#              template, drop ambient channels with empty pools
#              to avoid ``EMPTY_POOL`` errors, fill 4 seasons
#              when ``season`` is enabled but its pool is short.
#              Trigger cleanup is conservative: drop framing /
#              lighting / weather / season-tainted phrases iff
#              the pool has at least one clean alternative left
#              (single-phrase pools are kept as-is — the
#              operator handles those via the admin UI).
#            * ``preview_lint.py`` — dry-applies the migration
#              in memory and shows before/after lint counts so
#              the change is reviewable without touching disk.
#            * ``unclassified.py`` — debug helper that lists
#              the styles ``_infer_location_type`` couldn't
#              place; used during heuristic tuning.
#
#          Loader heuristic upgrades
#          (``src/services/style_loader_v3.py``):
#            * ``_INDOOR_HINT_TOKENS`` extended with shop /
#              boutique / lounge / gallery / clinic / hospital /
#              stage / venue / podium / armchair / bookshelves
#              + studio-prop terms (ring light, exposed brick,
#              marble surface) for catalog rows whose
#              ``scene_anchor`` lists props instead of saying
#              "studio".
#            * ``_OUTDOOR_HINT_TOKENS`` extended with piazza /
#              crosswalk / balcony / yacht / deck / bicycle /
#              meadow / grass / sea / ocean / tropical /
#              landmark / blue sky / clear sky / etc.
#            * New ``_INDOOR_ID_HINTS`` / ``_OUTDOOR_ID_HINTS``
#              consulted when the scene-anchor scan misses but
#              the style id makes the intent obvious (e.g.
#              ``warm_outdoor`` whose anchor is just lighting
#              prose, but the id literally says "outdoor").
#            * New ``_AMBIGUOUS_MIXED_HINTS`` for catalog
#              entries that genuinely span both contexts
#              (instagram_aesthetic / architecture_shadow /
#              decision_moment / shopfront / stage); these
#              get classified as ``mixed`` rather than left
#              unclassified so the lint engine has something
#              to anchor on.
#
#          Catalog state after migration:
#            * ``available_channels`` populated on 121 / 126
#              rows (the 5 document styles correctly stay
#              empty — they're scene-locked).
#            * ``location_type`` populated on 126 / 126 rows.
#            * Distribution: 71 indoor, 47 outdoor, 5 document,
#              3 mixed, 0 unclassified.
#            * Lint: 8 warning-level ``TRIGGER_DIRTY`` issues
#              left, all on single-phrase trigger pools where
#              auto-cleanup would destroy meaning. These need
#              semantic rewrites in the admin UI, not script
#              work; offending styles include athens_acropolis,
#              decision_moment, panoramic_window, rooftop_city,
#              speaker_stage, tinder_pack_rooftop_golden,
#              tinder_top, warm_outdoor.
#            * Conflicts: 1 duplicate display_label (cycling vs
#              cycling_social — both «🚴 Велопрогулка»), 2
#              similar pairs (near_car ~ in_car, podcast ~
#              podcast_host); flagged for operator review via
#              the conflicts page.
#
#          Direct user impact:
#            * ``mirror_aesthetic`` — operator's headline
#              complaint — now classifies as indoor with
#              ``available_channels = [lighting, time_of_day,
#              framing, clothing, scene_override]``. The
#              «Сезон» and «Погода» pill groups disappear from
#              StyleSettingsModal automatically.
#            * Outdoor styles (paris_eiffel, dubai_burj_khalifa,
#              etc.) get the full 4-season pool by default, so
#              «4 сезона а не 2» is enforced via lint and via
#              the actual data.
#            * Document styles (passport_rf, visa_us, etc.) get
#              ``available_channels = []`` so the modal hides
#              every ambient control — they always go through
#              ``scene_preserve`` mode anyway.
#
#          Rollback:
#            * The migration is data-only (and the loader
#              heuristic upgrade is a strict superset of 1.29.0).
#              ``git revert`` of this commit restores the
#              1.29.0 catalog with no schema breakage.
#            * Admin operators can also undo per-style edits
#              via the editor — the 1.29.0 admin path is
#              unchanged.
#
#          Test counts: 2002 backend pytest pass (unchanged —
#          the migration is data, not behaviour). ``ruff`` /
#          ``tsc --noEmit`` clean.
# 1.30.1 — Catalog hygiene patch. Cleans up the residue 1.30.0
#          deliberately left for the operator: 8 single-phrase
#          ``TRIGGER_DIRTY`` warnings + the 3 naming conflicts
#          surfaced by ``find_conflicts``. Pure content edit;
#          no Python / TS code touched, no schema change.
#
#          Trigger-pool rewrites — each of the 8 styles below
#          had its trigger pool collapsed to a single phrase
#          that copied the whole ``scene_anchor`` (including
#          lighting / framing tokens). This release replaces
#          each one with three clean paraphrases of the
#          inviolable motif so the sampler still has variety
#          and the lint engine no longer warns. Lighting /
#          backlight prose is preserved in ``ambient.lighting``
#          where it belongs:
#            * athens_acropolis  — Acropolis-on-hilltop variants
#              without "warm light".
#            * decision_moment   — large-window pose without
#              "warm rim light".
#            * panoramic_window  — floor-to-ceiling window
#              variants without "rim light".
#            * rooftop_city      — rooftop+skyline variants
#              without "warm lights".
#            * speaker_stage     — podium+screen variants
#              without "from above".
#            * tinder_pack_rooftop_golden — open-air rooftop
#              variants without "rim light".
#            * tinder_top        — uncluttered outdoor framing
#              variants without "backlight".
#            * warm_outdoor      — foliage+water variants
#              without "backlight" / "rim light".
#
#          Display-label deduplication:
#            * ``cycling`` (mode=dating) renamed
#              ``🚴 Велопрогулка → 🚴 Велосвидание`` so it no
#              longer collides with ``cycling_social``
#              (mode=social), which keeps the original label.
#            * ``near_car`` "🚗 У машины" → "🚗 Возле авто"
#              and ``in_car`` "🚘 В машине" → "🚘 За рулём".
#              Levenshtein distance jumps from 2 to >5; the
#              two scenes (рядом с авто / за рулём) read
#              clearly distinct in the modal.
#            * ``podcast_host`` (mode=social) "🎧 Подкаст" →
#              "🎙 За микрофоном"; the cv-mode ``podcast``
#              "🎧 Подкастер" stays untouched. Different
#              emoji family + different focus removes the
#              similarity warning.
#
#          Catalog state after this release:
#            * Lint: 0 dirty styles, 0 issues
#              (was 8 / 8 in 1.30.0).
#            * Conflicts: 0 duplicate labels, 0 similar labels,
#              0 duplicate IDs (was 1 / 2 / 0).
#            * ``available_channels`` / ``location_type``
#              coverage unchanged at 121 / 126 and 126 / 126.
#
#          Rollback:
#            * Pure JSON edit + a one-line APP_VERSION bump.
#              ``git revert`` restores 1.30.0 instantly with no
#              consumer-side migration needed.
#            * The renamed labels are referenced by id
#              everywhere (the ``display_label`` is purely
#              cosmetic), so no analytics / billing / share
#              link breaks.
#
#          Test counts: 2002 backend pytest pass (unchanged).
#          ``ruff`` clean for src/ + tests/. ``tsc --noEmit``
#          clean. ``audit.py`` reports the catalog as fully
#          green for the first time since the 1.28.0 migration.
# 1.30.2 — Style-curation wrap-up patch. Closes the residual
#          items left after 1.30.1 so the next release cycle
#          can move on to scaling work without the catalog
#          carrying half-finished hygiene debt.
#
#          ``scene_anchor`` cosmetic cleanups (4 styles):
#            * ``evening_home`` — "warm ambient lamp lighting"
#              → "warm ambient lamp glow".
#            * ``studio`` (smooth gradient backdrop) —
#              "smooth gradient lighting" → "smooth gradient
#              backdrop falloff".
#            * ``formal_portrait`` — "classic Rembrandt
#              lighting with gentle fill" → "classic Rembrandt
#              sidelight with gentle fill" (Rembrandt sidelight
#              is the same photographic term, just without the
#              "lighting" word that tripped the regex).
#            * ``neutral_bg`` — "even lighting from both sides"
#              → "even illumination from both sides".
#
#          Lint regression budget tightened
#          (``tests/test_styles_v3_data.py``):
#            * ``MAX_DIRTY_SCENE_ANCHORS = 45 → 4``. The
#              remaining four are inherent to the style
#              identity and intentionally retained:
#              ``nyc_brooklyn_bridge`` (golden sunset),
#              ``sf_golden_gate`` (fog), ``sunset_beach``
#              (golden sunset), ``rain`` (in light rain).
#              Touching them would change the visual concept,
#              not just the wording.
#
#          Location reclassification (1 style):
#            * ``decision_moment`` — ``location_type``
#              ``mixed → indoor``. The pose is "standing at a
#              large window overlooking the cityscape", which
#              is structurally indoor (person is inside, looking
#              out). The ``available_channels`` set is identical
#              for ``mixed`` and ``indoor`` so behaviour is
#              unchanged; this is a metadata correction so the
#              admin lint / conflict reports stay accurate.
#
#          Deliberately deferred:
#            * ``quality_identity.base`` coverage — 0 / 100 v3
#              styles have a non-empty value. The model wrapper
#              falls back to ``_MODEL_DEFAULT_TAIL`` when empty
#              (see ``src/prompts/model_wrappers.py:75-77``)
#              and that fallback is correct for every model
#              currently wired up. Filling per-style tails
#              requires A/B generation tests, not a batch
#              script — punted to a separate QA-driven effort.
#
#          Catalog state after this release:
#            * Lint: 0 dirty styles, 0 issues (unchanged).
#            * Conflicts: 0 / 0 / 0 (unchanged).
#            * Dirty scene anchors: 8 → 4 (50% reduction).
#            * Locations: 72 indoor, 47 outdoor, 5 document,
#              2 mixed (was 71 / 47 / 5 / 3 in 1.30.1).
#
#          Tests: 2002 backend pytest pass (unchanged). Ruff
#          clean. ``tsc --noEmit`` clean. Pure data + one
#          test-budget edit; ``git revert`` restores 1.30.1
#          with no consumer-side migration needed.
# 1.31.0 — Wave 1 of the Wizard UX Polish + Theme Rollout.
#          Pure-frontend release: backend, prompt pipeline and
#          style catalog are untouched. The wizard now scrolls
#          as one continuous page, the upload step matches the
#          analysis step's two-column layout, the result step
#          drops the Result/Original toggle in favour of a
#          single vertical action stack, and the style-settings
#          modal stops rendering a white native ``<select>`` in
#          dark theme. Wave 2 (1.32.0) will add a real
#          ``ThemeProvider``, a sun/moon toggle in the NavBar
#          and migrate ``glass-btn-*`` use-sites onto Button /
#          Card / Select React primitives.
#
#          AppPage shell (``web/src/pages/AppPage.tsx``):
#            * Root ``h-dvh ... overflow-hidden`` →
#              ``min-h-dvh`` (no overflow). ``<main>`` no
#              longer constrains height; ``<motion.div>`` no
#              longer ships its own ``overflow-y-auto``. The
#              page now produces a single browser scrollbar
#              that pulls header / StepBar / step content
#              together, matching the screenshots requested.
#            * ``NavBar`` wrapped in a ``sticky top-0 z-[100]``
#              shell so navigation stays pinned during scroll.
#            * ``goToStep`` calls ``window.scrollTo`` instead of
#              the now-defunct inner ``scrollRef``; ``scrollRef``
#              and its ``ref`` attribute removed.
#            * Inner content padding bumped to
#              ``var(--space-24)`` mobile / 48px tablet — more
#              "воздуха" between StepBar and step body.
#
#          Step-1 / Upload (``StepUpload.tsx``):
#            * Switched from a single 600px column to a 2-column
#              flex (mirrors ``StepAnalysis``). Left column =
#              260px photo / dropzone + ``Далее`` (full-width
#              within column); right column = ``Требования к
#              фото`` and ``Не будет обработано`` cards plus
#              ``Заменить фото`` (full-width). Mobile collapses
#              to single column.
#            * Requirements / reject lists wrapped in
#              ``glass-card`` panels for visual parity with
#              the rest of the wizard.
#
#          Step-2 / Analysis (``StepAnalysis.tsx``):
#            * One-line fix: ``items-start`` on the
#              ``flex-col tablet:flex-row`` container so the
#              left photo card stops stretching to the height of
#              the right results panel. Removes the empty grey
#              column under the photo flagged in the screenshot.
#
#          Step-3 / Style (``StepStyle.tsx``):
#            * Removed ``flex-1 min-h-0 overflow-y-auto`` from
#              the styles list — the step inherits the page
#              scroll. Outer container gap bumped to
#              ``var(--space-24)`` between heading / cards /
#              CTAs.
#
#          Step-5 / 6 / Generate (``StepGenerate.tsx``):
#            * Removed ``h-full ... overflow-y-auto`` from the
#              root and ``shrink-0`` from the photo column —
#              one page-level scroll only, more vertical
#              spacing between sections.
#            * Result view: dropped the ``Результат / Исходное``
#              tab toggle and the associated ``viewTab`` /
#              ``setViewTab`` / ``showingOriginal`` state. The
#              user always sees the result; comparison now
#              happens via ``StepBar`` thumbnails.
#            * Result actions reorganised into two vertical
#              stacks **under** the photo (matched to the
#              260px photo column width):
#                – Stack 1 (primary): ``Скачать фото``
#                  (glass-btn-primary) + ``Поделиться``
#                  (glass-btn-ghost), full-width buttons.
#                – Stack 2 (secondary): ``Другое фото`` /
#                  ``Другой стиль|формат`` / ``Другой вариант`` /
#                  ``Настройки`` / ``Улучшить ещё``, plus the
#                  document-scenario ``Открыть AI Look Studio``
#                  link, all full-width.
#            * ``ResolvedSlotsBadges`` now renders between the
#              two stacks, anchored under the primary actions.
#            * Old "CTA buttons" wrap-flex group below the
#              start-generation CTA removed — the new vertical
#              stack inside the photo column is the single
#              source of truth.
#
#          StyleSettingsModal (``StyleSettingsModal.tsx``):
#            * Replaced the native ``<select>`` for the
#              "Освещение" channel with a local
#              ``Dropdown`` component: glass-card popover,
#              click-outside / Escape-to-close, dark-theme
#              hover states. Fixes the white OS menu that
#              appeared on top of the dark modal in the
#              Windows screenshot. The component is local to
#              this file by design — it will be extracted into
#              ``components/ui/Select.tsx`` in Wave 2.
#            * Replaced the four hard-coded literals
#              (``#E6EEF8``, ``rgba(255,255,255,0.05)``,
#              ``rgba(255,255,255,0.1)``, ``#7BA8FF``) with
#              semantic Tailwind tokens (``text-text-primary``,
#              ``bg-surface-2``, ``border-border-base``,
#              ``text-brand-primary`` / ``bg-brand-primary``).
#              The drag-handle stripe in the mobile sheet uses
#              ``bg-border-strong`` instead of a 20%-opacity
#              white literal. After this patch the modal has
#              no theme-dependent literals and will follow
#              ``data-theme`` automatically once Wave 2 ships
#              the toggle.
#
#          Out-of-scope (deliberately deferred to Wave 2):
#            * ``ThemeProvider`` + sun/moon toggle in NavBar.
#              ``data-theme="dark"`` still hard-coded on
#              ``<body>`` in ``web/index.html``.
#            * React primitives (``Button``, ``Card``,
#              ``Select``, ``Modal``) under
#              ``web/src/components/ui/`` and progressive
#              migration of ``glass-btn-*`` / ``glass-card``
#              use-sites.
#            * Full-app sweep of hardcoded ``#hex`` and
#              ``rgba(...)`` literals in
#              ``NavBar.tsx`` / ``Footer.tsx`` /
#              ``AuthModal.tsx`` / ``Landing`` / ``Hero`` etc.
#
#          Tests: ``tsc --noEmit`` clean,
#          ``vite build`` clean (76.62 kB CSS gzip 14.70 kB,
#          715 kB JS gzip 210.21 kB), ``ruff check src tests``
#          clean, ``pytest tests/test_api/
#          tests/test_orchestrator/`` 104 passed / 54 skipped
#          (no backend changes). Pure UI release; ``git revert``
#          restores 1.30.2 with no consumer-side migration.
# 1.31.1 — Wave 1.5 UX polish — фронтенд-only follow-up к 1.31.0 по
#          обратной связи пользователя. Backend (prompt engine,
#          slot sampler) не трогали — качественные проблемы
#          (winter↔одежда, «вклеенное фото») вынесены в Wave 2.
#
#          StepGenerate (``web/src/components/wizard/StepGenerate.tsx``):
#            * Удалена кнопка ``Другой вариант`` вместе с
#              ``handleReroll`` и сопутствующим ``lastInputHints``
#              state-ом + двумя effect-ами сброса. Кнопка
#              запускала полную (платную) генерацию через
#              ``app.generate(undefined, style, hints, freshSeed)``,
#              что не соответствовало ожиданиям пользователя
#              ("just another option" → новое списание кредита).
#              Альтернативный путь к re-roll-у — открыть
#              "Настройки", применить — это явный consent.
#            * Вторичный стек кнопок результата перепорядочен
#              от наименее радикального к самому радикальному:
#              ``Улучшить ещё`` → ``Настройки`` → ``Другой стиль |
#              формат`` → ``Другое фото`` (+ опциональный
#              ``Открыть AI Look Studio`` для document-сценария).
#              Прежний порядок (``Другое фото`` первым) вынуждал
#              пользователя сбрасывать прогресс, чтобы добраться
#              до самой частой операции — улучшения.
#            * ``setLastInputHints(hints)`` убран из ``onApply``
#              модалки — хинты по-прежнему долетают до текущей
#              генерации, но больше не «помнятся» для
#              несуществующего reroll-а.
#
#          StyleSettingsModal (``web/src/components/wizard/StyleSettingsModal.tsx``):
#            * ``hasClothing`` теперь смотрит только на
#              ``available_channels`` для curated-стилей
#              (``isCurated ? curatedChannels.includes('clothing')
#              : (options?.clothing?.length ?? 0) > 0``). Раньше
#              поле скрывалось, когда ``clothing.allowed`` пуст,
#              но channel разрешён — на ``paris_eiffel``,
#              ``dubai_burj_khalifa`` и других landmark-стилях
#              пользователь физически не мог задать одежду
#              (особенно нужно при ``season=winter``, чтобы не
#              получить летнюю футболку среди снега). Free-text
#              input теперь виден всегда, chips-suggestions
#              показываются только при непустом пуле.
#            * Popover локального ``Dropdown`` сменён с
#              ``glass-card`` (``rgba(255,255,255,0.03)`` +
#              ``backdrop-filter: blur(...)``) на solid
#              ``bg-surface-1`` + ``shadow-[var(--effect-elevation-2)]``.
#              Внутри родительского ``glass-card``-модала
#              вложенный backdrop-filter не работает (CSS spec:
#              nested filter context создаёт новый stacking
#              boundary, blur не наследуется), поэтому popover
#              был почти прозрачным и наезжал на текст модалки.
#              Solid-фон + elevation-shadow дают надёжную
#              визуальную сепарацию слоёв.
#
#          StepUpload (``web/src/components/wizard/StepUpload.tsx``):
#            * Симметричная 2x2-раскладка вместо асимметричной
#              двухколонки 1.31.0. Top row на tablet+:
#              ``[260px фото-карточка][flex-1 стэк из 2
#              gradient-border-card]`` с ``items-stretch`` —
#              высота фото подстраивается под суммарную высоту
#              стэка, исчезает «лесенка». Bottom row:
#              ``[260px Далее primary][flex-1 Заменить фото
#              ghost]`` — оба CTA в той же колоночной системе
#              координат. На mobile стекается в одну колонку,
#              порядок сохраняется. До загрузки фото нижний ряд
#              скрывается (нечего «Далее»).
#
#          AppPage (``web/src/pages/AppPage.tsx``):
#            * Tablet+ vertical air обрезан с
#              ``gap-[48px] / py-[48px]`` (96 + 48 = 144px) до
#              ``gap-[var(--space-24)] / py-[var(--space-24)]``
#              (24 + 24 = 48px). Снимает «полпустой страницы»
#              при коротком контенте — пользователь жаловался
#              на «скролл по пустоте». Mobile gap/py остались на
#              ``var(--space-24)`` (без изменений).
#            * Добавлен ``overflow-x-hidden`` на root —
#              подстраховка от горизонтального скролла из-за
#              popover-ов и mesh-gradient-а.
#
#          Theme switcher (``web/src/lib/theme.tsx`` +
#          ``web/src/main.tsx`` + ``web/index.html`` +
#          ``web/src/sections/NavBar.tsx``):
#            * Новый файл ``lib/theme.tsx`` с ``ThemeProvider``
#              (React Context) и хуком ``useTheme()``. Initial
#              читается из ``document.documentElement.dataset.theme``
#              (если уже выставлен FOUC-скриптом), затем из
#              ``localStorage.getItem('theme')``, затем из
#              ``matchMedia('(prefers-color-scheme: light)')``,
#              fallback — ``dark``. На каждом ``setTheme``
#              атрибут пишется на ``<html>`` и persist в
#              localStorage.
#            * Inline-script в ``<head>`` ``index.html``
#              выставляет ``data-theme`` до первого paint —
#              FOUC prevention без бандлера. ``data-theme="dark"``
#              убран из ``<body>``: теперь источник истины —
#              ``<html>``, что синхронно с
#              ``document.documentElement``-логикой провайдера.
#              ``main.tsx`` оборачивает ``<App>`` в
#              ``<ThemeProvider>``.
#            * NavBar получил локальный ``ThemeToggle``
#              (sun/moon SVG), вставлен в desktop-группу перед
#              language-switcher (mode='app' и 'landing') и в
#              mobile-группу перед бургером.
#              ``aria-label`` зависит от текущей темы. Wave 2
#              проведёт полный sweep хардкодов под токены —
#              сейчас light-режим читаем, но местами шероховатый
#              (text-[#E6EEF8] и rgba(...)-литералы остались).
#
#          Tests: ``tsc --noEmit`` clean,
#          ``vite build`` clean (76.88 kB CSS gzip 14.73 kB,
#          717 kB JS gzip 210.64 kB), ``ruff check src tests``
#          clean, ``pytest tests/test_api/
#          tests/test_orchestrator/`` 104 passed / 54 skipped
#          (no backend changes). Pure UI release; ``git revert``
#          восстанавливает 1.31.0 без миграций. Backend
#          quality-issues (winter↔одежда, «вклеенное фото»),
#          full color-hardcode sweep и React-примитивы
#          (``Button`` / ``Card`` / ``Select``) — Wave 2 (1.32.0).
# 1.32.0 — Wave 2 итерация 1: Pipeline integrity + scroll fix.
#          Подготовительный релиз перед coherence (1.32.1) и
#          scene integration (1.32.2). Ни одна A/B-метрика
#          качества не должна сместиться — проверка инвариантов.
#
#          AppPage scroll-в-никуда (``web/src/pages/AppPage.tsx``):
#            * Удалён ``<EnergyField />`` из AppPage. Компонент
#              рендерит 10 absolute-блобов с ``top: 5vh ... 340vh``
#              внутри ``<main>`` без ``overflow: hidden``, что
#              расширяло document.documentElement до ~3400px и
#              давало пользователю «скролл по пустоте» на коротком
#              wizard-шаге (видно на скриншоте после 1.31.1).
#              Mesh gradient (``MeshGradientBg``) остаётся —
#              он ``position: fixed`` и не растягивает документ.
#              EnergyField по-прежнему рендерится на длинных
#              лендингах (``Landing.tsx`` / ``DocumentPhotoLanding.tsx``),
#              там 340vh-блобы вписаны в реальную высоту страницы.
#
#          Полный ResolvedSlots payload в API
#          (``src/prompts/composition_builder.py``,
#          ``src/prompts/engine.py``,
#          ``web/src/lib/api.ts``):
#            * ``CompositionIR`` получил опциональное поле
#              ``resolved_slots: object | None`` — v3 builder
#              кладёт туда полный ``ResolvedSlots`` инстанс,
#              v2 builder оставляет ``None`` (чистая обратная
#              совместимость). До 1.32.0 IR схлопывал
#              trigger/time_of_day/season в строку ``scene``,
#              и UI badges не видели эти каналы по отдельности
#              даже в v3-генерациях.
#            * ``PromptEngine.build_image_prompt_v2`` теперь
#              форвардит ``ir.resolved_slots.to_dict()`` целиком
#              в ``out_resolved_slots`` (если IR пришёл от v3).
#              Поля: ``trigger`` / ``scene`` / ``lighting`` /
#              ``weather`` / ``time_of_day`` / ``season`` /
#              ``clothing`` / ``expression`` / ``random_picks`` /
#              ``user_overrides`` / ``substitutions``. Defensive
#              fallback на старую IR-derived dict, если IR без
#              resolved_slots (на случай тестовых v2 IR-ов).
#            * ``web/src/lib/api.ts``: ``ResolvedSlots`` тип
#              расширен теми же полями + ``random_picks`` и
#              ``user_overrides`` как ``Record<string, string>``,
#              ``substitutions`` как массив. UI badges
#              (``ResolvedSlotsBadges.tsx``) уже умели рендерить
#              trigger/time_of_day/season — теперь они реально
#              получают эти данные.
#
#          v1 fallback decommission (``src/orchestrator/executor.py``,
#          ``src/metrics.py``):
#            * Новый Prometheus counter
#              ``ratemeai_prompt_v1_fallback_total`` с label-ами
#              ``mode`` и ``style``. После v2-cutover эта ветка
#              должна давать 0 hits в проде.
#            * При попадании в legacy ``_build_mode_prompt``
#              executor пишет ``logger.warning("v1_prompt_fallback_hit")``
#              с контекстом (mode, style, variant_id, ab_image_model)
#              и инкрементит счётчик. Если за неделю Grafana
#              покажет 0 hits — ветка удаляется в 1.33.1.
#
#          Тесты (``tests/test_prompts/test_v3_composition.py``):
#            * ``test_engine_forwards_full_resolved_slots_payload``
#              — все 11 ключей ``ResolvedSlots.to_dict()``
#              присутствуют в ``out_resolved_slots``; ambient
#              channels с непустыми пулами раскатываются;
#              random_picks покрывает все каналы при пустых
#              hints; user_overrides пуст.
#            * ``test_engine_seeded_pipeline_is_deterministic`` —
#              same ``(spec, hints, seed)`` → same prompt + same
#              resolved_slots на повторных запусках; разные seed
#              → разные prompt-ы (контракт антирепита).
#            * ``test_engine_user_overrides_partition_resolved_slots``
#              — пин канала через ``input_hints`` падает в
#              ``user_overrides``, не в ``random_picks``.
#
#          Sanity: ``tsc --noEmit`` clean, ``vite build`` clean
#          (76.88 kB CSS gzip 14.73 kB, 717 kB JS gzip 210.65 kB),
#          ``ruff check src tests`` clean, ``pytest tests/test_api/
#          tests/test_orchestrator/ tests/test_prompts/``
#          1568 passed / 54 skipped (3 новых теста). ``git revert``
#          восстанавливает 1.31.1 без миграций — изменения
#          обратно-совместимы (новые поля resolved_slots
#          опциональны для UI, EnergyField возвращается одной
#          строкой).
#
#          Следующая итерация (1.32.1) — cross-channel coherence
#          (``CoherenceRule`` в StyleSpecV3, правила
#          season→clothing/lighting/weather; ревизия
#          ``data/styles.json`` под winter-стили). После неё
#          1.32.2 — scene integration anchors (light wrap,
#          ambient occlusion, contact shadows, per-model tails).
# 1.32.1 — Wave 2 итерация 2: Cross-channel coherence.
#          Решает «winter↔linen» класс конфликтов: до 1.32.1 v3
#          schema по дизайну сэмплировал каналы независимо
#          (``ambient`` каналы — это «по дизайну отсутствует
#          coherence»). Это давало максимальное first-roll
#          разнообразие, но допускало сочетания вида
#          ``season=winter`` + ``clothing="white linen"`` на
#          яхте. 1.32.1 вводит **opt-in** coherence слой,
#          сохраняя независимость как default.
#
#          Schema (``src/prompts/style_schema_v3.py``):
#            * Новый ``@dataclass(frozen=True) CoherenceRule``
#              с полями:
#               - ``season: str`` — целевой сезон, который
#                 триггерит правило (case-insensitive match
#                 на rolled ``season``).
#               - ``clothing_override: dict[str, str]`` —
#                 per-gender замена дефолтной одежды.
#                 Применяется только если пользователь не
#                 пинал ``clothing_override``.
#               - ``lighting_filter`` / ``weather_filter`` /
#                 ``time_of_day_filter`` — opt-in whitelist
#                 для канала. Если original roll вне whitelist
#                 (и пользователь не пинал) — re-roll из
#                 whitelist той же RNG (детерминизм seed
#                 сохраняется).
#            * ``StyleSpecV3.coherence: tuple[CoherenceRule, ...]``
#              — пустой tuple = legacy behavior (все каналы
#              независимы). ``__post_init__`` валидирует
#              non-empty season и unique seasons на правило.
#
#          SlotSampler (``src/prompts/slot_sampler.py``):
#            * Новый ``_apply_coherence`` post-processing шаг
#              после независимого сэмплинга. Применяется
#              только когда ``spec.coherence`` непуст И
#              ``ambient.season`` rolled.
#            * Precedence (вшита в логику):
#               user_override > coherence > random_pool > default
#            * Все coherence-патчи логируются в
#              ``ResolvedSlots.substitutions`` с channel-именами
#              ``coherence_clothing`` / ``coherence_lighting`` /
#              ``coherence_weather`` / ``coherence_time_of_day``,
#              чтобы executor мог отрисовать UI-уведомление с
#              другим тоном, чем при out-of-pool soft-substitute.
#
#          JSON loader (``src/services/style_loader_v3.py``):
#            * Новый ``_coherence_rules`` парсер для массива
#              ``coherence`` в JSON-стиле. Толерантен к
#              malformed entries (логирует и дропает).
#            * Wired в ``_to_v3`` builder.
#
#          Data (``data/styles.json`` — 21 стиль обновлён):
#            * Скрипт-ревизия
#              ``scripts/migrations/2026_05_coherence/audit_seasonal_clothing.py``
#              нашёл 15 v3-стилей с конфликтом winter↔summer-coded
#              clothing.
#            * ``migrate.py`` (idempotent) применил два класса
#              правок:
#               1) Удалил ``winter`` из ``ambient.season`` для
#                  5 семантически невозможных winter-сценариев:
#                  yacht, beach_sunset, swimming_pool,
#                  sea_balcony, singapore_marina_bay (тропики).
#               2) Добавил ``coherence`` правила для 21 outdoor
#                  стиля под winter-генерации:
#                  paris_eiffel, dubai_burj_khalifa, nyc_*
#                  (3 шт), tokyo_tower, sf_golden_gate,
#                  rome_colosseum, venice_san_marco,
#                  barcelona_sagrada, athens_acropolis,
#                  sydney_opera + summer-rule для
#                  london_eye / london_big_ben +
#                  4 outdoor-активности (running, tennis,
#                  cycling, motorcycle, hiking) + travel_blogger,
#                  hotel_breakfast.
#               Каждое правило содержит per-gender (male/
#               female/neutral) clothing_override (wool coat /
#               winter parka / thermal kit) — модель получает
#               сезонно-корректную фразу.
#
#          Тесты (``tests/test_prompts/test_coherence.py``):
#            * 9 unit-тестов покрывают:
#               - winter-rule replaces summer linen на yacht
#               - summer-rule replaces snow boots на ski
#               - substitution log получает channel
#                 ``coherence_clothing``
#               - user pin на ``clothing_override`` побеждает
#                 coherence (override > coherence)
#               - season не совпал с правилом → fallback на
#                 default (без coherence-логов)
#               - lighting_filter re-rolls off-filter value
#               - lighting_filter оставляет уже-в-фильтре
#                 значение нетронутым
#               - lighting_filter уважает user pin
#               - seeded determinism сохраняется
#
#          Sanity: ``tsc --noEmit`` clean, ``vite build`` clean
#          (76.88 kB CSS gzip 14.73, 717 kB JS gzip 210.65),
#          ``ruff check src tests`` clean,
#          ``pytest tests/test_api/ tests/test_orchestrator/
#          tests/test_prompts/ tests/test_services/``
#          1714 passed / 54 skipped (9 новых coherence + старые
#          v3 регрессии). ``git revert`` чисто восстанавливает
#          1.32.0; ``data/styles.json`` ревёрнется через тот же
#          revert (поля coherence просто перестанут читаться
#          loader-ом, но он их толерирует).
#
#          Risk: правила coherence могут переопределить
#          пользовательский clothing_override — UNIT-тесты
#          подтверждают precedence override > coherence >
#          default. A/B пользователя на winter-генерациях
#          подтвердит, что одежда теперь сезонная.
#
#          Следующая итерация (1.32.2) — scene integration
#          anchors (SCENE_BLEND_PHOTO с light wrap, ambient
#          occlusion, contact shadows; разведение
#          QUALITY_PHOTO_GPT vs QUALITY_PHOTO_NANO).
# 1.32.2 — Wave 2 итерация 3: Scene integration anchors.
#          Решает «вклеенное фото» класс жалоб: до 1.32.2
#          ``LIGHT_INTEGRATION_PHOTO`` давал общую фразу про
#          highlights / shadows / color cast, но не использовал
#          film-industry термины для compositing, которые модели
#          лучше парсят. 1.32.2 вводит новый
#          ``SCENE_BLEND_PHOTO`` anchor — отдельный, длинный,
#          с пятью обязательными терминами (edge light wrap,
#          ambient occlusion, contact shadows, color grading
#          match, atmospheric depth). Best-practices сверка:
#            * Nano Banana 2 (Gemini) prompt guide прямо
#              упоминает edge light / ambient occlusion / color
#              grading match.
#            * GPT Image 2 предпочитает narrative («key and
#              fill lighting», «atmospheric depth»).
#            * FLUX Kontext positive-framing only — anchor
#              целиком positive (нет no/without/avoid/don't).
#
#          Anchor (``src/prompts/image_gen.py``):
#            * Новая константа ``SCENE_BLEND_PHOTO``
#              (~580 chars, ~140 tokens) с film-industry
#              compositing-терминами. Размещена между
#              LIGHT_INTEGRATION и CAMERA так, чтобы
#              cinematography-блок был непрерывным
#              (lights → wrap → camera → anatomy).
#
#          Per-model wrappers (``src/prompts/model_wrappers.py``):
#            * ``QUALITY_PHOTO_GPT`` и ``QUALITY_PHOTO_NANO``
#              были до 1.32.2 byte-for-byte идентичны
#              (намеренно, ради v2 parity-теста). Теперь оба
#              embed ``SCENE_BLEND_PHOTO``. Вариация per-model
#              tail зарезервирована, текст идентичен
#              (отдельные константы оставляют возможность
#              разойтись в будущем без breaking changes).
#            * Новый ``QUALITY_PHOTO_FLUX`` константа +
#              ``wrap_for_flux_kontext`` функция +
#              ``wrap_for_model("flux_kontext", ...)`` ветка.
#              FLUX route добавлен на случай активации
#              executor-маршрута через FAL.
#
#          Тесты:
#            * ``tests/test_prompts/test_scene_blend.py`` —
#              10 smoke-тестов:
#                - anchor содержит все 5 compositing-терминов;
#                - anchor positive-framed (no negative tokens);
#                - per-model tails (GPT/Nano/FLUX) embed anchor;
#                - per-model wrappers сохраняют термины после
#                  compress_prompt + _truncate;
#                - DOC styles НЕ embed anchor (DOC_PRESERVE /
#                  DOC_QUALITY bypass);
#                - prompt budget < 2000 chars (≈ 480 tokens),
#                  ≤ PROMPT_MAX_LEN.
#            * ``tests/test_prompts/test_schema_v2_parity.py``
#              обновлён: parity-тесты ``test_v2_matches_v1_*``
#              стрипают SCENE_BLEND_PHOTO из v2 output перед
#              сравнением с v1 (v1 — frozen legacy fallback,
#              его не апдейтим).
#
#          Sanity: ``ruff check src tests`` clean,
#          ``vite build`` clean, ``pytest tests/test_api/
#          tests/test_orchestrator/ tests/test_prompts/
#          tests/test_services/`` 1724 passed / 54 skipped
#          (10 новых scene_blend + старые v3/coherence
#          регрессии).
#
#          Risk: SCENE_BLEND ~140 токенов добавляет к prompt
#          ≈ 40-50% длины. Замерено — типичный final prompt
#          ~1560 chars, остаётся ~940 chars headroom до
#          PROMPT_MAX_LEN=2500. A/B пользователя на 10+
#          генерациях с одинаковыми seed-ами до/после
#          подтвердит «вклеенность» лучше или хуже.
#
#          Следующая итерация (1.33.0) — UI primitives
#          (Button / Card / Select / Field / Modal / Divider)
#          и color-sweep wave 1 (миграция модалок на токены).
# 1.33.0 — Wave 2 итерация 4: UI primitives + color sweep wave 1.
#          Frontend-only релиз (backend пайплайн не трогается).
#          Закладывает design-system fundament для последующих
#          sweep-волн в 1.33.1+.
#
#          UI primitives (``web/src/components/ui/``):
#            * ``Button.tsx`` — варианты ``primary | secondary |
#              ghost | danger | success | glass``, размеры
#              ``sm | md | lg``. Все классы через токены
#              (``--color-brand-primary``, ``--color-text-primary``,
#              ``--color-danger``) — никаких хардкодных хексов.
#            * ``Card.tsx`` — варианты ``glass | solid |
#              gradient-border``, наследует ``glass-card`` для
#              совместимости.
#            * ``Select.tsx`` — обобщённый popover-dropdown,
#              извлечён из локального ``Dropdown`` в
#              ``StyleSettingsModal`` (1.31.0). Surface через
#              ``bg-[var(--color-surface-1)]`` +
#              ``shadow-[var(--effect-elevation-2)]`` —
#              решает 1.31.0 жалобу на полупрозрачный popover.
#            * ``Field.tsx`` — лейбл + control + helper/error
#              (layout-only, не дублирует input-стили).
#            * ``Modal.tsx`` — единая основа для AuthModal /
#              StorageModal / ReviewModal / ShareModal /
#              StyleSettingsModal: backdrop, framer-motion,
#              portal, esc-to-close, body-scroll-lock.
#            * ``Divider.tsx`` — горизонтальный/вертикальный
#              разделитель, замена inline-style ``rgba(...)`` в
#              5+ местах NavBar.
#            * ``index.ts`` — barrel export.
#
#          Color tokens:
#            * ``--color-danger`` / ``--color-danger-soft`` —
#              алиасы для существующих ``danger-base`` /
#              ``danger-surface`` (упрощают import в Tailwind).
#            * ``web/tailwind-core.config.cjs`` —
#              ``danger`` / ``danger-soft`` маппинг.
#
#          Modal sweep wave 1:
#            * ``AuthModal.tsx`` — ``text-[#E6EEF8]`` →
#              ``text-[var(--color-text-primary)]``,
#              ``text-[#FF4D6A]`` → ``text-[var(--color-danger)]``.
#            * ``StorageModal.tsx`` — text-токены.
#            * ``ReviewModal.tsx`` — text-токены.
#            * ``ShareModal.tsx`` — text-токены.
#            * ``StyleSettingsModal.tsx`` — локальный ``Dropdown``
#              удалён, используется ``<Select>`` из ``ui/``.
#
#          Sanity: ``tsc --noEmit`` clean, ``vite build`` clean
#          (717 kB main, оптимизация — итерация 5),
#          ``ruff check src tests`` clean,
#          ``pytest tests/test_api/ tests/test_orchestrator/
#          tests/test_prompts/`` 1587 passed / 54 skipped
#          (backend не трогали — никаких регрессий).
#
#          Risk: чисто JSX/CSS изменения, ``git revert`` чисто
#          восстанавливает. Light-mode читабельность модалок
#          улучшилась (text-token инвертируется через
#          ThemeProvider).
#
#          Следующая итерация (1.33.1) — sweep wave 2:
#          NavBar / Hero / Pricing / Footer / wizard-шаги
#          + bundle code-splitting (admin chunk + framer-motion
#          chunk, цель <500 kB main) + удаление v1 fallback
#          если PROMPT_V1_FALLBACK метрика подтвердила 0 hits.
# 1.33.1 — Wave 2 итерация 5: Sweep wave 2 + hygiene + bundle split.
#          Закрывает Wave 2: оставшиеся хардкоды → токены, очистка
#          theme CSS, code-splitting в Vite. Frontend-only
#          (backend пайплайн не трогается).
#
#          Color sweep wave 2:
#            * NavBar.tsx — 18× ``text-[#E6EEF8]`` →
#              ``text-[var(--color-text-primary)]``, 8×
#              ``hover:bg-[rgba(255,255,255,0.06)]`` →
#              ``hover:bg-[var(--color-surface-hover)]``,
#              2× ``text-[#FF4D6A]`` →
#              ``text-[var(--color-danger)]``, dropdown menu
#              surface ``rgba(12, 16, 24, 0.95)`` →
#              ``bg-[var(--color-surface-1)]`` + elevation,
#              6 inline-divider ``rgba(255,255,255,0.08)`` →
#              ``bg-[var(--color-border-base)]``,
#              mobile-drawer ``rgb(8, 12, 18)`` →
#              ``bg-[var(--color-bg-base)]``.
#            * Sections (Hero / Pricing / Footer / Simulation /
#              SocialProof / HowItWorks) — text-token sweep.
#            * Wizard (StepUpload / StepGenerate / StepStyle /
#              StepAnalysis / StepDocumentFormat / StylesSheet /
#              StepBar) — 12+6+6+7+2+3+3 ``#E6EEF8`` →
#              ``var(--color-text-primary)``,
#              ``#FF9EAD`` (Не будет обработано) →
#              ``var(--color-danger)``.
#            * Pages / components (Landing / Toast / AuthCallback /
#              ConsentGate / LinkPage / CategoryTabs /
#              ResolvedSlotsBadges / PaymentSuccess /
#              PrivacyPolicy / DocumentPhotoLanding /
#              ShareButtons / LinkedAccountsPanel) — text-token
#              sweep + LinkedAccountsPanel inline-style buttons →
#              ``bg-[var(--color-surface-2)]`` +
#              ``border-[var(--color-border-base)]``.
#            * Admin pages (StylesAdminPage /
#              ConflictsAdminPage) — преднамеренно не тронуты,
#              они lazy-loaded и идут в ``admin`` chunk
#              (см. §5.3).
#
#          Theme CSS hygiene:
#            * Удалён избыточный ``@media (prefers-color-scheme:
#              dark) :root:not([data-theme="light"])`` в
#              ``design-tokens.css``. FOUC-script в
#              ``index.html`` всегда выставляет ``data-theme``,
#              поэтому media-query никогда не активировался.
#              Заменён на короткий комментарий о причине удаления.
#
#          Bundle code-splitting:
#            * ``vite.config.ts`` — ``manualChunks(id)``:
#                - ``framer-motion`` отдельным chunk-ом
#                  (~138 kB / 46 kB gzip) — загружается всегда,
#                  но кэшируется отдельно и не пересобирается
#                  при правке любого React-кода.
#                - ``react-router-dom`` + ``@remix-run`` →
#                  ``router`` chunk (~50 kB / 18 kB gzip).
#                - ``/src/pages/admin/*`` → ``admin`` chunk
#                  (~35 kB / 10 kB gzip), пользователи не
#                  скачивают.
#            * ``App.tsx`` — ``StylesAdminPage`` и
#              ``ConflictsAdminPage`` обёрнуты в
#              ``React.lazy() + Suspense`` с локальным
#              ``AdminFallback`` спиннером. До этого они шли в
#              main bundle и тянулись на каждую загрузку.
#
#          Bundle size (до → после):
#            * main:    717 kB → 498 kB (-30%)
#              gzip 211 kB → 140 kB (-34%)
#            * framer-motion: split → 138 kB / 46 kB gzip
#            * router: split → 50 kB / 18 kB gzip
#            * admin: split → 35 kB / 10 kB gzip
#            * total served на user-path: ~140 kB + 46 kB +
#              18 kB = 204 kB gzip (vs 211 kB до). Admin chunk
#              теперь грузится только админами.
#            * Vite chunk-size warning (>500 kB) больше не
#              срабатывает.
#
#          V1 prompt fallback (defer):
#            * ``_build_mode_prompt`` остаётся на месте.
#              ``PROMPT_V1_FALLBACK`` метрика добавлена только в
#              1.32.0 (этот же session), нужна минимум неделя
#              прод-данных для подтверждения 0 hits перед
#              удалением. Решение: следить за метрикой; если
#              через неделю в Prometheus 0 — удалить в патч-релизе
#              1.33.2.
#
#          Sanity: ``tsc --noEmit`` clean,
#          ``vite build`` clean (498 kB main, no warnings),
#          ``ruff check src tests`` clean,
#          ``pytest tests/test_api/ tests/test_orchestrator/
#          tests/test_prompts/`` 1587 passed, 54 skipped
#          (backend не трогался — никаких регрессий).
#
#          Risk: чисто frontend изменения, ``git revert`` чисто
#          восстанавливает. Light-mode легибильность по всему
#          консумерскому пути (NavBar / wizard / sections)
#          улучшилась. Admin-роуты теперь имеют 100ms задержку
#          первой отрисовки (Suspense fallback) при первом
#          переходе — приемлемо для админов, и кэш браузера
#          обнуляет это после первого визита.
# 1.34.0 — Theme System Overhaul, итерация 1: glass-tokens + light
#          mirror. До этой версии светлая тема меняла только цвет
#          текста — потому что .glass-* классы (15 штук) и fallback-
#          блоки в ``web/src/index.css`` были построены на
#          ``rgba(255,255,255,...)`` поверх dark-фона и
#          ``rgba(0,0,0,...)`` тенях. На light это давало серую муть
#          и инверсия не работала. Симметричного ``[data-theme=
#          "light"]`` override-блока не было.
#
#          Что сделано:
#            * Введены семантические glass-токены в
#              ``[data-theme="dark"]`` блоке и зеркальный
#              ``[data-theme="light"]`` блок: ``--glass-surface``,
#              ``--glass-surface-hover``, ``--glass-surface-strong``,
#              ``--glass-surface-soft``, ``--glass-border``,
#              ``--glass-border-hover``, ``--glass-border-soft``,
#              ``--glass-inset-highlight`` /
#              ``--glass-inset-highlight-soft``,
#              ``--glass-shadow-soft``, ``--glass-shadow-card``,
#              ``--glass-shadow-nav``, ``--glass-nav-surface``,
#              ``--glass-footer-surface``,
#              ``--glass-divider-surface``,
#              ``--glass-fallback-surface`` /
#              ``--glass-fallback-nav`` /
#              ``--glass-fallback-footer`` /
#              ``--glass-fallback-divider``, ``--glass-text``.
#            * Light-палитра: «белое матовое стекло» (вариант А по
#              запросу) — ``rgba(255,255,255,0.55..0.75)`` поверх
#              светлых ``--color-bg-base``, тени
#              ``rgba(15,23,42,0.08..0.12)``.
#            * Все .glass-* классы (.glass, .glass-btn-secondary,
#              .glass-btn-ghost, .glass-card, .glass-card-highlight,
#              .glass-tab-active, .glass-row, .glass-row-active,
#              .glass-badge[-cyan/-success/-info/-danger],
#              .glass-nav, .glass-footer, .glass-divider,
#              .glass-progress-track / .glass-progress-fill-muted,
#              .social-proof-feed-item) переключены с rgba-хардкодов
#              на токены.
#            * .glass-btn-primary сохраняет accent-градиент (он
#              brand-mark, theme-agnostic), но drop-shadow-слой
#              переведён на ``var(--glass-shadow-soft)``, чтобы
#              светлая тема не получала избыточно тёмную тень.
#            * ``color: #E6EEF8`` внутри .glass-btn-secondary и
#              .glass-btn-ghost → ``var(--glass-text)``. White текст
#              в .glass-btn-primary остался — primary всегда белый
#              по дизайну.
#            * Fallback-блоки ``@supports not (backdrop-filter)`` и
#              ``@media (prefers-reduced-transparency: reduce)``
#              переведены с хардкодных ``rgba(17,24,32,...)`` /
#              ``rgba(10,14,20,...)`` на token-aware
#              ``var(--glass-fallback-*)``.
#
#          Sanity: ``tsc --noEmit`` clean, ``vite build`` clean
#          (498 kB main, 78 kB CSS, no warnings, no regressions в
#          разделении чанков). Backend не трогался.
#
#          Risk: чисто CSS-переменные, ``git revert`` восстанавливает
#          предыдущее поведение без структурных изменений. Возможный
#          визуальный артефакт в light — недостаточно контрастные
#          границы у .glass-row на больших серых поверхностях; A/B
#          тюнингуется через ``--glass-border``/``--glass-border-soft``
#          без re-deploy логики. Mesh-фон (``.mesh-gradient-layer``)
#          ещё хардкодит ``#0A0E14`` — это сделано в 1.34.1.
# 1.34.1 — Theme System Overhaul, итерация 2: mesh-фон + декоративные
#          слои + sweep оставшихся TSX-хардкодов. После 1.34.0 светлая
#          тема корректно меняла ``.glass-*`` поверхности, но
#          фиксированный mesh-слой и SVG-noise все ещё хардкодили
#          dark-палитру и затемняли всё, что под ними.
#
#          Что сделано:
#            * ``.mesh-gradient-layer`` (web/src/index.css) — финальный
#              radial-gradient теперь использует ``var(--mesh-base)``
#              вместо ``#0A0E14``. Каждая тема задаёт свою базу
#              (``--color-bg-base``) и opacity blob-ов:
#              ``--mesh-blob-accent-opacity`` (0.08 dark / 0.05 light),
#              ``--mesh-blob-accent-sec-opacity``,
#              ``--mesh-blob-violet`` и ``--mesh-blob-magenta``.
#              Light-вариант использует более яркие но менее насыщенные
#              blob-цвета (rgba(168,85,247,0.05) violet,
#              rgba(236,72,153,0.04) magenta) — это даёт деликатные
#              акценты вместо «грязных пятен» от хардкодного
#              dark-фиолетового.
#            * ``EnergyField.tsx`` — нейтральные blob-ы используют
#              theme-aware ``--energy-neutral-r/g/b`` (60,20,180 в dark
#              и 168,85,247 в light) вместо хардкода ``rgba(60,20,180,
#              opacity)``. Per-blob opacity по-прежнему задаётся в TS
#              (нужно для разных blob-ов), но base RGB меняется с темой.
#            * ``.section-noise-bg`` — добавлен симметричный
#              ``[data-theme="light"] .section-noise-bg`` блок с
#              инвертированной SVG noise-палитрой: финальный stop
#              ``rgba(247,248,250,1)`` вместо ``rgba(22,30,40,1)``,
#              opacity 0.06 вместо 0.1. Без этого SVG-углы выглядели
#              чёрными квадратами на светлом фоне.
#            * ``.howworks-gradient-backdrop`` — magenta-blob теперь
#              ``var(--howworks-blob-magenta)`` (тот же violet в light
#              для гармонии с mesh).
#
#          TSX sweep (доделано из плана §2.5):
#            * StepGenerate.tsx — placeholder bg
#              ``rgba(255,255,255,0.02)`` → ``var(--glass-surface-soft)``;
#              SVG circle stroke в error-overlay
#              ``stroke="rgba(255,255,255,0.3)"`` →
#              ``stroke="currentColor" strokeOpacity="0.3"``;
#              gradient overlay ``linear-gradient(to top, rgba(0,0,0,0.7))``
#              → Tailwind utility ``bg-gradient-to-t from-black/70``.
#              Чёрные overlay-градиенты над фотографиями оставлены
#              theme-agnostic (это photo-darkening для читаемости).
#            * StepBar.tsx — circle border
#              ``border-[rgba(255,255,255,0.12)]`` →
#              ``border-[var(--color-border-base)]``;
#              text-white активного шага → ``text-[var(--color-text-on-brand)]``
#              (тёмный текст на cyan brand-bg, AA-контраст);
#              line-fill ``rgba(255,255,255,0.04..0.08)`` → токены.
#            * Simulation.tsx — 2 placeholder ``rgba(255,255,255,0.02)``
#              → ``var(--glass-surface-soft)``;
#              ``--gb-color`` для unselected gradient-border-card →
#              ``var(--glass-border-hover)``.
#            * StylesSheet.tsx — drag handle ``rgba(255,255,255,0.2)``
#              → ``var(--glass-border-hover)``;
#              ``--gb-color`` для unselected style → token;
#              «Скоро» badge bg → ``var(--glass-surface-strong)``.
#            * StepUpload / StepAnalysis — photo-card placeholder bg
#              → ``var(--glass-surface-soft)``;
#              StepAnalysis loading state circles
#              ``border-[rgba(255,255,255,0.1)]`` →
#              ``border-[var(--glass-border)]``.
#            * StepStyle.tsx — framing selector container
#              ``bg-[rgba(255,255,255,0.03)]`` →
#              ``bg-[var(--glass-surface-soft)]``;
#              border-t ``rgba(255,255,255,0.05)`` →
#              ``var(--glass-border-soft)``.
#            * StepDocumentFormat.tsx, DocumentPhotoLanding.tsx —
#              ``--gb-color`` для unselected → ``var(--glass-border-hover)``.
#            * ReviewModal.tsx — 2 photo placeholder bg → token.
#            * StorageModal.tsx — photo placeholder bg + pagination
#              dots non-active state → tokens.
#            * LinkPage.tsx — 3 input field bg/border → ``--glass-*``
#              tokens. Brand-OAuth кнопки (Yandex/VK/phone) оставлены
#              с фиксированными цветами — они brand-identity.
#            * LinkedAccountsPanel.tsx — provider-row bg →
#              ``var(--glass-surface)``.
#            * ShareButtons.tsx — circle button bg + border → tokens.
#            * Toast.tsx — ``rgba(34,197,94,0.15)`` (success) /
#              ``rgba(59,130,246,0.15)`` (info) /
#              ``rgba(234,179,8,0.15)`` (warning) bg-классы переведены
#              на ``var(--glass-surface-strong)`` + border через
#              ``color-mix(in srgb, var(--color-success-base) 30%,
#              transparent)``. Иконки ``#22c55e/#3b82f6/#eab308`` →
#              ``var(--color-success-base)/info-base/warning-base``.
#
#          Что осталось theme-agnostic (by design):
#            * Photo overlays (StepGenerate AI badge, StorageModal
#              nav arrows ``bg-black/55``, failed-tile gradient) —
#              чёрное затемнение над фотографиями работает в обеих
#              темах.
#            * Brand-OAuth кнопки (Google #fff, Yandex #FC3F1D,
#              VK #0077FF, phone #4ADE80) — фиксированные brand-
#              identity цвета по гайдлайнам провайдеров.
#            * ``.glass-btn-primary`` accent-градиент (cyan→magenta).
#            * ``.gradient-text``, ``.gradient-border-*``.
#            * Admin pages (StylesAdminPage / ConflictsAdminPage)
#              в lazy ``admin`` chunk — out of scope этой итерации.
#
#          Sanity: ``tsc --noEmit`` clean, ``vite build`` clean
#          (498 kB main, 82 kB CSS — +3 kB от новых токенов и
#          light-варианта section-noise SVG, gzip 15 kB → 15.5 kB,
#          приемлемо). Backend не трогался.
#
#          Risk: light-mode mesh может казаться слишком блёклым на
#          крупных мониторах; mitigation — opacity-токены
#          (``--mesh-blob-*-opacity``) подкручиваются без re-deploy.
#          Для аб-теста легко переключить значения.
# 1.34.2 — Theme System Overhaul, итерация 3: AICADS sync, dead-
#          hardcodes verification, ThemeProvider cross-tab sync,
#          docs.
#
#          Что сделано:
#            * Сверка ``web/src/design-tokens.css`` против
#              ``AICADS-/packages/core/ai-ds-styles.json`` — все
#              light-токены mirror AICADS spec 1:1
#              (``color_bg_base.light = core_white``,
#              ``color_text_primary.light = core_gray_95 = #353535``,
#              ``color_surface_2.light = core_gray_5_alt = #F7F8FA``,
#              ``color_border_base.light = core_gray_15 = #E5E7EB``,
#              brand ``core_brand_50 = #00F0FF`` идентичен в обеих
#              темах). Dark-токены в ``design-tokens.css`` тоже
#              соответствуют AICADS, но в ``index.css``
#              ``[data-theme="dark"]`` есть документированный
#              «AI Look Studio» override (``#0A0E14`` вместо AICADS
#              ``#161E28``) — это интенционально, более глубокий
#              эстетический выбор продукта.
#            * Финальный grep хардкодов в ``web/src/`` — 0 цветовых
#              хардкодов вне:
#                - admin pages (``StylesAdminPage.tsx`` /
#                  ``ConflictsAdminPage.tsx``) — out of scope, lazy
#                  ``admin`` chunk;
#                - brand-OAuth кнопки и иконки провайдеров (Yandex,
#                  VK, Telegram, Google, OK, WhatsApp, Zalo, Line)
#                  — by design (brand identity);
#                - photo overlays (``bg-black/...`` над
#                  фотографиями) — by design;
#                - accent-градиенты (``glass-btn-primary``,
#                  ``gradient-text``, ``gradient-border-*``) — by
#                  design.
#            * StepAnalysis.tsx — soft-warnings panel (warning
#              triangle) ``stroke="#FFC27A"``,
#              ``text-[#FFD6A8]`` → ``text-[var(--color-warning-base)]``,
#              ``stroke="currentColor"``.
#              ``--gb-color: rgba(255,190,120,0.35)`` →
#              ``color-mix(in srgb, var(--color-warning-base) 35%,
#              transparent)``.
#            * PrivacyPolicy.tsx — 3 ссылки ``text-[#60A5FA]`` →
#              ``text-[var(--color-link-default)]``.
#            * ThemeProvider (``web/src/lib/theme.tsx``) — добавлен
#              ``window.addEventListener('storage', ...)`` listener.
#              Если пользователь переключает тему в одной вкладке,
#              остальные синхронизируются автоматически. JSDoc
#              обновлён (Wave 2 sweep уже сделан в 1.33.x).
#            * ``index.css`` — добавлен заголовок-комментарий
#              «Theme tokens (1.34.2)» с правилами для новых
#              компонентов: «only ``var(--color-*)`` /
#              ``var(--glass-*)``, no hardcoded ``#...`` /
#              ``rgba(255,255,255,...)`` outside accent-градиентов
#              и documented theme-agnostic exceptions».
#            * Удалён избыточный JSDoc «Wave 2 (1.32.0) проведёт
#              полный sweep» в theme.tsx — sweep уже сделан в
#              1.33.0/1.33.1/1.34.0.
#
#          Sanity:
#            * ``tsc --noEmit`` clean.
#            * ``vite build`` clean (498 kB main / 81 kB CSS,
#              splitting chunks intact).
#            * ``ruff check src tests`` clean.
#            * ``pytest tests/test_api/ tests/test_orchestrator/
#              tests/test_prompts/`` — 1587 passed, 54 skipped
#              (backend нетронут).
#
#          Risk: low. Чистый verification + единичные точечные
#          fix-ы (StepAnalysis warnings, PrivacyPolicy links,
#          theme cross-tab sync). ``git revert`` чисто откатывает
#          ThemeProvider listener при подозрении на гонки.
#
#          Theme System Overhaul завершён. Глобально:
#            * v1.34.0 — glass-tokens + light mirror
#              ([data-theme="light"] block).
#            * v1.34.1 — mesh-фон + декоративные слои + TSX sweep.
#            * v1.34.2 — verification + cross-tab sync + docs.
#          Светлая тема теперь полностью функциональна, primary
#          brand-colors идентичны в обеих темах, фон/поверхности/
#          glass меняются как ожидается.
# 1.35.0 — Ambient ParticleBackground (premium subtle mode).
#          Новый фоновой слой с 250 (desktop) / 100 (mobile) мелкими
#          частицами на flow-field из 2D simplex-noise. Цель —
#          ощущение «живой цифровой среды» / «AI / data system»,
#          без визуального шума и не отвлекая от UI.
#
#          Что сделано:
#            * ``web/src/components/effects/ParticleBackground.tsx`` —
#              Canvas 2D рендерер. Inline simplex-noise (~150 строк,
#              public domain Stefan Gustavson), wraparound-движение,
#              theme-aware цвет/opacity через CSS-токены.
#            * RAF-loop с rolling avg FPS-window (60 кадров). Если
#              avg < 45 → halve density (250→125→63...) one-shot.
#            * Scroll-input: deltaY → velocityBoost 1.0 → 1.2 (clamp),
#              лёгкая направленность вниз пропорциональна
#              ``scrollDirection``. Exponential decay back to 1.0
#              ~1.5s после остановки скролла.
#            * ``prefers-reduced-motion: reduce`` → return null
#              (canvas вообще не создаётся).
#            * ``MutationObserver`` на ``<html>`` data-theme attribute
#              — palette swap происходит без re-mount: на dark
#              ``rgba(255,255,255,0.05-0.15)``, на light
#              ``rgba(15,23,42,0.04-0.10)``.
#            * Particle size 1-2px, размер 3px только для 5%
#              «акцентных» частиц.
#            * НЕТ connections (lines между частицами), НЕТ pulse/
#              flash, НЕТ per-particle alpha-osc — спека прямо
#              запрещает.
#
#          Tokens:
#            * ``index.css`` ``[data-theme="dark"]`` и
#              ``[data-theme="light"]`` блоки получили
#              ``--particle-color``, ``--particle-opacity-min``,
#              ``--particle-opacity-max``. Композитор читает их
#              ``getComputedStyle`` при init и при theme-change через
#              ``MutationObserver``.
#
#          Mounting (важно — scope):
#            * ``Landing.tsx`` и ``DocumentPhotoLanding.tsx`` —
#              ``<ParticleBackground/>`` добавлен как 2-й
#              decorative layer, между ``<MeshGradientBg/>`` и
#              ``<EnergyField/>``.
#            * AppPage **НЕ** трогается. Там в 1.32.0 был
#              зафиксирован баг «scroll to nowhere» при
#              абсолютно-позиционированных слоях в скролл-
#              контейнере wizard-а. ParticleBackground тоже
#              ``position: fixed`` и теоретически безопасен, но
#              для изоляции рисков в этой итерации добавляем
#              только на лендинги. AppPage particle-фон —
#              отдельная итерация после A/B оценки лендингов.
#
#          z-stack (все ``pointer-events: none``):
#            * mesh-gradient-bg: z:0 (статичный градиент-фон).
#            * particle-background: z:1 fixed (мелкие частицы).
#            * energy-field: z:1 absolute, после в DOM (крупные
#              blob-ы, follow-mouse).
#
#          Sanity: ``tsc --noEmit`` clean, ``vite build`` clean
#          (502 kB main / 82 kB CSS, +4 kB / +2 kB gzip — в пределах
#          плана <5 kB gzip). Backend не трогался.
#
#          Risk: low. Particles это purely additive layer;
#          ``git revert`` чисто восстанавливает предыдущее
#          поведение лендингов. Возможный визуальный артефакт —
#          частицы могут показаться слишком блёклыми на
#          крупных мониторах в light theme; mitigation —
#          ``--particle-opacity-*`` token tweak без re-deploy.
# 1.36.0 — Theme-aware PNG (hybrid: dual-asset для logo,
#          CSS filter для placeholder-иллюстраций) + увеличенный
#          ThemeToggle.
#
#          Logo (brand-critical → dual-asset):
#            * ``web/scripts/generate-light-logo.mjs`` — одноразовый
#              build-time скрипт (jimp 1.6.1 как devDep). Алгоритм:
#              luminance-only inversion (Rec. 601), сохраняем
#              chroma direction → cyan-glow остаётся cyan, но
#              «тёмная подложка → светлая, светлый текст → тёмный».
#              Альфа не трогается.
#            * ``web/src/assets/logo-light.png`` (~587 kB) сгенерирован
#              этим скриптом и закоммичен в репозиторий. Запуск
#              ``npm run generate:light-logo`` нужен только при
#              обновлении исходного logo.png.
#            * ``web/src/lib/themedAsset.ts`` — хук ``useThemedLogo()``,
#              возвращающий правильный src по активной теме.
#            * ``NavBar.tsx`` и ``Landing.tsx`` — заменён прямой
#              ``import logo from '../assets/logo.png'`` на
#              ``useThemedLogo()``. Также ``mixBlendMode`` сделан
#              theme-aware: ``lighten`` на dark, ``darken`` на
#              light (тёмные части лого впечатываются в белый фон).
#
#          Placeholder illustrations (CSS filter, variant A):
#            * ``index.css`` — новый класс ``.theme-adaptive-png``,
#              читающий ``var(--png-filter, none)``.
#            * ``[data-theme="light"]`` — ``--png-filter: brightness
#              (1.05) contrast(0.92) saturate(0.9)`` (мягкий тон-
#              матчинг, без агрессивного inversion — спека прямо
#              запрещает).
#            * Применено к 7 ``<img>`` в:
#                - ``StepGenerate.tsx`` (placeholder-upgrade × 2 —
#                  без агрессивного inline-blur loading-shimmer; тот
#                  оставлен как есть, его inline-filter и так задаёт
#                  собственный визуал).
#                - ``StepAnalysis.tsx`` (placeholder-upload × 1).
#                - ``ReviewModal.tsx`` (placeholder-upload + upgrade).
#                - ``Simulation.tsx`` (placeholder-upload + upgrade).
#
#          ThemeToggle bigger:
#            * Размер кнопки переключения темы увеличен до полно-
#              ценного button-size: 40×40px на desktop (было 36),
#              48×48px на mobile (было 44). Иконка 20-22px вместо
#              18, чтобы переключатель не «терялся» среди CTA-кнопок
#              и предлагал комфортный touch-target.
#
#          Sanity: ``tsc --noEmit`` clean, ``vite build`` clean (502.79
#          kB main / 82.24 kB CSS, +0.3 kB main / +0.04 kB CSS gzip).
#          Both logo PNGs хешируются Vite раздельно — браузер грузит
#          фактически отображаемый, второй on-demand при theme-swap.
#          ``ruff check`` clean. Backend нетронут.
# 1.37.0 — Revert 1.35.0 + 1.36.0: убран Ambient ParticleBackground
#          и theme-aware PNG hybrid system по обратной связи
#          пользователя — оба эффекта «выглядят ужасно» в проде.
#          Сохранён только увеличенный ThemeToggle (40/48 px) — он
#          жалоб не получал.
#
#          Что откачено:
#            * ``ParticleBackground.tsx`` удалён, импорт + использо-
#              вание убраны из ``Landing.tsx`` и
#              ``DocumentPhotoLanding.tsx``.
#            * ``--particle-color``, ``--particle-opacity-min``,
#              ``--particle-opacity-max`` токены удалены из обоих
#              ``[data-theme="*"]`` блоков ``index.css``.
#            * ``useThemedLogo`` хук, ``themedAsset.ts``,
#              ``logo-light.png`` (~587 kB), ``scripts/generate-
#              light-logo.mjs``, ``npm run generate:light-logo``
#              скрипт и devDep ``jimp`` удалены.
#            * ``NavBar.tsx`` и ``Landing.tsx`` вернулись к прямому
#              ``import logoSrc from '../assets/logo.png'`` с
#              ``mixBlendMode: 'lighten'`` (как было до 1.36.0).
#            * Класс ``.theme-adaptive-png`` и ``--png-filter``
#              токен удалены из ``index.css``. Класс снят с 7
#              placeholder-img в StepGenerate / StepAnalysis /
#              ReviewModal / Simulation.
#
#          Что сохранено:
#            * ``ThemeToggle`` 40×40 desktop / 48×48 mobile,
#              иконка 20-22 px (1.36.0 part). Жалоб не было.
#
#          Sanity: ``tsc --noEmit`` clean, ``vite build`` clean
#          (498.61 kB main / 81.76 kB CSS / 140.18 kB main gzip —
#          точно совпадает с post-1.34.2 baseline). Backend
#          нетронут.
#
#          Note: light theme сейчас остаётся как в 1.34.2 — logo с
#          ``mixBlendMode: 'lighten'`` на белом фоне может выглядеть
#          бледно, но это исходное поведение. Если нужна следующая
#          итерация по light theme, лучше идти через прямой re-export
#          логотипа в Figma / SVG-версию вместо алгоритмического
#          inversion.
# 1.38.0 — Interactive WebGL Fluid Background (premium subtle).
#          Тонкий cursor-driven «след» поверх mesh-gradient на
#          лендингах, быстро тает, цвета — наши brand primary
#          через ``--accent-r/g/b`` (category-aware).
#
#          Что сделано:
#            * ``web/src/components/effects/FluidBackground.tsx`` —
#              TS-порт Stam-style stable fluids на основе кода
#              Pavel DoGreat (MIT), без bloom/sunrays/capture.
#              ~700 строк, 9 fragment-шейдеров (advection, divergence,
#              curl, vorticity, pressure, gradient-subtract, splat,
#              copy/clear, display).
#            * WebGL2 с фоллбэком на WebGL1 (через
#              ``OES_texture_half_float`` +
#              ``OES_texture_half_float_linear``). Manual-bilinear
#              fallback в advection-шейдере если linear filtering
#              на half-float не поддерживается (iOS Safari).
#            * Конфиг для «не ляписто, органично»:
#              ``DENSITY_DISSIPATION 4.5`` (волна тает ~0.6s),
#              ``VELOCITY_DISSIPATION 2.0`` (движение затухает),
#              ``CURL 8`` (менее «вихревой»),
#              ``SPLAT_FORCE 1500`` (мягкие, не «бьющие»),
#              ``TRANSPARENT true`` (фон прозрачный поверх mesh),
#              ``BLOOM/SUNRAYS false`` (отключены — оба дают
#              «ляписто»).
#            * ``pickSplatColor()`` — кастом вместо random HSV:
#              читает ``--accent-r/g/b`` из computed style → +/-12%
#              jitter → ``themeAlpha = 0.55`` на light (cyan на
#              белом «давит» иначе). Палитра автоматически меняется
#              при смене категории (social=cyan, business=purple,
#              dating=pink, ...).
#            * Interaction model: only pointer-move/down/touch.
#              Никаких auto-splat, никаких scroll-triggered волн.
#              На idle экран чистый — поверх него виден только
#              MeshGradient + EnergyField.
#            * Performance/safety: ``prefers-reduced-motion: reduce``
#              → return null; mobile (``innerWidth<768``) →
#              ``SIM_RESOLUTION=64, DYE_RESOLUTION=512``; FPS-guard
#              one-shot халвит ``DYE_RESOLUTION`` если avg<45 за
#              60 кадров; battery saver — отключает RAF при level<0.2
#              без зарядки (через ``navigator.getBattery()``).
#
#          Mounting:
#            * ``Landing.tsx`` и ``DocumentPhotoLanding.tsx`` —
#              ``<FluidBackground/>`` добавлен между
#              ``<MeshGradientBg/>`` (z:0) и ``<EnergyField/>`` (z:2).
#            * AppPage не трогается — regression risk «scroll to
#              nowhere» из 1.32.0.
#
#          Sanity: ``tsc --noEmit`` clean, ``vite build`` clean
#          (516.75 kB main / 81.76 kB CSS, +18 kB main / +6.2 kB
#          gzip — в пределах плана <12 kB gzip). Backend нетронут.
#
#          Risk: low. Pure additive layer на лендингах,
#          ``git revert`` чисто восстанавливает baseline.
#          Подкрутка ``themeAlpha``/``SPLAT_FORCE`` без redeploy —
#          через CSS-токены или config-pull можно сделать в
#          следующей итерации, если поведение в проде потребует
#          fine-tune.
# 1.39.0 — SVG vectorization: logo + placeholders.
#          Замена 3 PNG-ассетов на inline SVG-компоненты, которые
#          рендерятся идеально в обеих темах без mixBlendMode-хаков
#          и алгоритмических фильтров.
#
#          Bundle:
#            * ``logo.png`` (582 kB) удалён.
#            * ``placeholder-upload.png`` (839 kB) удалён.
#            * ``placeholder-upgrade.png`` (908 kB) удалён.
#            * Итого -2.37 MB raster-ассетов; +4.5 kB main JS /
#              +0.9 kB gzip за inline SVG (LogoEmblem + 2
#              Placeholder-art компонента).
#
#          Что сделано:
#            * ``web/src/assets/LogoEmblem.tsx`` — геометрический
#              monogram «AI» в двойном кольце с soft Gaussian-glow.
#              ``stroke="currentColor"`` для буквенной части
#              (наследует ``color: var(--color-text-primary)``
#              родителя — автоматически тёмный на light и светлый
#              на dark) + ``stroke="var(--color-brand-primary)"``
#              для accent-rings (category-aware: cyan/purple/
#              pink/orange).
#            * ``web/src/components/effects/PlaceholderArt.tsx`` —
#              два минималистичных line-art SVG: ``PlaceholderUpload``
#              (фоторамка с dashed «drop zone» + portrait silhouette)
#              и ``PlaceholderUpgrade`` (та же рамка с radial-glow
#              backdrop + sparkles + accentированный силуэт).
#              Тоже ``currentColor`` + ``var(--color-brand-primary)``.
#
#          Замены:
#            * ``NavBar.tsx`` (×2: button-логотип и Link-логотип) и
#              ``Landing.tsx`` (×1 hero-логотип) — ``<img src=
#              {logoSrc}>`` с ``mixBlendMode: 'lighten'`` заменён на
#              ``<LogoEmblem className="w-full h-full"/>``.
#              Glow-backdrop за emblem-ом смягчён (0.18 → 0.10
#              alpha для NavBar, 0.4 → 0.18 для Hero) — emblem уже
#              имеет встроенный Gaussian-glow.
#            * ``StepGenerate.tsx`` (×3 placeholder-upgrade,
#              включая animated blur-shimmer для error state),
#              ``StepAnalysis.tsx`` (×1 placeholder-upload),
#              ``ReviewModal.tsx`` (×2),
#              ``Simulation.tsx`` (×2). Все 8 ``<img>`` заменены
#              на соответствующие React-компоненты с
#              ``text-[var(--color-text-secondary)]`` для
#              currentColor-наследования.
#
#          Удалены файлы:
#            * ``web/src/assets/logo.png``.
#            * ``web/public/img/placeholder-upload.png``.
#            * ``web/public/img/placeholder-upgrade.png``.
#
#          Эффекты для пользователя:
#            * Logo и иллюстрации идеально вписываются в обе темы
#              без «бледного» mixBlendMode-эффекта или
#              «грязного» CSS-инверта.
#            * Иллюстрации category-aware: при переключении
#              сценария (social → business → dating) accent в
#              placeholder-ах меняется с cyan на purple/pink/orange.
#            * Page load на лендинге быстрее: ~1.7 MB меньше
#              raster-ассетов в начальной загрузке. SVG inline =
#              нет network-roundtrip за placeholder.
#
#          Sanity: ``tsc --noEmit`` clean, ``vite build`` clean
#          (521.28 kB main / 82.01 kB CSS, +4.5 kB main /
#          +0.25 kB CSS / +0.9 kB gzip — в пределах ожиданий по
#          плану). Backend нетронут.
# 1.40.0 — Fluid Background v2: optimisation + visual polish.
#          Точечный релиз поверх 1.38.0 по 5 проблемам обратной
#          связи (сплошной цвет, грязный хвост на light, явный при
#          медленном движении, перекрытие UI, тормоза). Backend и
#          анализ-пайплайн не тронуты.
#
#          Что сделано в ``FluidBackground.tsx``:
#            1. ``pickSplatColor(speed)`` теперь ремиксит каждый
#               splat как случайную точку на нашем brand-gradient
#               ``primary→secondary`` (читает ``--accent-{r,g,b}``
#               и ``--accent-sec-{r,g,b}`` через cache, см. п.5).
#               Подряд несколько splat-ов под мышью = визуально
#               «градиентный хвост», а не одноцветная клякса.
#            2. ``SHADING`` (fake-3D diffuse-кромки) включается
#               только на dark — на light они выглядели «грязно-
#               серыми» поверх белого фона. Реализовано двойной
#               компиляцией display-шейдера (``displayProgShaded``
#               + ``displayProgPlain``); выбор по ``themeCache``
#               на каждом render. ``themeAlpha = 0.55`` в
#               ``pickSplatColor`` убран — за dim'инг на light
#               отвечает ``mix-blend-mode: multiply`` (см. CSS).
#            3. Velocity-throttle в ``applyInputs()``:
#               ``speedSq < 0.0001`` → splat пропускается (медленный
#               курсор за чтением не оставляет следа). Прошедший
#               threshold splat линейно-затемняется по
#               ``min(1, speed * 12)`` → бледный на низких
#               скоростях, насыщенный на жесте.
#            4. RAF-pause idle: после 2 s с последнего pointer-event
#               ``cancelAnimationFrame`` останавливает loop;
#               handlers возобновляют его при следующем move/touch.
#               На статичной странице 0% CPU/GPU вместо 100% RAF.
#            5. Cached accent + ``MutationObserver``:
#               ``getComputedStyle`` теперь вызывается только при
#               init и при изменении ``data-theme`` (<html>) или
#               ``data-category`` (root <div>). ``pickSplatColor``
#               синхронно читает кэш — 0 ns vs ~5-15 µs на
#               ``getComputedStyle`` в горячем пути.
#            6. Deferred resize: ``initFBOs()`` больше не
#               блокирует обработчик ``resize``; перенесено в
#               следующий RAF-кадр.
#            7. Понижен baseline render-cost:
#               ``SIM_RESOLUTION 128 → 96`` (-45% sim fillrate),
#               ``DYE_RESOLUTION 1024 → 768`` (-45% dye fillrate),
#               ``PRESSURE_ITERATIONS 20 → 12`` (Pavel default 20
#               для тяжёлых сцен; для нашего lite-эффекта 12
#               достаточно), ``CURL 8 → 6`` (мягче curl),
#               ``SPLAT_RADIUS 0.20 → 0.18``, ``VELOCITY_DISSIPATION
#               2.0 → 2.5`` (волна тает чуть быстрее). Mobile:
#               ``SIM=48, DYE=384`` (было 64/512).
#            8. Canvas ``z-index: 0`` (было 1) → теперь живёт в
#               одном backdrop-слое с ``.mesh-gradient-bg``.
#               UI-плашки с implicit ``z: auto`` больше не
#               провисают под fluid.
#
#          Что сделано в ``index.css``:
#            * Блок ``.fluid-background`` с ``mix-blend-mode:
#              lighten`` (dark — bright cyan/purple вытягивается
#              поверх тёмной подложки); ``[data-theme="light"]
#              .fluid-background { mix-blend-mode: multiply }``
#              (cyan × white = cyan, без серого «налёта»).
#            * Stacking-guard: ``main > section, main >
#              .glass-divider, .glass-nav { isolation: isolate }``
#              — единый декларативный фикс вместо массового
#              z-index proliferation.
#
#          Эффекты для пользователя:
#            * Цветной градиентный хвост вместо одноцветной
#              кляксы; на light theme — чистые цветные мазки без
#              серого налёта.
#            * Курсор в idle = чистый фон (нет накапливающейся
#              кляксы при медленном движении).
#            * UI-плашки и модалки гарантированно над fluid.
#            * Idle CPU 0% (было ~5% RAF non-stop); active perf
#              -45% fillrate за счёт пониженных resolutions.
#
#          Sanity: ``tsc --noEmit`` clean; ``vite build`` clean
#          (522.42 kB main / 82.23 kB CSS, +0.14 kB main / +0.22 kB
#          CSS — в пределах ожиданий: +cache + observer + speed-
#          scale logic, см. план §6). Out of scope: WebGL2
#          transform-feedback compute pressure-iter, 0.5x canvas
#          downsampling, AppPage-fluid (всё ещё intentionally off).
# 1.41.0 — Rebrand: «AI Look Studio» → «Look Studio» + новый
#          фирменный logo от дизайнера.
#
#          Что сделано:
#            * ``LogoEmblem.tsx`` полностью переписан на основе
#              ``LSLOGO.svg`` (исходник дизайнера): четыре «орбиты»
#              + центральное двойное кольцо. Геометрия inline JSX
#              (нет дополнительного raster/svg ассета). Окрашен
#              одним токеном ``var(--color-brand-primary)`` →
#              category-aware (cyan / purple / pink / orange) +
#              theme-aware. Размер 100% наследуется от родителя
#              (``viewBox="0 0 21 21"``, ``className="w-full
#              h-full"``) — все потребители (NavBar 40-44 px,
#              Landing 60-140 px) рендерятся без изменений.
#              Опциональный Gaussian-glow ``stdDeviation=0.45``
#              для премиальности.
#            * Удалены user-facing вхождения «AI» из бренд-нейма
#              «AI Look Studio» → «Look Studio»:
#              - ``index.html`` <title>;
#              - ``Landing.tsx`` brand-heading;
#              - ``NavBar.tsx`` (×2 logo wordmark; убран
#                раздельный <span>AI</span>);
#              - ``Footer.tsx`` копирайт;
#              - ``PrivacyPolicy.tsx`` legal text;
#              - ``StepGenerate.tsx`` CTA «Открыть Look Studio»;
#              - ``aria-label`` логотипа в ``LogoEmblem.tsx``;
#              - download filenames: ``ai-look-photo.jpg`` →
#                ``look-studio-photo.jpg``, ``ai-look-result.jpg``
#                → ``look-studio-result.jpg``;
#              - e2e smoke-test title regex;
#              - комментарии в ``index.css``.
#            * Удалён ``LSLOGO.svg`` из корня репо — геометрия
#              перенесена inline в TSX, отдельный asset не нужен.
#
#          Что НЕ тронуто (intentionally — это инфраструктура,
#          не user-facing brand):
#            * localStorage-ключи ``ailook_*`` (миграция данных
#              сломала бы все активные сессии).
#            * NPM package name ``@ailook/web`` (internal).
#            * Домен ``ailookstudio.ru`` и ``api.ailookstudio.ru``
#              (DNS / Vercel — менять отдельным релизом).
#            * Telegram bot handle ``@RateMeAIBot`` и
#              VK/OK app slugs (external IDs).
#
#          Sanity: ``tsc --noEmit`` clean; ``vite build`` clean.
#          Backend и анализ-пайплайн нетронуты.
# 1.42.0 — Fluid v3 + logo polish: точечные правки по обратной
#          связи поверх 1.40-1.41. Backend нетронут.
#
#          1. Цвет fluid-эффекта строго совпадает с категорией.
#             В 1.40.0 ``pickSplatColor`` миксил primary↔secondary
#             с random t — это уводило оттенок в дополняющий цвет
#             (для social: cyan→violet), и пользователь воспринимал
#             эффект как «не тот цвет». Возвращён single-hue
#             подход: только primary категории + ±12% jitter по
#             каждому RGB-каналу (мягкий разброс яркости в пределах
#             одного оттенка). Соответствие категория↔цвет
#             эффекта теперь 1:1 (cyan для social, purple для cv,
#             pink для dating, orange для model, и т.д.).
#
#          2. Light theme: убран «грязный» тёмный налёт.
#             Корневая причина — на light theme ``mix-blend-mode:
#             multiply`` превращает любой приглушённый RGB в
#             видимый тёмный цвет на белом фоне (cyan*0.3 = (0,72,
#             76) → multiply white = тёмный teal). 1.40.0
#             ``speedScale`` снижал RGB на медленных движениях,
#             что и давало тот «грязный» серо-teal на скрине.
#             Фикс: на light theme ``speedScale = 1`` всегда —
#             полная saturation цвета. Speed-modulation
#             реализуется только через skip-threshold (медленный
#             курсор просто не делает splat). На dark theme
#             speedScale сохранён — приглушённый цвет на тёмной
#             подложке = soft fade, выглядит красиво.
#
#          3. FluidBackground в AppPage. Раньше было intentionally
#             off (см. 1.38.0 out-of-scope). Теперь смонтирован
#             в ``main`` после ``MeshGradientBg`` — wizard-page
#             получает ту же premium-атмосферу что и Landing.
#
#          4. LogoEmblem без accent-backdrop. Из-под лого убран
#             тонированный квадрат (``rgba(--accent, 0.10)`` в
#             NavBar / 0.18 в Landing) — теперь сам глиф «дышит»
#             на любой подложке. Применено в:
#             ``NavBar.tsx`` (×2 — onHomeClick + Link),
#             ``Landing.tsx`` (×1 — brand heading).
#             ``DocumentPhotoLanding`` использует общий NavBar,
#             правится автоматически.
#
#          NB: Эпизод «на ru-сервере остался старый логотип» —
#          это был кэш браузера юзера. ``ru.ailookstudio.ru``
#          уже на 1.41.0 (verified: ``Last-Modified``, bundle
#          hash ``index-DiJw-6w9.css``). После hard reload
#          обновится.
#
#          Sanity: ``tsc --noEmit`` clean; ``vite build`` clean
#          (524.51 kB main / 81.80 kB CSS, -0.5 kB main / -0.4 kB
#          CSS — секондари-cache + accent-backdrop dropped).
# 1.43.0 — Fluid v4: color-lag fix + ambient idle splats.
#          Backend нетронут.
#
#          1. Цвет fluid-эффекта больше не запаздывает на один шаг.
#             Корневая причина: ``MutationObserver`` срабатывает в
#             microtask до того, как браузер пересчитал computed
#             style для CSS-переменных, изменённых через
#             ``data-category``. ``getComputedStyle()`` в callback'е
#             возвращал СТАРЫЕ значения → ``themeCache.primary``
#             обновлялся с лагом на один step. Фикс: обернули
#             ``refreshThemeCache`` в ``requestAnimationFrame`` —
#             RAF гарантирует, что style commit прошёл, и
#             computed values уже отражают новый ``data-category``.
#
#          2. Эффект больше не «исчезает после первого шага» в
#             AppPage. Корневая причина: RAF-pause idle 2s из 1.40.0
#             — на длинных wizard-шагах (например, ожидание
#             анализа фото) юзер не двигает мышью, dye полностью
#             растворяется, RAF останавливается → визуально пустой
#             фон. Фикс: убран RAF-pause, добавлены ambient idle
#             splats — каждые 4 s в случайной точке viewport'а
#             делается мягкий случайный splat (40% force от
#             user-splat'а, велосити 0.05 = средний), фон всегда
#             «дышит».
#
#             Energy budget: на скрытой вкладке браузер сам не
#             вызывает RAF (нативный pause), так что значимого
#             роста energy-потребления нет. Battery saver и
#             ``prefers-reduced-motion`` из 1.38.0 продолжают
#             корректно отключать эффект на edge-cases.
#
#          NB: «На ru-сервере осталась подложка у логотипа» —
#          снова кэш браузера юзера. ``ru.ailookstudio.ru`` уже
#          на 1.42.0 (verified: bundle hash ``index-CyXg9Pbr.css``
#          совпадает с моим build). Hard reload (Ctrl+F5) обновит.
#
#          Sanity: ``tsc --noEmit`` clean; ``vite build`` clean
#          (524.51 kB main / 81.80 kB CSS — без изменения
#          размера: ambient-loop и rAF-обёртка в пределах
#          minifier-noise'а).
# 1.48.0 — Landing rebuild + bot handle update.
#          (1) Proof counter — removed the static heart icon next to
#              the number; flying like-particles repositioned to the
#              right edge, larger (44/56 px), softer easing
#              (cubic-bezier(0.16, 1, 0.3, 1)), 2 s flight with a
#              gentle blur-in/out. Section glow attenuated.
#          (2) Unified landing typography — added .landing-h1 / -h2
#              / -lead / -body classes (Inter family preserved) and
#              applied them across Hero, ProofCounter, Testimonials,
#              Simulation, BeforeAfter, ApiSection, HowItWorks,
#              Pricing, scenario heroes (Dating, Resume, Documents)
#              and the brand+CTA block on the home landing.
#          (3) Testimonials block fully rewritten as a 3-slot
#              carousel: DiceBear avatar (notionists, gradient bg)
#              + nickname + direction chip + tier chip (Премиум
#              accent gradient / Обычный neutral) + emoji-rich short
#              review + auto-cycling before/after slider with a
#              live drag handle. Sweep 3 s, hold 3 s, soft cross-
#              fade to next card.
#          (4) BeforeAfterSlider — added autoCycle / autoCycleMs /
#              autoHoldMs / autoFrom / autoTo / hideHandle props;
#              user drag pauses the autopilot for 1.5 s.
#          (5) Landing.tsx — Testimonials moved up directly under
#              ProofCounter (Hero → ProofCounter → Testimonials →
#              HowItWorks → Simulation → BeforeAfter → API → CTA →
#              Pricing).
#          (6) HowItWorks made reusable: optional ``steps`` and
#              ``title`` props, CSS grid (``repeat(4, 1fr)``) with
#              equal-height cards (``min-height`` floor +
#              ``flex: 1 1 auto`` on the description) so plates
#              align symmetrically across the row. Connected on all
#              four landings (home, Dating, Resume, Documents) with
#              identical visuals; Documents replaced its custom
#              4-card grid with the shared component.
#          (7) Scroll regression fix on scenario landings — root
#              divs switched to ``min-h-screen flex flex-col`` +
#              ``main flex-1`` so the footer pins to the bottom on
#              short pages; ``.energy-field`` clipped (``overflow:
#              clip``) so deep blobs (top: 200vh+) no longer leak
#              past short main heights.
#          (8) Telegram bot handle rebrand: ``RateMeAIBot`` →
#              ``RateMeAI_bot`` in src/config.py default username,
#              .env.example YOOKASSA_RETURN_URL, web Hero
#              platform link and LinkPage instructions copy.
#          Sanity: tsc --noEmit clean; ruff clean; vite build OK.
# 1.49.0 — Landing polish round 2 (heart swarm, solid testimonial
#          cards, unified before/after slider, fluid-bg without lag
#          and dark light-theme tail).
#          (1) ProofCounter — каждый tick рождает 4..7 сердец (6..9
#              на burst), размеры 0.55..1.7, веер шире (x: 4..72,
#              y: -10..-44), лёгкий ±25° rotate, delay 0..520 ms,
#              анимация 2400 ms с поздним пиком opacity и blur-in/
#              out → пользователь видит «стайку» сердечек разного
#              размера, плавно растворяющихся, вместо одного
#              рывкового. Glow attenuated до 0.07/1400 ms,
#              перестал «вспышить» при множественном burst.
#          (2) Testimonials — карточка стала semi-solid: фон
#              ``rgba(17,24,32,0.78)`` (dark) /
#              ``rgba(255,255,255,0.82)`` (light) +
#              ``backdrop-filter: blur(18px) saturate(140%)``,
#              ``glass-card`` убран из className. Боковые слоты
#              увели в фон (opacity 0.30, blur 5 px, saturate 0.7).
#              Slider-wrap теперь solid (var(--color-surface-2)),
#              before/after плейсхолдеры читаются ясно. Eyebrow
#              «Отзывы» удалён со всех 4 лендингов.
#          (3) Unified before/after slider — все 4 лендинга
#              используют default-вариант (3 слота prev/center/
#              next) с ``withSlider=true``. Documents больше не
#              compact и не withSlider=false. Compact-вариант
#              оставлен в коде ради back-compat, но нигде не
#              используется.
#          (4) Themed before/after mocks — PlaceholderUpload /
#              PlaceholderUpgrade получили prop ``tone?: 'home' |
#              'dating' | 'cv' | 'documents'``. Через CSS-
#              переменную ``--tone-color`` accent-элементы
#              (sparkles, glow, dots, frame) переключаются на
#              тематический оттенок: rose ``#F46FA0`` (Dating),
#              violet ``#7C9BFF`` (CV), neutral cream
#              ``#D9CFB7`` (Documents). Home — без override
#              (динамический accent). Testimonials прокидывает
#              ``tone`` в TestimonialCard.
#          (5) FluidBackground lag fix — ``[data-category]``
#              CSS-transition урезан: ``--accent-r/g/b/--accent-
#              sec-*`` переключаются мгновенно, transition
#              оставлен только для ``--color-brand-primary/
#              hover``. Раньше 0.4 s интерполяция RGB-каналов
#              приводила к тому, что ``getComputedStyle`` в
#              ``refreshThemeCache`` (даже rAF-обёрнутый) видел
#              промежуточные значения → splat'ы рисовались
#              «между цветами». MutationObserver теперь дополни-
#              тельно вызывает ``clearDye()`` при смене
#              ``data-category`` — мгновенно стирает FBO read +
#              write, и старый «хвост» предыдущего цвета не
#              тлеет 600 ms после переключения.
#          (6) FluidBackground unified theme — убран
#              ``mix-blend-mode: lighten/multiply``-разрыв между
#              темами. Теперь ``mix-blend-mode: normal; opacity:
#              0.7`` для обеих. Удалены ``LIGHT_OVERRIDES``
#              (разные dissipations/radius/force для light),
#              ``themeScale = 0.55`` в pickSplatColor, и двойная
#              компиляция display-шейдера (SHADING+plain). Теперь
#              на белой подложке след — мягкий светло-cyan tint,
#              никаких тёмных «грязных» пятен; на тёмной —
#              насыщенный cyan-tint как раньше. Контракт mount'а
#              расширен (FluidBackground уже на всех 4 лендингах
#              + AppPage).
#          Sanity: tsc --noEmit clean; ruff clean; vite build OK.
# 1.49.1 — Hotfix follow-up to user feedback on 1.49.0:
#          (1) BeforeAfterSlider in autoCycle mode rewritten as a
#              one-shot opacity cross-fade (3 s fade → 3 s hold,
#              no clip-path, no reverse, no shutter). Carousel re-
#              mounts each card via key={item.id} so the dissolve
#              restarts cleanly on advance — the visual now matches
#              beforeafterly.com that was originally referenced.
#              Interactive (drag) mode keeps the clip-path divider
#              for ReviewModal and BeforeAfterSection.
#          (2) Testimonials slider compressed: aspect-[4/5] →
#              aspect-[4/3]. Track min-height bumped to 780/820 px
#              so the active card no longer overlaps the next
#              "Как это работает" section.
#          (3) ProofCounter — dense TikTok-style heart stream.
#              Tick interval 800-2400 ms (was 8000-36000 ms),
#              2-3 hearts per tick (3-5 on burst, was 4-7/6-9).
#              All HOME_COPY/DOCUMENT counter presets in
#              data/social-proof.ts retuned to the same range, plus
#              a hard floor in ProofCounter.tsx so future preset
#              edits can't return jerky long pauses.
#          (4) FluidBackground full revert to 1.48 visuals:
#              ``mix-blend-mode: lighten`` (dark) /
#              ``mix-blend-mode: normal; opacity: 0.55`` (light) —
#              dark theme regains the bright "lighten" glow,
#              light theme renders as a soft cyan tint without
#              dark multiply pixels. SHADING + plain dual display
#              shaders, LIGHT_OVERRIDES (faster dissipation,
#              thinner radius, lower force on white) and
#              themeScale = 0.55 in pickSplatColor restored.
#              clearDye() on data-category change removed.
#          (5) Lag-fix preserved: CSS-transition on --accent-r/g/b
#              stays disabled (only --color-brand-primary/hover
#              transitions remain) so the fluid color no longer
#              lags one step behind on category switches.
#          Sanity: tsc --noEmit clean; ruff clean; vite build OK.
# 1.49.2 — Heart pacing + selfie slider tuning per user feedback.
#          (1) ProofCounter — back to natural social-proof pace.
#              Tick 5..10s (was 0.8..2.4s) — counter no longer
#              looks like a bot incrementing every second. Per
#              tick: 3..4 hearts (4..5 on rare burst, chance 8..
#              12%). Animation rewritten to 1800 ms with fast
#              entry (10%) + long, gentle dissolve (last 40%);
#              the heavy 5px blur-in that made the previous
#              version feel "stuck/laggy" before liftoff is gone.
#              All HOME_COPY/DOCUMENT counter presets in
#              data/social-proof.ts retuned to 5..10 s; floor in
#              ProofCounter.tsx clamps to the same range so future
#              CMS edits can't bring back jerky 30-second pauses
#              or per-second bot-like ticks.
#          (2) Testimonials slider — aspect-[3/4] (iPhone selfie
#              portrait), was 4:3 horizontal squarish. Track
#              min-height bumped to 1000 px (mobile 860 px) so
#              the active card has room for the taller frame
#              without overlapping "Как это работает".
#          Sanity: tsc --noEmit clean; ruff clean; vite build OK.
# 1.50.0 — Style showcase + improved hearts/landings.
#          (1) ProofCounter — анимация сердец переписана: 1200 ms
#              (было 1800), 3 keyframe-стопа вместо 4 (убран
#              «излом» на 60% времени), per-particle --dur jitter
#              1100..1350 ms (частицы из одного тика расходятся
#              по времени), translate3d + statichный filter
#              (composite-only, без перерасчёта drop-shadow на
#              каждый кадр). Easing cubic-bezier(0.16, 0.84, 0.44,
#              1) — мгновенный старт + длинный плавный шлейф.
#          (2) Simulation — глобальная переработка блока.
#              • Заголовок: «6 категорий — под любую задачу» →
#                «Улучшаем фото — под любую задачу» (CMS поле
#                title по-прежнему уважается).
#              • CategoryTabs: убрана внешняя плашка
#                gradient-border-card glass; кнопки направлений
#                теперь рендерятся на прозрачном фоне. Coming-soon
#                направления (model/brand/memes) скрыты на
#                лендинге через флаг hideComingSoon (в wizard
#                логика «скоро» сохранена).
#              • Правая часть: вместо двух статичных карточек
#                Исходное / Стилизованное теперь
#                BeforeAfterSlider в режиме playKey — один
#                кросс-фейд before → after при выборе стиля,
#                aspect-[3/4] (iPhone selfie). Под слайдером —
#                отзыв из «style-showcase» пула, привязанный к
#                выбранному стилю; никнейм + tier-бэйдж + цитата.
#              • Score-row пересобран: до/после рядом,
#                tabular-nums, без heavy progress-bars.
#              • Pros: showCategoryTabs (default true),
#                forceCategory: ReviewCategory (CategoryId | 'documents').
#          (3) BeforeAfterSlider — добавлен режим playKey: при
#              изменении ключа компонент проигрывает один
#              кросс-фейд 0→1 за autoCycleMs без шторки и
#              реверса. На первом mount fade=1 (показываем сразу
#              «после»). Существующий autoCycle режим для
#              Testimonials не изменился.
#          (4) Сценарные лендинги — Simulation добавлен на
#              DatingPhotoLanding (forceCategory='dating'),
#              ResumePhotoLanding (forceCategory='cv') и
#              DocumentPhotoLanding (forceCategory='documents');
#              на DocumentPhotoLanding убран статичный grid
#              «Поддерживаемые форматы» — Simulation полностью
#              его заменяет с интерактивным выбором формата.
#          (5) Testimonials data — расширены тип Testimonial:
#              category: ReviewCategory (добавлен 'documents'),
#              usage?: 'carousel' | 'style-showcase'. Добавлены
#              ~30 коротких style-showcase отзывов (по
#              направлениям) — не пересекаются по тексту с
#              carousel-отзывами в основной карусели. Новая
#              утилита getStyleShowcaseReview(category, styleKey)
#              возвращает «отзыв под слайдером» по детерминисти-
#              чному hash'у styleKey'а (повторный клик на тот же
#              стиль не перетасовывает отзыв).
#          (6) ReviewModal/Testimonials: type-narrow для
#              category === 'documents' (документ-тестимониалы
#              на DocumentPhotoLanding по-прежнему рендерятся в
#              карусели через legacy category='cv').
#          Sanity: tsc --noEmit clean; ruff clean; vite build OK.
# 1.50.1 — Unified showcase card + tighter Simulation/Testimonials.
#          (1) Extracted TestimonialShowcaseCard
#              (web/src/components/TestimonialShowcaseCard.tsx) —
#              shared by both the carousel (`Testimonials`) and the
#              right column of `Simulation`. The card carries
#              avatar + nickname + direction/style chip + tier
#              badge + emoji review + before/after slider, with two
#              animation modes:
#                - `autoCycle`: legacy carousel behaviour (one
#                   cross-fade per active slot, re-mount on advance);
#                - `playKey`: new manual trigger — the cross-fade
#                   replays whenever `playKey` changes (Simulation
#                   uses it for the «click on style» interaction).
#          (2) Shrunk the carousel card across the board:
#                - testimonial-slot width 560 → 420 px (compact 520
#                   → 400 px) so the card no longer floats massively
#                   over neighbouring sections;
#                - is-prev/is-next translate ±72% → ±82% to keep the
#                   side cards from creeping under the centred one
#                   after the width reduction;
#                - testimonial-card padding 20/24 → 16/20 + gap 16
#                   → 12 — denser layout at the same content;
#                - testimonial-emoji-review font 16/24+18/28 →
#                   15/22+16/24, still readable but proportionate;
#                - testimonial-track min-height 1000/860 → 760/720
#                   px — matches the actual contents, no longer
#                   bleeds into «Как это работает».
#          (3) Simulation: right column reuses the new card
#              instead of slider+score-row+local review block. The
#              score-row (5.42 / 6.79) was removed for visual
#              consistency with the main carousel — the same review
#              card appears in both places. Right column max-width
#              440 → 420 px.
#          (4) Simulation left column: 5 styles → 8 (ITEMS_PER_PAGE),
#              gap-12 → gap-20. Heights of left/right columns now
#              match within ~50 px on desktop, fixing the «red
#              lines» misalignment the user reported.
#          (5) Documents landing: 5 formats → 8. Added medical_form
#              (Медкомиссия), driver_license (Водительские права)
#              and student_id (Студенческий ID) to
#              DOCUMENT_LANDING_ITEMS, with a matching
#              `style-showcase` testimonial each so the slider has
#              a per-format quote.
#          Sanity: tsc --noEmit clean; ruff clean; vite build OK.
# 1.50.2 — Brand CTA on scenario landings + section reorder.
#          (1) DatingPhotoLanding / ResumePhotoLanding /
#              DocumentPhotoLanding: HowItWorks moved before
#              Simulation (was after). New flow:
#                Hero → ProofCounter → Testimonials →
#                HowItWorks → Simulation → BrandCTA → Footer.
#              Main Landing.tsx — без изменений (порядок там уже
#              был правильным).
#          (2) Brand heading + CTA section added on each scenario
#              landing — повторяет section#app основного, но
#              без логотипа Look Studio: вместо него крупная
#              надпись с темой сценария:
#                Documents → «📋 Фото на документы»
#                Resume   → «💼 Фото для резюме»
#                Dating   → «💘 Фото для знакомств»
#              Размер шрифта 32 / 60 / 96 px (моб/планшет/деск)
#              чтобы длинные русские строки не уезжали за
#              max-w-[1200px] контейнера. H2 + lead адаптированы
#              под сценарий («Готовы создать фото?» /
#              «Готовы обновить резюме?» / «Готовы получать
#              мэтчи?»). CTA: «Открыть приложение» если
#              canAccessApp, иначе «Получить доступ» (открывает
#              AuthModal) — синхронно с поведением на основном.
#          (3) DocumentPhotoLanding: старый Final CTA блок
#              («Готовы создать фото?» с двумя карточками
#              REQUIREMENTS_SHORT / REJECT_BULLETS) удалён —
#              его место занимает новый брендовый блок.
#              Соответствующие импорты убраны.
#          Sanity: tsc --noEmit clean; ruff clean; vite build OK.
# 1.50.3 — Финальный экран лендингов: тарифы + ритм + scroll-reveal.
#          (1) Pricing (основной): убрали слово «Тарифы» из шапки.
#              Дефолты + CMS-сидер landing_content.json: title теперь
#              «Первое улучшение», caption — «Разблокируй
#              эксклюзивные стили». Subtitle (градиентный
#              «— попробуй бесплатно») и список из 4 планов оставлены
#              без изменений. CMS-админка может перезаписать тексты;
#              для свежих установок и любого окружения, где CMS
#              запись пуста, теперь показываются новые формулировки.
#          (2) ScenarioPricing — новый компонент
#              (web/src/sections/ScenarioPricing.tsx). Одиночная
#              «прикольная» карточка по центру экрана, glass-card-
#              highlight, max-w 440 px:
#                - бейдж «5 фото» в шапке;
#                - крупная цена 199 ₽ + подпись «5 AI-фото · 40 ₽
#                  за фото»;
#                - feature-list (4 пункта): «5 AI-фото в одном
#                  пакете / Доступ ко всем стилям категории /
#                  Без водяных знаков / Подбор за 2 минуты». Без
#                  «гарантии возврата» — её нет в продукте,
#                  не обещаем то, чего не делаем.
#                - CTA «Купить 5 фото за 199 ₽» вызывает тот же
#                  createPayment(5) flow, что и main Pricing.
#                - заголовок секции зеркалит main Pricing
#                  (тот же шаблон title + gradient subtitle +
#                  caption), tagline настраивается per-scenario.
#              Подключён последним блоком (после BrandCTA, перед
#              Footer) на DatingPhotoLanding, ResumePhotoLanding,
#              DocumentPhotoLanding. Итоговый порядок секций
#              сценарных лендингов теперь:
#                Hero → ProofCounter → Testimonials → HowItWorks
#                → Simulation → BrandCTA → ScenarioPricing → Footer.
#          (3) Ритм / воздух между блоками:
#                - Testimonials: gap heading↔слайдер 24 → 32/48 px
#                  («Впечатления пользователей» больше не «лип» к
#                  карусели);
#                - HowItWorks: внутренний padding 16/24 → 32/64 px
#                  и gap 16/24 → 24/40 px — блок воспринимается
#                  как «отдельная сцена», а не зажатая полоса;
#                - Simulation: десктопный py 120 → 88, gap heading
#                  ↔ контент 96 → 64 — секция выровнялась с
#                  соседями (между HowItWorks и Simulation
#                  больше нет «провала» в 144 px);
#                - Pricing (main): py 120 → 96, gap 96 → 64 —
#                  единая концовка с section#app;
#                - section#app (Landing) и BrandCTA на сценарных:
#                  py 120 → 96/88 — финал не «утопает» в нижнем
#                  margin'е страницы;
#                - BeforeAfterSection: gap 24 → 32/48 — заголовок
#                  отлип от слайдера на десктопе.
#          (4) Scroll-reveal анимации первого появления:
#                - Новый хук web/src/lib/useReveal.ts — глобальный
#                  singleton: один IntersectionObserver наблюдает
#                  за всеми `.reveal` / `.reveal-stagger` нодами,
#                  при пересечении viewport на 15% выставляет
#                  data-revealed="true" — CSS transition догоняет
#                  до финального состояния (opacity 0→1, translateY
#                  16px→0, scale 0.985→1; 600 ms cubic-bezier).
#                  MutationObserver подписывает новые ноды,
#                  появляющиеся после React-рендера. Уже видимые
#                  при загрузке элементы помечаются сразу — без
#                  блика «пустого экрана». Хук вызывается в App.tsx
#                  один раз; повторные вызовы no-op.
#                - На `prefers-reduced-motion: reduce` контроллер
#                  пропускает IO и мгновенно проставляет атрибут
#                  всем; CSS-правила сбрасывают transform/opacity.
#                - `.reveal-stagger > *` с задержками 0/80/.../560
#                  ms по nth-child(N) — для карточек тарифов и
#                  шагов «Как это работает».
#                - Покрытие: heading-блоки в Pricing /
#                  ScenarioPricing / Testimonials / HowItWorks /
#                  Simulation / BeforeAfterSection / ApiSection /
#                  BrandCTA, плюс stagger на howworks-grid и
#                  Pricing PLANS row. Hero намеренно без reveal
#                  (он первый, виден сразу — мерцание лишнее).
#                  ProofCounter: reveal только на heading +
#                  subheading, сама цифра и burst-частицы не
#                  оборачиваем — иначе transform-контекст ломает
#                  letящие сердечки.
#          Sanity: tsc --noEmit clean; ruff clean; vite build OK.
# 1.50.4 — Liquid-Glass-уровень для тела лендингов + 3-картовый
#          ScenarioPricing.
#          (1) Унификация glass-токенов с шапкой (.glass-nav).
#              Раньше карточки и кнопки в теле имели surface-alpha
#              0.04 / 0.02 — на фоне «толстого» nav-стекла (alpha
#              0.65) тело смотрелось «куце». Подняли:
#                - --glass-surface 0.04 → 0.07 (dark), 0.55 → 0.62 (light)
#                - --glass-surface-strong 0.06 → 0.10 / 0.70 → 0.78
#                - --glass-surface-soft 0.02 → 0.04 / 0.40 → 0.48
#                - --glass-border 0.08 → 0.12 / 0.08 → 0.12
#                - --glass-border-hover 0.14 → 0.18 / 0.16 → 0.20
#                - --glass-inset-highlight 0.06 → 0.14 (dark) / 0.80 → 0.85 (light)
#                - --glass-shadow-card → двухслойная тень
#                  (0 16px 48px / 0.40 + 0 2px 8px / 0.20 contact-shadow
#                  для dark; 0 16px 40px / 0.16 + 0 2px 6px / 0.08 для light).
#              Saturate в .glass-card 1.15 → 1.25,
#              .glass-card-highlight 1.20 → 1.30. Inset highlight
#              переведён с 1px на 1.5px — заметнее верхняя «грань линзы».
#          (2) Sheen — диагональный specular через ::before на
#              .glass-card / .glass-card-highlight (mix-blend-mode:
#              screen в dark, normal в light с opacity 0.55). Имитация
#              скользящего по линзе света — основной фактор «дороже»
#              ощущения. На :hover sheen разгорается до opacity 1.
#              isolation: isolate на родителе изолирует ::before в
#              собственном stacking context, контент-потомки рисуются
#              поверх; pointer-events:none — клики пробрасываются вниз.
#              ::before и .gradient-border-card::after не конфликтуют
#              (разные псевдоэлементы), поэтому glass-карточки могут
#              остаться gradient-bordered.
#          (3) Hover-lift на .glass-card / .glass-card-highlight /
#              .glass-card-premium: translateY(-2px ÷ -3px) +
#              усиление glow и тени; 250 ms cubic-bezier(.16,.84,.44,1).
#              На prefers-reduced-motion transform:none, остальное
#              остаётся (тень/border меняются мягко).
#          (4) Новый класс .glass-card-premium — расширение
#              .glass-card-highlight для самых «продающих» карточек:
#                - двухслойный sheen (linear + radial bottom-right
#                  glow в тон активной категории);
#                - inset accent-glow по нижней грани
#                  (0 -1px 30px rgba(accent,0.04));
#                - saturate 1.35;
#                - усиленный hover (-3px translate, glow до 0.20 alpha).
#              Применён в Pricing (highlighted plan на main) и в
#              средней карточке ScenarioPricing.
#          (5) ScenarioPricing — переписан на 3 позиции в одном ряду
#              (раньше была одна карточка по центру; user feedback —
#              «куе»):
#                a) «Попробовать» — 199 ₽ · 5 фото · glass-card,
#                   CTA «Купить 5 за 199 ₽» → createPayment(5);
#                b) «Прокачать образ» — 499 ₽ · 15 фото ·
#                   glass-card-premium · BEST badge ·
#                   savingBadge «Экономия 40%» · features 4 шт ·
#                   CTA «Купить 15 за 499 ₽» → createPayment(15)
#                   (packQty=15 уже отлажен на основном Pricing);
#                c) «Корпоративный тариф» — B2B-карточка, без цены
#                   и без покупки. Features: «✦ Свой бренд / стили
#                   · ✦ Webhook-интеграция · ✦ Договор и счёт».
#                   CTA «Узнать про API» → /#api (scrollIntoView к
#                   <ApiSection /> на главной; на сценарном
#                   делает navigate('/') + setTimeout 120 ms +
#                   scrollIntoView, как NavBar.scrollToPricing).
#              Mobile: горизонтальный snap-scroll, как в основном
#              Pricing. Desktop: 3-up flex, центральная чуть шире
#              (flex-[1.15]), B2B чуть уже (flex-[0.95]) — даёт
#              визуальный фокус на «BEST». Под рядом — мягкая
#              подпись «Все пакеты идут на один баланс».
#          Sanity: tsc --noEmit clean; ruff clean; vite build OK.
# 1.50.5 — Тёмное тонированное стекло (как у шапки) + фоновые
#          градиенты ушли в «свет из глубины».
#          (1) Dark-токены glass-* переведены на тёмный пигмент
#              rgba(10, 14, 20) — тот же что у .glass-nav. Раньше
#              dark-карточки красились белым оверлеем 0.07 alpha
#              и на тёмном фоне выглядели «молочно-матовыми», а
#              шапка — «обсидиановой». Теперь визуальный язык один:
#                --glass-surface           rgba(10,14,20, 0.55)
#                --glass-surface-hover     rgba(10,14,20, 0.45)
#                --glass-surface-strong    rgba(10,14,20, 0.70)
#                --glass-surface-soft      rgba(10,14,20, 0.30)
#                --glass-border            rgba(255,255,255, 0.10)
#                --glass-border-hover      rgba(255,255,255, 0.18)
#                --glass-inset-highlight   rgba(255,255,255, 0.16)
#                --glass-shadow-card       0 18px 48px / 0.45,
#                                          0 3px 10px / 0.30
#              Light-тема не трогалась — там шапка и карточки
#              уже в одном молочно-светлом языке.
#          (2) .glass-card-highlight и .glass-card-premium перешли
#              на ту же тёмную базу — accent ушёл в border + glow,
#              а surface остался тёмным. На light-теме, где тёмная
#              база смотрится грубо, accent-tint surface оставлен
#              через [data-theme='light'] override. Glow, тени и
#              hover-lift подкручены — карточка ощутимо «парит»
#              над mesh-фоном.
#          (3) Sheen ::before усилен под тёмный surface:
#                base: linear-gradient(135°, white 0.14 → 0)
#                premium: то же + radial accent corner
#                    (rgba(accent, 0.16) at 100% 100%) и
#                    yellow-tint diagonal up to 0.20
#              mix-blend-mode: screen на dark гасится в нечто
#              «бликующее как линза», на light — выключен,
#              opacity снижен (mix:normal, 0.55-0.65).
#          (4) Buttons / badges / rows / tabs тоже потемнели —
#              они все используют те же --glass-surface-* токены.
#              Получили единый язык «тёмное тонированное стекло»
#              везде.
#          (5) Фоновые градиенты — «свет из глубины», не «слой
#              поверх объектов»:
#              - .energy-field z-index 1 → 0. Раньше energy сидел
#                в промежуточном слое между mesh (z-0) и UI-
#                секциями (z-2), и выраженные blob'ы читались
#                как «градиент поверх контента». Теперь energy в
#                одном фоновом слое с mesh + fluid (DOM-order:
#                mesh → fluid → energy → секции в isolated
#                z-2). Свет проходит сквозь полупрозрачные
#                тёмные карточки как фоновая подсветка, а не
#                лежит сверху.
#              - EnergyField BLOBS opacity ~×0.5 (0.04-0.07 →
#                0.020-0.035) — blob'ы теперь работают на
#                тонкое свечение, а не самостоятельный слой.
#          Sanity: tsc --noEmit clean; ruff clean; vite build OK.
# 1.50.7 — Footer / стилевая консистентность / стабильный скролл.
#          (1) <ScrollToTop> внутри BrowserRouter: при PUSH/REPLACE
#              навигации насильно прокручиваем страницу к началу;
#              POP оставлен браузеру (back/forward сохраняют свой
#              scroll-restore). Чинит «иногда лендинг открывается
#              на тарифах» при кликах по ссылкам в футере.
#          (2) ApiSection — колонки поменяли местами: на десктопе
#              слева список API-сценариев, справа описание +
#              преимущества + CTA. На мобиле порядок прежний
#              (список → описание).
#          (3) Тематика модалок (data-category) — порталы
#              монтируются в document.body и не наследовали
#              data-category страницы. Добавили проброс
#              app.activeCategory в Policy/Support/UI Modal/
#              StyleSettings/StylesSheet. Тем самым акценты
#              (--color-brand-primary / --accent-r/g/b) теперь
#              правильно меняются в модалках на /znakomstva
#              (pink), /dokumenty и /rezume (purple).
#          (4) Лендинги Dating/Document/Resume теперь
#              синхронизируют app.activeCategory под свою
#              категорию через useEffect на mount — иначе модалки
#              видели дефолтное 'social' (cyan).
#          (5) Чистка «AI» из видимых пользователю текстов:
#              titles/meta всех лендингов, hero-subtitle,
#              ScenarioPricing, Pricing, ApiSection, SupportModal
#              FAQ, StepAnalysis, StepGenerate label. Сохранены:
#              transparency-badge "AI-generated" (EU AI Act
#              Art. 50), ConsentGate (юридический терм
#              «AI-сервисы»), EXIF UserComment-метка.
#              landing_content.json: tagline, api.subtitle и
#              FAQ-вопрос обновлены.
#          (6) Footer: добавлен LogoEmblem рядом с brandTitle,
#              новый дефолтный tagline («Портреты, которые
#              работают…»). Если CMS вернёт legacy-tagline c
#              "AI/ИИ/нейросеть" — клиент перетирает его новым
#              дефолтом, чтобы AI не вылез до деплоя.
#          (7) #4ADE80 → var(--color-success-base) в LinkPage и
#              LinkedAccountsPanel. Брендовые цвета провайдеров
#              (Telegram/Yandex/VK/Google/OK) намеренно оставлены
#              как корпоративные.
# 1.50.8 — Admin UX cleanup: (1) Общий AdminLayout с табами вверху
#          (Landing CMS / Каталог стилей / Конфликты названий) —
#          навигация между админ-страницами больше не через ad-hoc
#          ссылки, единый sticky-хедер с активной подсветкой.
#          (2) Каталог стилей: убран selector schema_version и таб
#          «Slots v2» — каталог 100% v3, эти контролы редактировали
#          мёртвые поля. EMPTY_V2_TEMPLATE заменён на
#          EMPTY_V3_TEMPLATE (schema_version=3, trigger_pool,
#          scene_anchor, ambient.*, available_channels, location_type,
#          background_lock). Теперь две вкладки: «Базовое» и «Поля
#          стиля» (последняя объединяет старые v3 channels + те v2
#          поля, что движок ещё читает: clothing.default,
#          quality_identity.base/per_model_tail). validateV2Draft
#          заменён validateV3Draft (trigger_pool ≥ 1, scene_anchor
#          непустой, clothing.default ≥ 1, quality_identity.base
#          непустой). v2-поля в JSON НЕ удаляются, потому что
#          style_loader_v2._to_v2 читает их и для schema_version=3.
#          (3) Отступы: все три страницы теперь под max-w-1240 +
#          px-16/32/48 + py-32/40 (было p-6 = 6px). Ячейки таблицы
#          px-16 py-12 (было px-3 py-2). Заголовки колонок и кнопки
#          фильтров переведены на русский (ID/Режим/Название/Линт/
#          Разблокировка/Сценарий/Действия). Колонка «v» удалена,
#          legacy-версия отображается как inline-бейдж рядом с id.
#          (4) StepStyle.tsx: «· {styles.length} стилей» рядом с CTA
#          «Хочу другой образ» заменено на «· {N} доступно» —
#          основной экран больше не упоминает заблокированные
#          стили. Locked видны только в шторке StylesSheet (как и
#          раньше); при разблокировке через unlock_after_generations
#          стиль автоматически попадает в recommendedStyles.
#          Backend не тронут.
# 1.50.9 — Admin whitelist by email: ``require_admin`` теперь
#          принимает либо UUID в ``ADMIN_USER_IDS`` (legacy), либо
#          email в новой переменной ``ADMIN_EMAILS``. Email-матч
#          идёт по ``user_identities.profile_data->>'email'`` для
#          любого провайдера (google/yandex/vk_id/apple/yandex).
#          Onboarding нового админа теперь = одна env-переменная,
#          без поиска UUID в БД. Оба whitelist-а опциональны и
#          работают параллельно (OR).
# 1.51.0 — Sync session-token bootstrap (frontend only). Раньше
#          ``_token`` в ``web/src/lib/api.ts`` инициализировался
#          ``null``, а реальное значение из ``localStorage``
#          подгружал ``AppContext`` уже внутри ``useEffect`` →
#          при прямом заходе на ``/admin/*`` страница успевала
#          смонтироваться и сделать запрос ДО восстановления
#          токена, ловя 401 и показывая «Сессия не активна».
#          Теперь ``_token`` читает ``ailook_session_token`` из
#          localStorage синхронно при загрузке модуля — до первого
#          React-рендера. Чистая фронт-правка, бэк не тронут;
#          фиксит редкие 401 и в обычном кабинете при reload.
# 1.52.0 — Admin Users tab: новая страница ``/admin/users`` для
#          ops-обзора пользователей, баланса кредитов, истории
#          транзакций и генераций с возможностью ручных операций.
#          Бэк (новый ``src/api/v1/admin/users.py``):
#            * GET ``/api/v1/admin/users?q=&limit=`` — substring
#              поиск по username / telegram_id / profile_data.email
#              + агрегаты (total_generations, last_task_at,
#              last_seen). Никаких полей с путями к фото в
#              ответах (privacy-by-design).
#            * GET ``/api/v1/admin/users/{id}`` — карточка с
#              identities, последними 50 транзакциями и 20
#              задачами (только id/mode/status/timestamps —
#              ``input_image_path``/``share_card_path`` НЕ в
#              SELECT-листе).
#            * POST ``/api/v1/admin/users/{id}/credits`` —
#              атомарное начисление (+amount, ``admin_grant``)
#              или списание (-amount, ``admin_debit``) с
#              обязательным ``reason``. Проверка
#              insufficient_credits на 400.
#            * POST ``/api/v1/admin/users/{id}/refund`` —
#              учётный возврат: списываем кредиты + пишем
#              ``admin_refund`` транзакцию с note и
#              опциональным payment_id. Реальные деньги через
#              ЮKassa/Stripe возвращаем отдельно вручную.
#          Все ручки гейтятся ``require_admin`` (UUID или email
#          из ``ADMIN_EMAILS``); существующий
#          ``/internal/admin/grant-credits`` (X-Internal-Key) не
#          тронут — продолжает работать для GitHub Actions
#          workflow и админ-бота.
#          Хелперы ``format_user_summary`` / ``search_users_by_query``
#          вынесены в ``src/services/admin_lookup.py``;
#          ``internal.py`` теперь импортирует их оттуда.
#          Фронт: ``web/src/pages/admin/UsersAdminPage.tsx`` с
#          таблицей и боковой шторкой (drawer); 4-я вкладка
#          «Пользователи» в ``AdminLayout``; маршрут
#          ``/admin/users`` lazy-load в ``App.tsx``.
# 1.53.0 — Scenario landings → CMS (frontend-only). Текст и
#          steps трёх сценарных лендингов (документы / знакомства
#          / резюме) теперь редактируется через тот же
#          ``/admin/landing`` JSON-редактор, что и ``home``.
#          В ``data/landing_content.json`` добавлены slug-и
#          ``document_photo``, ``dating_photo``, ``resume_photo``;
#          бэк (``landing_store``) автоматически их подхватывает,
#          ``GET /api/v1/admin/landing/pages`` возвращает все 4
#          ключа. В ``web/src/lib/landing-cms.ts`` добавлены
#          парсеры ``parseHero`` / ``parseHowItWorks`` /
#          ``parseFinalCta`` / ``parseScenarioPricing`` и
#          универсальный ``useLandingPage(slug)`` с кэшем.
#          ``DocumentPhotoLanding.tsx`` / ``DatingPhotoLanding.tsx``
#          / ``ResumePhotoLanding.tsx`` читают блоки из CMS;
#          захардкоженный контент остался в файлах как
#          fallback — пустой/битый JSON-блок рендерит старую
#          верстку, не белую страницу. Тестимониалы и
#          social-proof пресеты намеренно оставлены
#          динамическими (отдельные модули
#          ``data/testimonials`` и ``data/social-proof``).
# 1.54.0 — Soft-block + admin delete (минимум перед запуском).
#          DB: миграция ``011_user_blocked`` добавляет в
#          ``users`` поля ``blocked_at`` / ``blocked_reason`` /
#          ``blocked_by`` (все nullable; NULL = активен).
#          Backend: ``ensure_user_not_blocked()`` в
#          ``src/api/deps.py`` поднимает 403 с
#          ``detail = {"code": "account_blocked", "reason": ...}``;
#          вызывается из ``get_auth_user`` (каждый
#          authenticated-запрос), ``_auth_response`` (web auth),
#          трёх OAuth-callback'ов (Yandex/Google/VK-ID) и
#          ``_claim_link_response`` — заблокированный
#          юзер не может ни залогиниться, ни обновить токен.
#          Сервис ``src/services/user_purge.py`` — общая
#          логика 152-ФЗ ст. 14 erasure (storage + redis +
#          DB cascade + ``deletion_log``); используется и
#          self-serve ``DELETE /users/me`` (source="api"),
#          и админским ``DELETE /admin/users/{id}``
#          (source="admin"). Новые ручки в
#          ``src/api/v1/admin/users.py``:
#            * POST ``/admin/users/{id}/block`` — ставит
#              ``blocked_at/by/reason``. Самоблокировка
#              запрещена (400). Сообщения никуда не уходят —
#              юзер видит in-app overlay.
#            * POST ``/admin/users/{id}/unblock`` — обнуляет
#              три поля.
#            * DELETE ``/admin/users/{id}`` — полная
#              деперсонализация через ``purge_user``;
#              самоудаление admin-аккаунта запрещено.
#          Все три гейтятся ``require_admin``.
#          Frontend: глобальный перехватчик 403 в
#          ``request()`` (``web/src/lib/api.ts``) при коде
#          ``account_blocked`` бросает CustomEvent, который
#          ловит ``App.tsx`` и рисует
#          ``AccountBlockedScreen`` поверх всего UI
#          (``z-[10000]``). На странице
#          ``/admin/users`` в drawer'е добавлены кнопки
#          «Заблокировать» / «Разблокировать» (с
#          обязательной причиной мин. 3 символа) и
#          «Удалить из системы» (необратимо, требует
#          ввести UUID юзера для подтверждения). В таблице
#          справа — бейдж 🔒 «Заблокирован» с tooltip из
#          ``blocked_reason``. Bumped ``AdminUserSummary``
#          с тремя новыми полями (``blocked_at`` /
#          ``blocked_reason`` / ``blocked_by``).
#          Тесты: 12 новых юнит-тестов в
#          ``tests/test_api/test_admin_users.py``
#          (block validations, 404/400, self-block ban,
#          unblock clears, delete calls purge with
#          ``source="admin"``, ``ensure_user_not_blocked``
#          на 3 кейса). Полный набор: 2061 passed, 54 skipped.
# 1.55.0 — Multi-target admin + UX-фиксы (frontend-only).
#          После 1.54 пользователь обнаружил, что блок,
#          списания, лендинг и стили срабатывают только на
#          том инстансе, к которому пришёл админ-запрос —
#          а у нас два независимых FastAPI с собственными
#          Postgres'ами и собственными ``data/styles.json`` /
#          ``data/landing_content.json``: primary
#          (``app-production-6986.up.railway.app``,
#          обслуживает ``ailookstudio.ru`` и
#          ``ailookstudio.vercel.app``) и RU edge VPS
#          (``ru.ailookstudio.ru``). Решение: явный
#          переключатель ``Цель = Primary | RU`` в шапке
#          админки + кнопка «Применить на оба» для CMS
#          операций.
#          Новые модули фронта:
#            * ``web/src/lib/admin-targets.ts`` — декларация
#              ``ADMIN_TARGETS = [primary, ru]`` (env-driven
#              ``VITE_ADMIN_TARGET_PRIMARY_URL`` /
#              ``VITE_ADMIN_TARGET_RU_URL``), per-target
#              localStorage ключи
#              ``ailook_session_token__{primary|ru}``.
#            * ``web/src/lib/admin-target-context.tsx`` —
#              React-контекст ``useAdminTarget()``;
#              ``setTarget(id)`` зеркалит в api.ts и пишет
#              ``ailook_admin_active_target`` в localStorage,
#              чтобы выбор пережил refresh.
#          api.ts: ``API_BASE`` → ``getApiBase()``,
#          ``request<T>(path, init?)`` принимает
#          ``init.target`` (override на один вызов — для
#          fan-out). Токены и URL берутся из словарей
#          ``_tokens[targetId]`` / ``ADMIN_TARGETS``.
#          Legacy-ключ ``ailook_session_token`` мигрируется
#          в ``__primary`` при boot, поэтому существующие
#          сессии не выпадают.
#          AdminLayout: dropdown с цветным бейджем
#          (Primary = синий, RU = зелёный), под ним
#          подпись «у каждого target свои юзеры/кредиты,
#          контент пишется явно через "Применить на оба"».
#          При смене target children перемонтируются по
#          ключу (свежий fetch без stale данных).
#          ``NoTokenForTargetGate`` показывает страницу
#          логина с прямыми ссылками на
#          ``ailookstudio.ru/auth`` и
#          ``ru.ailookstudio.ru/auth`` если на выбранном
#          target нет токена.
#          CMS: ``LandingAdminPage`` и
#          ``StylesAdminPage`` (модалка) получили кнопку
#          «Применить на оба» рядом с обычным
#          «Сохранить». Кнопка делает PUT/POST на оба
#          target последовательно и рендерит inline-панель
#          с per-target диагностикой
#          (``✓ Primary: Сохранено`` / ``✗ RU: 401 — нужен
#          логин``). Failures одного target не откатывают
#          второго; оператор видит, где починить.
#          UX-фиксы редактора стилей:
#            * Ошибки API (422/409/500) теперь падают
#              **внутри** модалки, а не за её оверлеем —
#              ``handleSave`` rethrow'ит, ``StyleEditModal``
#              ловит и рисует красный баннер «Ошибка
#              сохранения».
#            * Баннер валидации сверху модалки
#              «Не сохранено: исправьте поля — trigger_pool,
#              clothing.default» с авто-переходом на
#              вкладку «Поля стиля».
#            * ``per_model_tail`` стал controlled:
#              defaultValue+onBlur заменён на
#              буферизированный textarea с парсингом
#              JSON по onChange и индикатором
#              «Невалидный JSON object».
#            * Кнопка «Сохранить» дизейблится во время
#              запроса, лейбл «Сохраняем…».
#          UX-фиксы Users tab: универсальный
#          ``describeAdminError`` переводит 404 в
#          «Пользователь не найден на текущем сервере.
#          Возможно, он на другом региональном инстансе —
#          переключите Цель в шапке», 401 — в
#          «Сессия не активна на этом сервере», 403 — в
#          «Аккаунт не в ADMIN_USER_IDS на этом инстансе».
#          Применён в catch-блоках ``fetchUsers``,
#          ``fetchDetail``, ``submitAction``,
#          ``handleBlock/Unblock/Delete``.
#          Backend: НИКАКИХ изменений в API/моделях.
#          CORS уже разрешает кросс-домен primary↔ru
#          (проверено через preflight на
#          ``/admin/users/{id}/block`` — оба инстанса
#          возвращают 200 с правильными
#          ``Access-Control-Allow-Origin``). Миграция
#          011 раскатана на оба postgres'а в 1.54.
#          Тесты: ``tsc --noEmit`` зелёный, ``ruff``
#          зелёный, ``pytest`` 2061 passed (без новых
#          тестов — multi-target фронта unit-тестами не
#          покрывается, нужен e2e).
#          ОПЕРАЦИОННОЕ: на RU edge нужно проверить
#          ``ADMIN_EMAILS`` в ``/opt/ratemeai/.env.ru`` —
#          без этой строки логин админа на ru.* даст 403.
# 1.55.1 — Hotfix: OAuth (Google/Yandex/VK) ломался после
#          переключения «Цель» в админке на RU.
#          Root cause: 1.55.0 сделал ``getApiBase()`` /
#          ``getToken()`` / ``request()`` зависимыми от
#          глобального ``_activeTarget``, который пишется
#          в ``localStorage.ailook_admin_active_target``
#          из admin-target-context. Эта переменная
#          использовалась ВЕЗДЕ — включая oauthInit,
#          ``/users/me`` и SSE прогресс. Если оператор хоть
#          раз кликнул переключатель на RU и не вернулся,
#          ACTIVE_TARGET_STORAGE_KEY застревал в ``ru``,
#          OAuth init шёл на ``https://ru.ailookstudio.ru``,
#          authorize_url возвращался с
#          ``redirect_uri=https://ru.ailookstudio.ru/auth/callback``
#          — которого нет в Google/Yandex/VK Console для
#          Vercel-фронта, и провайдер показывал
#          ``redirect_uri_mismatch``.
#          Fix: разнесли public flow и admin flow в api.ts.
#            * ``setToken(t)`` / ``getToken()`` теперь ВСЕГДА
#              работают с primary slot (для основного
#              кабинета). Админка использует
#              ``setTokenForTarget(id, t)`` /
#              ``getTokenForTarget(id)``.
#            * ``request<T>(path, init?)`` определяет target
#              по path: запросы на ``/api/v1/admin/*``
#              следуют ``_activeTarget`` (или явному
#              ``init.target``), всё остальное жёстко идёт
#              на primary.
#            * ``API_BASE`` legacy export всегда указывает
#              на primary (нужно для SSE и
#              ``image-url.ts``, которые захватывают
#              константу на boot).
#            * ``tokenStorageKey('primary')`` теперь
#              возвращает ``'ailook_session_token'``
#              (legacy key), чтобы public OAuth flow и
#              admin Primary flow жили в одном слоте — иначе
#              логин в кабинет не авторизовал бы admin
#              запросы на том же инстансе.
#          Cross-origin reality check в AdminLayout: при
#          переключении target на инстанс с другим origin
#          (``localStorage`` per-origin → токен невозможно
#          достать из чужого домена) ``NoTokenForTargetGate``
#          теперь показывает прямую кнопку «Открыть админку
#          target в новой вкладке», а не бесполезный
#          login-prompt.
#          Backend без изменений. tsc / ruff / pytest
#          (2061 passed) зелёные.
# 1.55.2 — Auto-provision ``ADMIN_EMAILS`` on the RU edge via
#          ``deploy/ru/update.sh``. Added an idempotent
#          ``ensure_env_line`` helper that, on every CI deploy-ru
#          run (and manual ``./update.sh`` invocations), rewrites
#          or appends ``ADMIN_EMAILS=vladimir18kostyal@gmail.com,
#          uk-tora@yandex.ru`` into ``/opt/ratemeai/.env.ru`` BEFORE
#          ``docker compose up -d app`` so the app container picks
#          up the new whitelist on startup. Logs a clear
#          ``[update.sh] ensuring ADMIN_EMAILS=...`` line in the
#          deploy-ru CI output so the change is auditable.
#          Re-runs are no-ops once the value matches.
#          Why: vladimir18kostyal@gmail.com (primary Google admin)
#          and uk-tora@yandex.ru (RU Yandex admin) need joint
#          access to ``ru.ailookstudio.ru/admin/*``.
#          ``_parse_admin_emails`` in src/api/v1/admin/auth.py:39-45
#          consumes the comma-separated list case-insensitively.
#          Primary (Railway) is unaffected: its env is managed by
#          the ``deploy-backend`` job's ``rl_set`` calls in
#          ``.github/workflows/ci.yml``, not by this script.
#          Also documented the convention in ``.env.ru.example``
#          under a new "Admin whitelist" section (placeholder
#          email only — real emails live in update.sh).
#          No code changes; tsc / ruff / pytest (2061 passed,
#          54 skipped) зелёные.
# 1.55.3 — Hotfix to 1.55.2: the ``ensure_env_line`` block in
#          ``deploy/ru/update.sh`` was placed AFTER ``git pull``,
#          which never ran on the deploy that introduced it.
#          Root cause: bash holds the script open via its original
#          file descriptor. ``git pull`` mid-script replaces the
#          file's inode (rename(2) is atomic), but the running
#          interpreter keeps reading the OLD inode for the rest of
#          execution — the new content only takes effect on the NEXT
#          deploy. Net result on the 1.55.2 deploy-ru run: the new
#          ensure block lived only on disk, not in the running bash
#          process; the deploy-ru log had no ``[update.sh] ensuring``
#          line and ``ADMIN_EMAILS`` was never written to ``.env.ru``.
#          Fix: moved ``ensure_env_line`` (and its
#          ``ADMIN_EMAILS=vladimir18kostyal@gmail.com,uk-tora@yandex.ru``
#          call) ABOVE ``git pull``. The OLD inode now executes the
#          ensure block before the file is replaced, so the very
#          first deploy after this change applies the env var. Future
#          edits to update.sh will follow the same one-deploy-lag
#          rule for anything below ``git pull`` — call out the rule
#          in the new comment block at the top of section 0.
#          No backend / frontend code changes.
#          tsc / ruff / pytest (2061 passed, 54 skipped) зелёные.
# 1.55.4 — Корневой фикс «русская админка не видит залогиненного
#          пользователя» вместо очередного костыля.
#          ИСТОРИЯ ПРОБЛЕМЫ: 1.55.0 раскатил мульти-таргет фронт,
#          1.55.1 починил OAuth, 1.55.2 попытался автоматически
#          провижинить ``ADMIN_EMAILS`` на RU edge изнутри
#          ``deploy/ru/update.sh`` — но bash держит открытым
#          original inode, и любая правка update.sh применяется
#          только на следующий deploy (one-deploy lag). 1.55.3
#          переставил ensure_env_line ВЫШЕ git pull, всё равно
#          оставляя one-deploy lag и хардкод emails в shell-скрипте.
#          Никакой наблюдаемости не было: 403 от админ-эндпоинтов
#          ничего не говорил оператору о причине.
#          ЧТО СДЕЛАНО:
#          1) **CI-driven provisioning** в .github/workflows/ci.yml.
#             ``ADMIN_EMAILS`` теперь синкается ОДНИМ источником
#             правды (новый GitHub secret ``secrets.ADMIN_EMAILS``
#             с fallback на «vladimir18kostyal@gmail.com,
#             uk-tora@yandex.ru») и одновременно:
#             - в Railway через ``rl_set ADMIN_EMAILS=$ADMIN_EMAILS
#               -s app -e production --skip-deploys`` в
#               ``deploy-backend``;
#             - в ``/opt/ratemeai/.env.ru`` через ``sync_env
#               ADMIN_EMAILS "$ADMIN_EMAILS"`` в SSH-action
#               ``deploy-ru`` ДО запуска update.sh.
#             Эта логика выполняется в bash CI-раннера, который НЕ
#             заменяется git pull'ом — bash inode quirk полностью
#             обходится.
#          2) **Удалён ensure_env_line из update.sh.** Скрипт теперь
#             делает только то, что должно происходить ON-host: pull,
#             build, restart. Комментарий с пояснением, почему env
#             provisioning живёт в CI, оставлен на месте.
#          3) **Снят ``lru_cache`` с ``_parse_admin_*``** в
#             ``src/api/v1/admin/auth.py``. Кэш фиксировал первое
#             прочитанное значение на всё время жизни процесса —
#             это значило, что если ADMIN_EMAILS попал в ``.env.ru``
#             ПОСЛЕ старта app, он бы никогда не подхватился без
#             рестарта контейнера. Парсинг 2-элементного списка
#             на запрос стоит микросекунды; зато диагностика теперь
#             отражает живое состояние settings.
#          4) **Старт-лог наблюдаемости** в ``src/main.py``:
#             ``admin_gate: ADMIN_USER_IDS=N entries, ADMIN_EMAILS=M
#             entries (mode=primary|edge)``. Если оба whitelist'а
#             пусты — log.error «все /api/v1/admin/* будут 403».
#             Теперь сразу из деплой-лога видно, дошёл ли env до
#             контейнера.
#          5) **Diagnostic endpoint ``GET /api/v1/admin/_whoami``**:
#             auth required, admin gate intentionally NOT required.
#             Возвращает ``{is_admin, matched_via: 'user_id'|'email'|
#             null, identity_emails, whitelist_size:{user_ids,
#             emails}, deployment_mode, market_id}``. НЕ раскрывает
#             whitelist целиком, но мгновенно говорит «у тебя email
#             X, а в ADMIN_EMAILS на этом инстансе 0 записей» —
#             заменяет немой 403 на actionable объяснение.
#          6) **AdminLayout: AdminGateDiagnostics-баннер.** При
#             наличии токена SPA вызывает ``adminWhoami()``;
#             если ``is_admin === false``, рендерит конкретное
#             сообщение в зависимости от состояния (whitelist пуст /
#             email-а нет у identity / email есть, но не в списке).
#             Раньше оператор видел только 403 и догадывался — теперь
#             в баннере чётко написано, что нужно поправить.
#          ОПЕРАЦИОННОЕ:
#          - Опционально создайте GitHub secret ``ADMIN_EMAILS``
#            (Settings → Secrets → Actions). Без него используется
#            хардкод-fallback с двумя текущими операторами.
#          - На existing RU host правится автоматически на следующем
#            deploy через main: CI допишет ADMIN_EMAILS в .env.ru,
#            update.sh поднимет app с новым env.
#          - Стартовый лог покажет ``admin_gate: ADMIN_EMAILS=2
#            entries`` — это валидация, что фикс отработал.
#          ТЕСТЫ:
#          - ``tests/test_api/test_admin_auth.py`` — 9 новых
#            unit-тестов: парсинг ADMIN_EMAILS (case/whitespace,
#            picks-up-after-change), require_admin email-path
#            (accept/reject/case-insensitive/skip-on-empty), все три
#            ветки _whoami (email match / user_id match / no match
#            with empty whitelists / no-email-identity).
#          - ``tests/test_api/test_admin_styles.py`` обновлён:
#            убраны cache_clear() (lru_cache снят), добавлен тест
#            «settings change picks up without restart»,
#            require_admin тесты передают monkeypatched admin_emails
#            и mock-db.
#          - ruff / tsc / pytest зелёные.
# 1.55.5 — РЕАЛЬНАЯ причина «русская админка не видит логин»: на
#          RU-сборке (`VITE_API_BASE_URL=https://ru.ailookstudio.ru`)
#          оба admin-target указывают на ОДИН backend, но slot'ы
#          в localStorage разные:
#             primary → ailook_session_token
#             ru      → ailook_session_token__ru
#          Публичный OAuth (auth.ts → setToken) ВСЕГДА пишет в
#          primary-slot. После того как оператор переключил «Цель»
#          на «RU» (ailook_admin_active_target=ru), `hasToken`
#          в admin-target-context смотрел в ru-slot, который пуст,
#          и `NoTokenForTargetGate` выводил «Нужен вход на target
#          «RU»» — несмотря на валидный токен в primary-slot.
#          Backend это видел нормально (в логах _whoami матчился по
#          email), но frontend даже не доходил до запроса —
#          блокировал на первом гейте.
#          Фикс: `getTokenForTarget(id)` теперь делает fallback на
#          primary-slot, когда `apiBase` запрошенного target'а
#          совпадает с primary apiBase (тот же backend → тот же
#          токен валиден). На Vercel-сборке (primary=Railway,
#          ru=ru.ailookstudio.ru) фолбэка нет — токен Railway не
#          валиден на RU edge, изоляция сохранена.
#          `request()` тоже переехал на `getTokenForTarget`, чтобы
#          Authorization-заголовок выставлялся корректно.
#          NoTokenForTargetGate получил блок «Показать диагностику
#          токенов» (origin + apiBase + storageKey + has/empty по
#          каждому target'у) — теперь видно сразу, где зарыт токен,
#          без обращения к консоли браузера.
# 1.56.0 — Scenario Platform: data-driven visa scenarios + i18n + approval probability flow
#          Phase 2 Scenario Engine (src/scenarios/) backed by data/scenarios.json
#          + 10 visa landings (/visa/*) reusing a generic VisaPage/VisaLanding shell.
#          New approval-probability mode for visa + document-photo: pre-analyze
#          accepts scenario_slug, returns approval_probability (0..100) +
#          visa_compliance checklist instead of score / 10. After regeneration
#          StepGenerate shows a fixed 98.9% (success_probability_after_pct from
#          analysis_display block in scenarios.json). Frontend i18n bundle
#          (RU + EN) splits UI translations from product content.
# 1.57.0 — Visa OAuth fix + full i18n migration + per-market CMS split
#          • OAuth return_path round-trips through Redis state instead of
#            sessionStorage so cross-origin redirects (vercel.app →
#            ailookstudio.ru / ru.ailookstudio.ru) land back on /visa/*
#            instead of /. Backend stores the (sanitised, single-leading-/)
#            return_path with the rest of the OAuth state and re-emits it
#            on the final /auth/callback redirect; SPA prefers the URL
#            query parameter over the legacy sessionStorage fallback.
#          • Wizard / sections / modals / scenario landings / account
#            screens migrated to react-i18next: new namespaces (modals,
#            account, scenarios, policies) plus a much wider RU+EN
#            translation bundle. RU edge keeps showing Russian, the
#            global build now serves English without a runtime toggle.
#          • Per-market CMS: landing_store now picks
#            data/landing_content.json on RU and
#            data/landing_content.<market>.json on the others. New
#            scripts/seed_landing_global.py generates a sibling file
#            with empty text fields so the SPA falls through to its
#            i18n fallbacks on the global build. Admin Landing CMS UI
#            spells out the per-server contract.
# 1.58.0 — i18n holes + CMS fallback hardening + visa testimonials + EN
#          input_quality copy.
#          • CMS fallback fix: introduced coalesceCmsString() in
#            web/src/lib/landing-cms.ts and replaced the naive
#            asString(value, fallback) helper in Pricing / Footer /
#            BeforeAfterSection / ApiSection so an empty CMS string
#            actually falls through to the i18n bundle (root cause of
#            the empty Pricing cards on the global server). Pricing
#            now per-field-merges cms plans on top of the default
#            English plans instead of an all-or-nothing replacement.
#          • Catalog i18n: new catalog namespace (categories,
#            abModels, params, abQualities, creditsPerGen plurals)
#            backs i18n-aware Proxy wrappers around CATEGORIES,
#            AB_MODELS, AB_QUALITIES, PARAMS_BY_MODE and
#            PARAM_LABELS, so wizard / landing surfaces stop leaking
#            "Соцсети / Обычный режим / 1 кредит за генерацию" on EN.
#            formatAbCredits() now goes through i18next plural rules.
#          • Stream facts (StepGenerate streaming carousel) and
#            ~120 landing-style names/descs (landingStyles +
#            STYLES_BY_CATEGORY + DOCUMENT_LANDING_ITEMS +
#            TINDER_PACK_LANDING_ITEMS) read through new
#            wizard:streamFacts.* and styles namespaces.
#          • Visa landings now render <Testimonials/> populated from
#            scenarios:visa.testimonials (4 entries RU+EN). Previously
#            visa pages skipped the social-proof block entirely.
#          • Backend ISSUE_TEXTS_BY_LANG: photo_requirements.py
#            picks RU vs EN by settings.resolved_market_id; legacy
#            ISSUE_TEXTS proxy keeps the input_quality.py call site
#            working unchanged. New tests in
#            tests/test_services/test_photo_requirements.py.
# 1.59.0 — i18n closure (after 1.58.0). Tenth-and-final pass closing
#          the remaining holes that 1.57/1.58 surfaced on the global
#          server.
#          Backend:
#          • src/prompts/{social,dating,cv}.py + perception.py now
#            ship paired _BODY_RU/_BODY_EN bodies; build_prompt(...,
#            lang=...) and PromptEngine.build(..., lang=...) accept an
#            explicit language while _resolve_lang() maps an unset
#            settings.resolved_market_id to RU (back-compat) and
#            ``global``/``en`` to EN. Existing test corpus keeps
#            asserting RU phrasing by passing lang="ru" explicitly.
#          • src/services/photo_requirements.py adds
#            _REQUIREMENTS_BULLETS_BY_LANG / _REJECT_BULLETS_BY_LANG
#            with get_requirements_bullets / get_reject_bullets
#            getters and a _BulletListProxy that keeps the legacy
#            module-level imports working. format_requirements_plaintext
#            and short_requirements_block became language-aware.
#          Frontend:
#          • web/src/lib/api.ts now post-processes catalog API
#            responses through localizeApiStyle(), translating each
#            entry's label/hook through the styles:* namespace with
#            a 7-category fallback. scripts/audit_styles.py audits
#            i18n coverage of data/styles.json against
#            web/src/locales/{ru,en}/styles.json and now exits 0.
#          • Two brand-new i18n namespaces — socialProof (HOME_COPY,
#            CATEGORY_EXTRA_MESSAGES, DOCUMENT_GENERIC_MESSAGES,
#            categoryMessages, feedTemplates with t() interpolation,
#            feedContexts) and testimonials (~50 EN entries). RU
#            testimonials stay hardcoded for parity; getActiveTestimonials()
#            prefers the EN bundle when MARKET_ID=global, falls back to
#            the RU corpus.
#          • DOCUMENT_SOCIAL_PROOF_PRESET converted to a Proxy-backed
#            getter; AI_FACTS eager export removed (use
#            getStreamFacts/getRandomFact). Both lazy-resolve through
#            i18next on every call instead of capturing empty strings
#            during module init.
#          • PlaceholderTone gained a 'visa' variant (#5BA9F2);
#            VisaLanding's <Testimonials/> uses tone="visa" so the
#            visa carousel visually separates from documents.
#          SEO:
#          • useDocumentMeta now resolves canonical URLs through
#            SEO_DOMAINS (RU=ailookstudio.ru, EN=ailookstudio.com),
#            emits ``hreflang`` link tags (ru/ru-ru/en/x-default),
#            and seeds og:locale + og:locale:alternate. sitemap.xml
#            grew xhtml:link alternates per URL.
#          Auto-translate seed:
#          • scripts/seed_landing_global.py gained --mode=auto-translate
#            and --preserve-existing. LANDING_I18N_MAP covers
#            footer/scenario_pricing/proof_counter/how_it_works/final_cta
#            for home/document_photo/visa-* with dotted-path writes
#            (incl. plans[N].title etc). Re-run is idempotent against
#            admin edits when --preserve-existing is set.
#          Tests / CI:
#          • web/vitest.config.ts + src/test/setup.ts wire up jsdom
#            and pin VITE_MARKET_ID=ru for stable i18n. New tests:
#            web/src/lib/landing-cms.test.ts (coalesceCmsString,
#            parseHero, parseProofCounter) and
#            web/src/sections/Pricing.test.tsx (CMS-fallback render).
#            CI workflow gained a ``Vitest (frontend)`` step.
#          • tests/test_prompts/test_localization.py covers
#            _resolve_lang + lang-aware build_prompt for each of
#            social/dating/cv. tests/test_services/test_photo_requirements.py
#            asserts RU/EN parity.
# 1.59.2 — Visa i18n closure. Patches the remaining EN-build holes
#          surfaced after 1.59.0:
#          Frontend:
#          • web/src/sections/HowItWorks.tsx + ru/en landing.json
#            grow a 4th step ("Download or share") so the home page
#            no longer ships only 3 cards in a 4-column grid.
#          • web/src/sections/Footer.tsx LogoEmblem now matches the
#            NavBar size (w-10/w-11 tablet) — fixes the visibly
#            small footer mark on EN/RU.
#          • web/src/lib/api.ts ``localizeApiStyle`` extracts the
#            leading emoji from the original RU label and prepends
#            it to the localized EN copy so AppContext.tsx no longer
#            falls back to the generic ✨ icon for every style.
#          • web/src/data/policies.tsx splits each *Body() into
#            *BodyRu/*BodyEn, dispatching by getAppLanguage(). Full
#            English translation of Privacy/Terms/Consents/Cookie/Refund,
#            adapted for ailookstudio.com (drops 152-FZ, keeps
#            GDPR + CCPA/CPRA). EN policies.json drops the now-unused
#            globalNotice block.
#          • web/src/pages/PrivacyPolicy.tsx switches to i18n keys
#            for "← Back to home", versionPrefix and useDocumentMeta
#            description.
#          • New i18n keys: common.actions.backToHome,
#            seo.privacy.{title,description}, policies.versionPrefix.
#          Backend:
#          • data/scenarios.json: ``analysis_checklist_en`` added to
#            all 10 visa scenarios (schengen/usa/uk/canada/japan/china/
#            uae/australia/korea/india).
#          • src/scenarios/{models,loader}.py: PromptOverrides gains
#            an optional ``analysis_checklist_en`` tuple; loader parses
#            it via a shared _parse_checklist helper.
#          • src/services/visa_compliance.py: ``compliance_checklist``
#            now picks RU vs EN through ``_resolve_lang(market_id)``,
#            with a Russian fallback when the EN translation is
#            missing. Existing call sites (pre-analyze, scenarios
#            API) keep the same signature.
#          Tests:
#          • web/src/lib/api.test.ts — vitest covering
#            ``_extractLeadingEmoji`` + ``localizeApiStyle`` (RU
#            emoji preserved, missing key keeps the original label).
#          • tests/test_scenarios/test_visa_compliance.py +
#            test_loader.py + tests/test_api/test_scenarios.py
#            updated for the EN/RU switch and the new model field.
# 1.59.3 — Dual-currency payments. Primary deployment switches from
#          410-redirect to native Xsolla Pay Station (USD), edge keeps
#          YooKassa (RUB). Tariff grid unified across both: 5/10/20/50
#          photo packs (RU 227/427/727/1527 ₽, EN 3.27/5.27/8.27/19.27 $).
#          New code:
#          • src/services/payments/{__init__,credit_packs,yookassa_provider,
#            xsolla_provider}.py — provider-dispatch layer keyed off
#            settings.payment_provider. ``CreditPack`` now carries Decimal
#            price + RUB/USD currency.
#          • src/api/v1/payments.py — POST /payments/create dispatches by
#            provider, new POST /payments/xsolla/webhook with HMAC-SHA1
#            verification, GET /payments/packs exposes the active catalog
#            for bot/SPA. Edge-only guard removed.
#          • src/main.py mirrors the YOOKASSA_* nullification for
#            XSOLLA_* on edge (and vice versa) so a misconfigured env
#            cannot leak the wrong provider.
#          • src/bot/handlers/mode_select.py: ``topup_currency_keyboard``
#            (RUB/USD branches) → calls primary or edge API depending on
#            the user's selection; per-backend session caches in Redis.
#          Frontend:
#          • web/src/sections/{Pricing,ScenarioPricing}.tsx: 4-tier grid
#            (5/10/20/50) for global pricing, 2-tier (5/10) for visa
#            scenarios. landing.json (ru/en) updated with new prices and
#            saving badges. ``web/src/lib/api.ts`` drops the legacy
#            ``RU_PAYMENTS_SITE_URL`` 410 redirect.
#          Config: CREDIT_PACKS default = 5:227,10:427,20:727,50:1527,
#          new CREDIT_PACKS_USD = 5:3.27,10:5.27,20:8.27,50:19.27,
#          XSOLLA_{MERCHANT_ID,PROJECT_ID,API_KEY,WEBHOOK_SECRET,
#          RETURN_URL} + PRIMARY_API_URL.
# 1.59.4 — Xsolla sandbox-mode + 422-fix. Live diagnosis against the
#          Pay Station Token API revealed two production blockers:
#          • Project 306459 was returning HTTP 422 ``Project is not
#            active`` on every /token call until the merchant runs the
#            mandatory test scenarios in Publisher Account.
#          • Even with project active, ``settings.external_id`` triggered
#            422 ``not required`` because the External-ID toggle is off
#            in the cabinet — and we don't actually need it (idempotency
#            uses the transaction id from the webhook).
#          Fixes:
#          • src/services/payments/xsolla_provider.py: drop
#            ``settings.external_id`` (kept only inside
#            ``custom_parameters`` for tracing); when
#            ``XSOLLA_SANDBOX_MODE=true`` add ``settings.mode=sandbox``
#            and route the user to ``sandbox-secure.xsolla.com`` instead
#            of ``secure.xsolla.com``. Verified end-to-end against the
#            live API — sandbox now returns a real Pay Station token.
#          • src/config.py: new ``xsolla_sandbox_mode`` bool flag.
#          • .env.example: documents the flag, the correct webhook URL
#            (Railway, NOT the Vercel SPA domain) and the sandbox card
#            ``4111 1111 1111 1111`` for QA.
# 1.59.5 — Pricing CMS bypass. Live audit found that the real cause
#          of "Failed to create payment" on the production landings
#          (and the visible "old tariffs" complaint on both
#          ailookstudio.ru/EN and ailookstudio.ru/RU) was a stale
#          ``home`` row in the ``landing_pages`` table on BOTH
#          deployments. It carried the pre-1.59 pack grid:
#          • primary: $0.99/$2.99/$6.99/$11.99 → 1/5/15/30 photos
#          • edge   : 59/199/499/899 ₽         → 1/5/15/30 фото
#          ``Pricing.tsx`` used to per-field-merge those CMS rows over
#          the i18n defaults via ``mergePlans`` (the 1.58 fallback
#          fix). The merge passed ``packQty`` straight through, so the
#          BUY buttons fired ``createPayment(1|15|30)`` against a
#          backend whose ``CREDIT_PACKS_USD``/``CREDIT_PACKS`` only
#          knows {5, 10, 20, 50} — every pack except the lone "5"
#          immediately 4xx'd at ``pack_by_quantity()`` and the SPA
#          fell into the alert.
#          Fix: drop ``plans[]`` from the CMS contract entirely. CMS
#          may still override ``title`` / ``subtitle`` / ``caption`` /
#          ``tryFreeLabel`` of the section, but the tariff grid
#          (price + ``packQty``) is now ALWAYS taken from the i18n
#          bundle, which is generated from the same source as the
#          backend ``CREDIT_PACKS*`` defaults. Stale CMS rows on prod
#          stop being load-bearing — no admin re-seed needed.
#          Test (``web/src/sections/Pricing.test.tsx``) flipped from
#          "merge keeps custom plan" to "ignore plans[] from CMS" so
#          regressions can't sneak the merge back in.
# 1.59.6 — Bot-only fallback guard for the A/B image-gen path.
#          User-visible bug: a Telegram generation on 2026-05-10
#          ~19:24 UTC came back through Nano Banana 2 instead of GPT
#          Image 2 and had drifted identity. Root cause: the
#          ``UnifiedImageGenProvider`` symmetric A↔B fallback (added
#          in 1.24.2) treated bot traffic the same as the web SPA, so
#          any transient GPT-2 failure (FAL queue timeout, OpenAI
#          5xx, OpenAI content-policy hit on the face) silently
#          re-ran the request on NB2 — with a prompt built for GPT-2,
#          ``thinking_level=fast`` (bot defaults to ``quality=low``)
#          and no face-preserve post-chain. The bot is contractually
#          "always GPT" (Telegram has no Premium picker), so the
#          fallback was never supposed to apply to it.
#          Fix: thread a ``source`` tag through the request chain —
#          bot → /analyze (Form field) → task ctx → edge→primary
#          payload → /internal/process-analysis → task ctx →
#          pipeline → executor → provider.params. The bot tags every
#          request with ``source="telegram_bot"``; the unified
#          provider refuses the A→B fallback when it sees that tag
#          and lets the original exception propagate so the bot
#          shows a generic "try again" message instead of returning
#          a mis-routed image. Web clients (no tag) keep the legacy
#          A→B and B→A backstops. The B→A direction is intentionally
#          NOT gated by the tag — falling forward to GPT-2 is always
#          safe for the bot contract.
#          New Prometheus signal:
#          ``style_mode_override_total{reason="fallback_skipped_telegram_bot"}``
#          increments every time the guard fires.
#          Regression tests in ``tests/test_providers/test_unified_provider.py``
#          (4 new cases) lock the four corners: bot+GPT failure
#          raises; routed_backend stays on gpt_image_2; web caller
#          still gets A→B fallback; bot+NB2 (hypothetical future) still
#          falls back to GPT-2.
# 1.60.0 — Two-region clean architecture, P0–P5 of the
#          ``two-region_clean_architecture`` plan.
#
#          Decisive shifts:
#
#          P0 — critical fixes.
#          * VK ID on RU edge was silently broken because CI synced
#            ``VK_CLIENT_ID``/``VK_CLIENT_SECRET`` while Pydantic
#            reads ``vk_id_app_id``/``vk_id_app_secret``
#            (src/config.py:413-415). Renamed env vars throughout
#            ``deploy-ru``; the workflow now strips legacy
#            ``VK_CLIENT_*`` lines from ``.env.ru`` on every deploy.
#          * ``yandex_oauth_init`` now returns HTTP 503 when
#            ``YANDEX_CLIENT_ID``/``SECRET`` are missing, instead of
#            building an authorize URL with an empty client_id and
#            landing the user on Yandex's generic error page that
#            looked like our bug.
#
#          P1 — two regional Telegram bots, language-routed.
#          * ``settings.peer_bot_username`` (src/config.py) holds the
#            "other region's" bot username; CI provisions it
#            (``AI_Look_Studio_bot`` on RU edge, ``RateMeAI_bot`` on
#            Railway). ``TELEGRAM_BOT_USERNAME`` is also pinned per
#            region.
#          * New ``LanguageGuardMiddleware`` runs BEFORE
#            ``UserRegistrationMiddleware`` and short-circuits
#            cross-region traffic before any DB write happens —
#            ru-speaking users on the Global bot get a deep-link to
#            ``@RateMeAI_bot`` and the chain aborts, and vice-versa.
#            This is the boundary that makes 152-ФЗ residency real.
#
#          P2 — domain rollout machinery.
#          * Split the 443 server-block for ``ru.ailookstudio.ru``
#            out of ``deploy/ru/nginx.conf`` into two extra-templates
#            (``ru-legacy.conf`` = SPA+API, ``ru-legacy-redirect.conf``
#            = 301 to apex). ``ensure_ru_legacy_block`` in
#            ``deploy/ru/update.sh`` keeps exactly one of them in the
#            ``nginx_extra_conf`` named volume, picked by the
#            ``RU_LEGACY_REDIRECT_ENABLED`` GitHub Variable.
#          * Updated ``docs/VARIANT_B_EXTERNAL_CHECKLIST.md`` for the
#            two-bot layout and the post-cutover state.
#
#          P3 — admin UX.
#          * New ``AdminStatusBanner`` (web/src/components/admin/)
#            shows the operator their auth state on THIS region
#            (via ``/api/v1/admin/_whoami``) plus a button to the
#            paired region's admin. Same-Origin Policy is the
#            architectural choice, not a bug.
#          * Added ``/admin → /admin/landing`` redirect so the bare
#            URL is no longer a 404.
#
#          P4 — PII guardrails in code.
#          * ``RemoteAnalysisRequest`` and ``RemotePreAnalyzeRequest``
#            switched to ``ConfigDict(extra="forbid")``. Anything the
#            edge might accidentally bolt on (email, telegram_id,
#            first_name) is now rejected with HTTP 422.
#          * ``internal_user_id`` on edge-proxy tasks is now
#            ``uuid5(NAMESPACE_DNS, f"edge-proxy.{edge_task_id or
#            trace_id or fresh}")`` instead of a single sentinel —
#            breaks k-anonymity joins on the primary side. The User
#            row is created on demand to keep the FK constraint
#            happy.
#          * New golden test
#            ``tests/test_services/test_remote_ai_payload.py``
#            asserts the JSON keys are whitelisted, no PII attribute
#            names or email-shaped values are present, and the
#            ephemeral policy_flags survive every hop.
#          * ``PIIFilter`` (src/utils/log_filters.py) now masks
#            emails, phones, ``telegram_id=…`` patterns and PII-keyed
#            dict args (``first_name``, ``language_code`` etc).
#          * ``_cleanup_ephemeral_artifacts`` zeros out
#            ``task.input_image_path`` and the storage-pointer fields
#            in ``task.result`` AFTER deleting the files, then
#            commits — no more dangling paths in Postgres dumps.
#
#          P5 — documentation.
#          * New ``docs/ARCHITECTURE.md`` is the source-of-truth doc
#            for the two-region layout (PII invariants, edge→primary
#            delegation, bot routing, DNS phases). README links to
#            it from a new "Архитектура" section with the five
#            invariants laid out for new contributors.
#
#          Migrations / breaking changes:
#          * CI now expects GitHub-secrets ``VK_ID_APP_ID`` /
#            ``VK_ID_APP_SECRET`` instead of ``VK_CLIENT_*``. The old
#            names are no longer read; CI will strip them from
#            ``.env.ru`` on the next deploy.
#          * Edge requests with unknown JSON fields will now fail
#            with HTTP 422 (previously they were silently dropped).
# 1.60.1 — Hotfix: revert the ``ru-legacy.conf`` split.
#          The 1.60.0 design moved the :443 ``ru.ailookstudio.ru``
#          server-block out of ``deploy/ru/nginx.conf`` into a named
#          volume (``/etc/nginx/conf.d/extra/ru-legacy.conf``), but on
#          the first deploy the volume was empty for a couple of
#          seconds → nginx started without any :443 listener, and
#          https://ru.ailookstudio.ru/health returned ``Connection
#          refused``. Reverted: the 443 block lives back in
#          ``deploy/ru/nginx.conf`` (read-only mount, always present
#          at startup). Phase-3 301-redirect is now a manual one-line
#          edit instead of a GitHub Variable. ``RU_LEGACY_REDIRECT_ENABLED``
#          variable and ``ensure_ru_legacy_block`` function removed.
# 1.60.2 — Test fix: ``tests/test_api/test_oauth.py`` now patches
#          ``settings.yandex_client_id`` etc. with autouse fixture so
#          the 503-guard added in 1.60.0 doesn't trip on CI (CI doesn't
#          load the prod ``.env``, so the values were blank).
# 1.60.3 — RU edge ops fix: ``resolve_a`` in ``deploy/ru/update.sh``
#          now asks 8.8.8.8 / 1.1.1.1 directly instead of the VPS's
#          systemd-resolved.  Some VPS providers (Selectel in our
#          case) cache apex A-records for far longer than the
#          authoritative TTL, which caused ``maybe_dns_cutover`` to
#          see the old Vercel-edge IP and silently skip certbot.
# 1.60.4 — RU edge cert hardening: ``maybe_dns_cutover`` now checks
#          the SAN of an existing ``/etc/letsencrypt/live/ailookstudio.ru``
#          lineage.  If SAN doesn't include ``ailookstudio.ru`` (e.g.
#          because a previous certbot run failed challenge but kept
#          the lineage directory, leaving stale contents that nginx
#          happily served as the default :443 cert) we
#          ``certbot delete`` and re-issue, then full-restart nginx
#          (instead of ``-s reload``) to drop any stale file handles
#          on the old cert.pem inode.  Symptom this fixes:
#          ``NET::ERR_CERT_COMMON_NAME_INVALID`` on
#          https://ailookstudio.ru because nginx kept serving the
#          ``ru.ailookstudio.ru`` cert even after the DNS cut-over.
#          Smoke test now uses ``curl --resolve`` to the VPS public
#          IP and refuses ``-k``, so a CN/SAN mismatch surfaces as a
#          loud WARN instead of a green "200" via insecure curl.
# 1.60.5 — RU edge cert hardening, follow-up: 1.60.4 SAN-check
#          reported ``cert already covers ailookstudio.ru`` (so the
#          right cert *is* present on the VPS), but live probes
#          still showed ``CN=ru.ailookstudio.ru`` for SNI
#          ``ailookstudio.ru``.  Root cause: ``nginx -s reload``
#          doesn't always re-evaluate the ``include extra/*.conf;``
#          glob when a file is dropped into the volume from a
#          sibling container — the running master keeps its cached
#          config tree.  Fix: ALWAYS ``docker compose restart nginx``
#          after copying the TLS template into the named volume,
#          and dump ``ls -la /etc/nginx/conf.d/extra/`` plus the
#          loaded ``server_name``/``listen 443`` lines so we can
#          see in CI logs exactly which server-blocks nginx ended
#          up with.
# 1.61.0 — RU edge architectural cleanup (one commit, no patches):
#          single cert + single :443 server-block in the repo, with
#          server_name ailookstudio.ru www.ailookstudio.ru and an
#          explicit www→apex 301 redirect. ru.ailookstudio.ru is
#          gone end-to-end: no DNS record, no nginx server-block,
#          no cert lineage (deleted by bootstrap-certs.sh), no
#          mentions in CI or docs. The "lazy include" of TLS via
#          a named volume populated at runtime — root cause of
#          every 1.60.x regression — is removed: deploy/ru/nginx.conf
#          now declares ssl_certificate paths directly and lives
#          read-only in the repo, mounted as `:ro` into the nginx
#          container. update.sh becomes ~180 lines shorter: no
#          maybe_dns_cutover, no certbot calls, no SAN checks, no
#          DNS resolution branching — just rebuild → restart → health.
#          Cert issuance moves out-of-band to deploy/ru/bootstrap-certs.sh,
#          triggered by the new ``Bootstrap RU edge cert`` workflow.
#          The RU Telegram bot @RateMeAI_bot finally runs: added a
#          dedicated docker service in polling mode (no public ports,
#          BOT_WEBHOOK_URL deliberately unset), so the bot that already
#          had a token in .env.ru actually has a process to back it.
#          CI: new optional ``RU_TELEGRAM_BOT_TOKEN`` secret syncs the
#          RU bot's token to .env.ru without colliding with the
#          Railway-side @AI_Look_Studio_bot; ``BOT_WEBHOOK_URL=``
#          stripped from .env.ru every deploy to enforce polling
#          invariant. Smoke tests now ``curl --resolve``-pin the
#          domain to the VPS public IP so a stale GitHub-runner DNS
#          cache (the 1.60 footgun) can't mask a real outage.
# 1.62.0 — One Telegram bot, Telegram Stars, per-language landing.
#          The 1.60–1.61 two-bot layout (RU @RateMeAI_bot on the VPS in
#          polling mode + Global @AI_Look_Studio_bot on Railway via
#          webhook) is collapsed into a single bot — @AI_Look_Studio_bot
#          on Railway, webhook only. Root cause: РКН blocks egress to
#          api.telegram.org from RU hosting, which makes polling from
#          the VPS impossible (1.61.0 service entered a restart loop
#          with TelegramNetworkError). Webhook still works because
#          Telegram opens the connection inbound from its side, not
#          ours.  Changes by phase:
#            * Phase A — emergency stop of ratemeai-bot-1 on the VPS
#              via an extended ru-diagnostic.yml ``stop_bot`` input.
#            * Phase B — docker-compose.ru.yml: bot service deleted.
#              ci.yml: stops syncing TELEGRAM_BOT_TOKEN / BOT_WEBHOOK_URL
#              into .env.ru and strips them on every deploy.
#            * Phase C — src/bot/app.py::_resolve_bot_api_base_url
#              always returns ``settings.api_base_url``; the
#              EDGE_API_URL fork is removed.  src/bot/handlers/mode_select.py:
#              all USD/RUB/EDGE/PRIMARY pack-callbacks (topup_cur:*,
#              buy_rub:*, buy_usd:*, buy:*) and the matching session
#              helpers (_ensure_edge_session / _ensure_primary_session
#              and friends) are gone.
#            * Phase D — src/bot/middlewares/language_guard.py deleted;
#              dispatcher no longer registers it.  ``settings.peer_bot_username``
#              kept for backward-compat but ignored.
#            * Phase E — Telegram Stars: ``credit_packs_xtr`` env
#              ("5:25,10:45,20:85,50:200"), get_credit_packs_xtr() +
#              xtr_pack_by_quantity() helpers, new
#              src/bot/handlers/stars.py with send_invoice /
#              pre_checkout_query / successful_payment, plus
#              src/services/payments/stars.py::record_stars_purchase
#              (idempotent by telegram_payment_charge_id stored in
#              CreditTransaction.payment_id with a ``stars:`` prefix).
#              topup_currency_keyboard becomes a one-button "Pay with
#              Telegram Stars" — XTR works on every Telegram client
#              including RU users via Fragment.com / Premium IAP.
#            * Phase F — per-language landing helper
#              ``settings.resolve_landing_url(language_code)``:
#              ru/be/kk/uk/ky → ailookstudio.ru, everyone else →
#              ailookstudio.vercel.app.  src/bot/handlers/link.py and
#              consent.py route through it.  CI syncs
#              BOT_WEB_LANDING_URL_RU / _DEFAULT on Railway.
#            * Phase G — cross-region link.  New internal endpoints on
#              Railway (``src/api/v1/internal_bot.py``):
#              ``POST /api/v1/internal/bot/stars/grant`` (called by
#              the bot ``successful_payment`` handler) and
#              ``GET /api/v1/internal/bot/users/{tg_id}/profile``
#              (read-only, X-Internal-Key).  The RU edge ``claim-link``
#              redeem (src/api/v1/users.py) calls the GET endpoint
#              and mirrors the bot-side image_credits into the web
#              user, dedupe-guarded by Redis ``bot_balance_merged:{tg_id}``.
#            * Phase I — tests + docs.  Rewrote
#              tests/test_bot/test_bot_routing.py (single-region),
#              added tests/test_bot/test_stars_payments.py (payload
#              round-trip + record_stars_purchase idempotency +
#              landing URL resolver) and tests/test_api/test_internal_bot.py
#              (auth + idempotency on the integration stack).
#              ARCHITECTURE.md / README.md updated.
#          External actions still required (Phase J):
#            * BotFather → @RateMeAI_bot: description "Бот переехал в
#              @AI_Look_Studio_bot".  Do NOT delete the bot — keeps
#              the username reserved.  Broadcast is impossible
#              because that bot can no longer reach api.telegram.org.
# 1.62.1 — RU deploy hotfix: deploy/ru/update.sh still ran
#          ``docker compose up app bot`` after 1.62.0 removed the
#          ``bot`` service from docker-compose.ru.yml, causing CI
#          deploy-ru to fail with ``no such service: bot``.
# 1.62.2 — Stars: deploy-backend now syncs INTERNAL_API_KEY and
#          CREDIT_PACKS_XTR to the Railway ``bot`` service (the app
#          already had the key; the bot was empty → «internal key»
#          after successful_payment). Default credit_packs_xtr raised
#          to 5:127 / 10:227 / 20:427 / 50:927 stars.
# 1.62.3 — CI deploy-ru: retry /health behind nginx; catalog/tasks
#          HTTP probes no longer use curl -f under ``set -e`` (avoid
#          silent exit 22 before readiness/auth diagnostics).
# 1.62.4 — RU edge 502-after-deploy hotfix.  ``up -d --build app``
#          gives the new app container a fresh docker-bridge IP, but
#          stock nginx upstream blocks resolve hostnames once at
#          process startup — so nginx kept ``connect() failed (111)``
#          to the OLD app IP until somebody restarted it by hand.
#          update.sh now always ``docker compose restart nginx`` after
#          rebuilding app, which forces a re-resolution of ``app``
#          against docker's embedded DNS.  ru-diagnostic.yml gains a
#          ``restart_nginx=yes`` switch so the same restart can be
#          triggered out-of-band for already-broken hosts.
# 1.62.5 — Telegram-bot generation quality parity with the web client.
#
#          Symptom users reported after the A/B cutover (v1.22): web
#          generations on GPT Image 2 / Nano Banana 2 look natural,
#          while the same models in the bot produce an "oversized head,
#          pasted face" result. The web continues to work even on full-
#          body styles, so the regression cannot be blamed on the
#          underlying edit model — both channels run the same provider,
#          the same ``image_quality=medium``, the same StyleSpec-derived
#          ``image_size``/``aspect_ratio`` and the same GFPGAN-/Code
#          Former-skipped A/B post-chain. The only difference left is
#          the request payload the bot sends to ``/api/v1/analyze`` and
#          the reference image the model receives:
#
#          1) ``framing`` was never forwarded by the bot, so the
#             executor fell back to its compatibility default
#             ``half_body`` (src/orchestrator/executor.py:framing_norm).
#             Web clients default to ``portrait`` (head & shoulders) —
#             see web/src/context/AppContext.tsx. Telegram references
#             from ``message.photo[-1]`` are tight head-and-shoulders
#             previews (max ~1280 px), and edit models preserve the
#             head scale from the reference: drawing a torso around a
#             same-sized head on ``half_body`` framing is exactly the
#             "oversized head" failure mode. Fix: new
#             ``_framing_for_style`` helper in
#             src/bot/handlers/mode_select.py picks framing from the
#             StyleSpec (``needs_full_body`` → ``full_body``, document
#             styles → ``portrait``, otherwise → ``portrait``) and the
#             bot forwards it both as a top-level form field and
#             inside ``input_hints`` so executor.modal_framing reads
#             the same value the web modal would. fal-ai / Google's
#             NB2 prompting guide and the OpenAI GPT Image 2 cookbook
#             both call out "match reference framing to desired output
#             framing" as the primary lever against head/torso
#             proportion drift.
#
#          2) ``enhancement_level`` was bumped per Telegram repeat
#             (``level_for_depth(depth)`` → 1, 2, 3, 4) but for photo
#             modes that value only travels into the LLM analysis
#             builder and perturbs ``base_description`` — the
#             ``ENHANCEMENT_LEVEL_MODIFIERS`` map in
#             src/prompts/image_gen.py only applies to ``emoji``. On
#             the old StyleRouter pipeline the prompt drift was
#             absorbed by PuLID + CodeFormer; on NB2 / GPT-2 it shows
#             through unpredictably. Bot now pins ``enhancement_level
#             = 1`` for ``dating``/``cv``/``social`` (matches the web
#             pin) and keeps the depth ladder only for ``emoji`` where
#             it actually drives the prompt template.
#
#          3) Head-crop proportion lock restored in the prompt. v1.14.2
#             shipped a "head-crop framing hint injected when a full-
#             body style meets a tight crop" guard. The A/B cutover
#             (v1.22) bypassed all StyleRouter / PuLID branches, and
#             with them that hint was no longer reached. The executor
#             now appends a positive-framed proportion-lock paragraph
#             ("Rescale head and shoulders to match the new framing so
#             head, shoulders and torso read as real human proportions
#             …") to the prompt when ``face_area_ratio > 0.35`` and
#             framing is ``half_body``/``full_body`` and the style is
#             not a document style. This is the same threshold the bot
#             already uses for the pre-generation reference-compat
#             warning (src/services/input_quality.py), so the trigger
#             aligns with the existing UX warning. Wording is positive-
#             framed only and passes ``_has_disallowed_negative`` in
#             src/prompts/style_spec.py.
#
#          Scenario_slug forwarding from the bot was considered and
#          dropped — ``image_instructions`` in data/scenarios.json is
#          only populated for visa scenarios, not for core
#          ``dating-photo``/``resume-photo``/``career`` slugs that
#          Telegram users would map to, so plumbing the field through
#          would add complexity for zero prompt-side effect.
#
#          Cost neutrality: all three fixes change ``/analyze`` payload
#          and the in-process prompt string only; FAL call count, model
#          tier, ``image_quality``/``image_size`` and ``aspect_ratio``
#          are untouched. Per-request cost stays identical.
#
#          Tests:
#            * tests/test_bot/test_mode_select_form_data.py rewritten
#              (5 cases): form_data carries framing/input_hints, no
#              image_model pin, framing is dynamic, input_hints is a
#              json.dumps call, enhancement_level=1 for photo only.
#            * tests/test_orchestrator/test_executor_head_crop_hint.py
#              new (5 cases): hint injected on half_body/full_body
#              with tight crop, skipped on portrait framing or when
#              face is small, wording stays positive-framed.
#            * tests/test_bot/test_results_redis_scope.py — assertion
#              flipped to match the v1.59.5 contract (reader does NOT
#              delete the gen_image key, /storage/{task_id} fallback
#              needs it).
# 1.62.6 — CI deploy step tolerant to Railway's queued-deploy state.
#
#          Symptom: every push to main since 06:43 UTC on 2026-05-18
#          failed at ``deploy-backend → Deploy Railway services
#          (sequential)`` with the CLI output
#            ``Deploying app...``
#            ``Indexing... Uploading...``
#            ``Deploys have been paused temporarily``
#            ``Error: Process completed with exit code 1.``
#          while Railway's own status page reported "Fully Operational"
#          and the user confirmed the project was healthy in the
#          Railway dashboard.
#
#          Root cause is a documented Railway platform behaviour: when
#          the global build pool is saturated, free / trial-tier
#          workspaces (and projects that still have a remaining trial
#          balance) get their deploys *queued* until the high-demand
#          window passes. The Railway help station puts it explicitly:
#          "Queued deployments will automatically process once the
#          pause lifts, no action required on your part."
#          ``railway up -d``, however, exits with status 1 the moment
#          the API returns the paused string — even though the deploy
#          is already in the queue and will roll out automatically.
#          Our CI used to treat that exit code as a fatal error and
#          aborted the whole deploy job mid-way (only ``app`` got
#          submitted, ``worker`` and ``bot`` never even tried).
#
#          Fix (``.github/workflows/ci.yml``):
#          * ``deploy_with_retry()`` wrapper around each
#            ``railway up -s <svc>`` call. Up to 5 attempts with
#            exponential backoff; a ``paused temporarily`` response is
#            treated as a SOFT success (the deploy is queued — break
#            and continue to the next service). Hard CLI errors still
#            fail the step after the retry budget.
#          * Health check rewritten to actively verify the new commit
#            SHA shows up on ``/health`` (``settings.deploy_git_sha``)
#            within a ~25 min window, instead of the previous 6 min
#            cap which was too tight for queued rollouts. The step
#            still exits early on first match, so unaffected pushes
#            still complete in under a minute.
#
#          No code-path changes. v1.62.5 generation-parity fixes are
#          untouched; this is strictly a CI-side change to stop
#          painting otherwise-successful deploys red on Railway's
#          high-demand windows.
# 1.64.0 — One-pass anatomy fix + deep dead-code cleanup.
#
#          Anatomy fix (closes long-standing "glued head" / oversized-head
#          regression on tight selfies routed through career / corporate
#          / formal_portrait styles):
#          * ``src/prompts/image_gen.py`` — added
#            ``_COMPOSITION_NUMERICAL_HINT`` (``portrait`` / ``half_body``
#            / ``full_body`` → explicit "face fills X% of frame" directive).
#            Removed conflicting "head and shoulders read as real human
#            proportions" tail from ``IDENTITY_PRESERVE_BLOCK`` — it
#            blocked half-body / full-body framings from honouring the
#            new numerical anchor.
#          * ``src/prompts/model_wrappers.py``:_assemble — inserts the
#            numerical hint **before** ``IDENTITY_PRESERVE_BLOCK`` for
#            non-document styles. Composition wins attention over
#            identity-copy, which is what was missing on the regressed
#            outputs.
#          * ``src/prompts/composition_builder.py`` — new
#            ``CompositionIR.framing`` field so model wrappers can pick
#            the numerical hint without re-parsing ``framing_line``.
#          * ``src/services/reference_preprocess.py`` (NEW) —
#            ``pad_reference_for_framing(image_bytes, face_bbox,
#            framing, target_size)``: re-positions the face on a fresh
#            canvas at the geometry expected by the framing
#            (face_height / face_center_y), edge-blur fill for empty
#            regions. Hard-coded geometry table in
#            ``_FRAMING_GEOMETRY``; portrait→28%/0.30,
#            half_body→15%/0.20, full_body→8%/0.12.
#          * ``src/orchestrator/executor.py`` — pad gate:
#            ``settings.csl_reference_pad_enabled`` AND non-document
#            AND framing ∈ {half_body, full_body} AND
#            composition_class ∈ {face_closeup, unknown} (or
#            face_area_ratio > csl_face_closeup_face_ratio) AND
#            face_bbox is not None. Failure → fallback to raw
#            reference + log. Removed the legacy
#            ``head_crop_proportion_lock`` prompt-tail block (lines
#            641-683 in v1.62.6); it duplicated the new anchor and
#            sat in the worst attention position (after truncation).
#          * ``src/config.py`` — new ``csl_reference_pad_enabled: bool
#            = True`` setting (kill-switch is a no-op for loose-crop
#            inputs because the gate is composition-class-bounded).
#          * ``src/metrics.py`` — new
#            ``REFERENCE_PADDED{framing, composition_class}`` Counter.
#
#          Deep dead-code cleanup (PuLID / Seedream / Reve / StyleRouter
#          / face_crop / generation_mode were no-op'd by the A/B router
#          since v1.21 — the A/B branch fires **before**
#          ``generation_mode`` is consulted, so the third-leg providers
#          never executed in prod):
#          * Deleted files:
#            ``src/providers/image_gen/fal_pulid.py``,
#            ``src/providers/image_gen/fal_seedream.py``,
#            ``src/providers/image_gen/reve_provider.py``,
#            ``src/services/face_crop.py``.
#          * ``src/providers/factory.py`` — removed
#            ``_build_fal_pulid``, ``_build_fal_seedream``,
#            ``_image_gen_provider_mode``, ``_image_gen_strategy``.
#            ``_build_unified_provider`` now takes only ``model_a``
#            and ``model_b``. ``get_image_gen`` is a single FAL-only
#            path.
#          * ``src/providers/image_gen/unified.py`` — collapsed
#            ``__init__`` / ``_pick_backend`` / ``close`` to the
#            two-model A/B contract. Removed ``routed_backend_var``
#            ContextVar + ``get_routed_backend`` helper. Dropped
#            ``style_mode`` label from ``IMAGE_GEN_BACKEND``.
#          * ``src/prompts/style_spec.py`` — removed
#            ``GenerationMode`` alias, ``StyleVariant.generation_mode``
#            / ``StyleSpec.generation_mode`` fields,
#            ``_SCENE_PRESERVE_STYLE_KEYS``, ``detect_generation_mode``,
#            and the ``generation_mode`` arg from
#            ``build_spec_from_legacy``.
#          * ``src/prompts/style_schema_v2.py``,
#            ``src/prompts/style_schema_v3.py`` — dropped
#            ``generation_mode`` field.
#          * ``src/services/style_loader.py``,
#            ``src/services/style_loader_v2.py``,
#            ``src/services/style_loader_v3.py`` — removed
#            ``generation_mode`` read/write logic.
#          * ``src/config.py`` — removed ``pulid_*``, ``seedream_*``,
#            ``image_gen_strategy``, ``model_cost_reve``, ``reve_*``
#            settings.
#          * ``src/metrics.py`` — removed ``STYLE_MODE_OVERRIDE``
#            metric (PuLID/Seedream fallback only). Removed
#            ``REVE_CALLS`` alias. ``estimate_image_gen_cost_usd``
#            now resolves only against GPT-2 / Nano Banana 2.
#          * ``src/prompts/image_gen.py`` — removed
#            ``_OUTPUT_ASPECT_TO_SIZE_PULID`` (1 MP variants for
#            PuLID); ``resolve_output_size`` no longer takes
#            ``generation_mode``. Every non-document style now
#            resolves to 1280×1600 ``portrait_4_3``.
#          * ``src/orchestrator/executor.py`` — removed
#            ``extra["generation_mode"]`` assembly, the PuLID-specific
#            retry escalation block (``pulid_mode`` / ``id_scale`` /
#            ``num_inference_steps`` / ``guidance_scale``), and
#            ``generation_mode`` / ``style_mode`` labels from metric
#            calls. ``_estimate_backend_cost`` and
#            ``_apply_codeformer_post`` no longer take
#            ``generation_mode``. ``_apply_codeformer_post`` now
#            runs on every edit-model output when CodeFormer is
#            enabled (the gating-out branch was PuLID-only).
#          * ``src/api/v1/internal.py`` —
#            ``/diagnostics/image-gen-probe`` collapsed: removed
#            ``mode`` (``identity_scene`` / ``scene_preserve``) and
#            ``provider=styled_router`` knobs; always probes via the
#            unified provider or an explicit A/B provider with the
#            bundled 256×256 face fixture.
#          * ``src/orchestrator/errors.py``,
#            ``src/orchestrator/pipeline.py``,
#            ``src/workers/tasks.py``,
#            ``src/providers/image_gen/fal_nano_banana.py``,
#            ``src/prompts/style_variants.py`` — purged
#            ``ReveAPIError`` imports/handling and StyleRouter / PuLID
#            references in comments.
#          * ``requirements.txt`` — removed ``reve[all]==0.1.2``;
#            Pillow constraint retained for ``reference_preprocess``.
#          * Deleted tests:
#            ``tests/test_providers/test_fal_pulid.py``,
#            ``tests/test_providers/test_fal_seedream.py``,
#            ``tests/test_providers/test_reve_image_gen.py``,
#            ``tests/test_providers/test_reve_body.py``,
#            ``tests/test_services/test_face_crop.py``,
#            ``tests/test_orchestrator/test_executor_generation_mode.py``.
#          * Updated tests:
#            ``tests/test_providers/test_unified_provider.py``
#            (two-model A/B contract only),
#            ``tests/test_orchestrator/test_executor_ab_routing.py``,
#            ``tests/test_orchestrator/test_executor_mask.py``,
#            ``tests/test_orchestrator/test_pipeline.py``,
#            ``tests/test_pre_analyze.py``,
#            ``tests/test_orchestrator/test_executor_seed_and_resolved_slots.py``,
#            ``tests/test_orchestrator/test_executor_identity_unverified.py``,
#            ``tests/test_orchestrator/test_identity_retry.py``,
#            ``tests/test_prompts/test_style_output_size.py``
#            (PuLID 1 MP variant gone — full-body styles now resolve
#            to 2 MP portrait), ``tests/test_api/test_diagnostics.py``
#            (rewritten for the v1.64 probe endpoint),
#            ``tests/test_bot/test_mode_select_form_data.py``,
#            ``tests/test_api/test_analyze_ab.py``,
#            ``tests/test_providers/test_fal_nano_banana.py``.
#          * Added tests:
#            ``tests/test_prompts/test_numerical_composition_anchor.py``,
#            ``tests/test_services/test_reference_preprocess.py``,
#            ``tests/test_orchestrator/test_executor_reference_padding.py``,
#            ``tests/test_orchestrator/test_executor_head_crop_hint.py``
#            (rewritten as a regression test for the removed prompt
#            tail).
#
#          Documentation:
#          * ``docs/ARCHITECTURE.md`` §8.9 "Anatomy fix one-pass (v1.64)"
#            describing numerical anchor + reference padding flow.
#          * ``docs/ARCHITECTURE.md`` §8.7 rollout table extended with
#            W5 (Anatomy fix, ``CSL_REFERENCE_PAD_ENABLED=true``).
#          * ``docs/ARCHITECTURE.md`` §3 sequence diagram updated:
#            FAL.ai only on the AI delegation arrow.
#          * ``docs/master_product_constitution.md`` §9.3 split into
#            pre-gen / post-gen with a new "AnatomyHint" pre-gen
#            entry; §9.3.2 added; §9.6 service architecture rewritten
#            to current FAL-only state; §14 anti-patterns extended
#            with "Identity-block, дублирующий composition" and
#            "Несколько image-gen провайдеров под одним route'ом".
# 1.65.0 — Anatomy Prompt Fix. The v1.64 numerical-anchor wording
#          ("face fills upper 25-30% of frame") improved the
#          "huge head" pathology on document-style edits but only
#          partially closed it on portrait/half/full body styles —
#          edit models treat numeric layout strings as weak signals
#          when they compete with the visual cue of a tight-selfie
#          reference. v1.65 replaces percentage targets with
#          cinematic-vocabulary directives that the supervised
#          training data of FAL Nano Banana 2 / GPT Image 2 Edit
#          actually recognises, simplifies the identity-preserve
#          block so the freed attention budget goes to composition,
#          extends the geometric reference-padding gate to cover the
#          most common request shape ("framing=portrait + tight
#          selfie"), and replaces the hardcoded ``half_body``
#          fallback with a CSL-aware auto-framing resolver shared
#          across the executor and the bot. Zero added FAL spend,
#          zero new model calls, zero quality-tier escalation.
#
#          Prompt contract changes
#          (``src/prompts/image_gen.py`` + ``src/prompts/model_wrappers.py``):
#          * ``_COMPOSITION_NUMERICAL_HINT`` rewritten to use an
#            explicit ``Reframe the reference into …`` operator plus
#            cinematic shot vocabulary (``bust shot`` / ``waist-up
#            shot`` / ``full-length standing shot``) and a physical
#            lens specification (``85mm portrait lens`` for
#            portrait/half_body, ``35mm`` for full_body). This is the
#            primary lever against edit-models defaulting to "copy
#            the reference's head/torso ratio".
#          * ``IDENTITY_PRESERVE_BLOCK`` trimmed from 9 anchors to 4
#            (face shape, eye shape/colour, hairline, skin undertone)
#            so attention budget shifts from "copy 9 facial details"
#            to "respect the cinematic composition above".
#          * ``PHOTOREAL_BLOCK`` camera anchor swapped from ``50mm
#            lens at eye level`` (the canonical "selfie perspective"
#            wording) to ``85mm portrait lens at chest height`` (the
#            canonical portrait-photography setup that compresses
#            perspective and renders natural head-to-body
#            proportions).
#          * Opener ``_dating_social_change_instruction`` appended a
#            positive-framed ``Recompose the body so head, shoulders
#            and torso read at natural human proportions`` clause so
#            the very first sentence carries an anatomy directive.
#          * ``model_wrappers._assemble`` no longer appends
#            ``ir.framing_line`` to the wire prompt — the cinematic
#            composition hint + the camera spec in ``PHOTOREAL_BLOCK``
#            already carry the framing signal; the duplicate line was
#            giving edit-models contradictory directives. The
#            ``framing_line`` attribute stays on ``CompositionIR``
#            for IR inspection / test tooling.
#
#          CSL auto-framing
#          (``src/services/composition_safety.py`` +
#          ``src/orchestrator/executor.py`` +
#          ``src/bot/handlers/mode_select.py``):
#          * New ``resolve_effective_framing`` is the single source of
#            truth for "what framing should this generation actually
#            run with". Priority: document → user pick (if allowed) →
#            ``needs_full_body`` boost (if allowed) → first canonical
#            framing in ``allowed_framings`` → fail-closed-safe
#            ``portrait``.
#          * ``executor.single_pass`` removed the hardcoded
#            ``half_body`` fallback for invalid / missing framing
#            requests and routes through the resolver instead. Writes
#            ``resolved_framing`` and ``user_picked_framing`` to
#            ``result_dict`` for UI surfacing and observability.
#          * ``bot.handlers.mode_select._framing_for_style``
#            collapsed to a thin wrapper over the resolver so the
#            Telegram-only UX shares the priority matrix with the
#            web wizard.
#
#          Reference-padding gate
#          (``src/orchestrator/executor.py`` + ``src/config.py``):
#          * ``should_pad`` now admits ``framing=portrait`` (the
#            previous gate fired only on half_body / full_body, so
#            the most common request shape — default portrait + tight
#            selfie — went unpadded).
#          * Threshold for "tight enough to pad" decoupled from the
#            CSL FACE_CLOSEUP threshold (0.35) via a new config knob
#            ``csl_reference_pad_face_ratio`` (default 0.28): padding
#            is a soft local PIL operation, so it fires on portrait-
#            class uploads with above-typical face size where the
#            "huge head" pathology shows up without the upload being
#            technically face_closeup.
#
#          Catalog-wide tests + lint
#          (``tests/`` + ``src/services/style_lint.py``):
#          * New ``tests/test_prompts/test_prompt_anatomy_catalog.py``
#            parametrises every registered v3 style × framing and
#            asserts the v1.65 contract end-to-end: ``Reframe the
#            reference into`` present, ``85mm portrait lens`` /
#            ``35mm lens`` present (per framing), legacy ``50mm lens
#            at eye level`` absent, identity anchor present, prompt
#            length within ``[650, 1550]``.
#          * New ``tests/test_services/test_resolve_effective_framing.py``
#            covers every branch of the priority matrix (document,
#            allowed user pick, needs_full_body boost, fail-closed-
#            safe).
#          * Updated ``test_v4_1_anchors.py``,
#            ``test_prompt_diversity_v4.py``,
#            ``test_executor_reference_padding.py``,
#            ``test_executor_ab_routing.py``,
#            ``test_positive_framing.py`` for the new wording / new
#            resolver behaviour.
#          * ``style_lint.py`` extended with ``SCENE_FRAMING_LEAK``
#            (scene_anchor / base_scene contains framing tokens),
#            ``QI_BASE_NONEMPTY`` and ``QI_PER_MODEL_TAIL_NONEMPTY``
#            (style-level quality overrides competing with the
#            central PHOTOREAL_BLOCK). ``preview_lint.py`` shows 0
#            dirty styles on the live ``data/styles.json``.
#
#          Observability
#          (``src/orchestrator/executor.py``):
#          * New INFO log ``framing_resolved`` carries ``user_picked``
#            and ``resolved_framing`` so we can measure how often the
#            auto-picker overrides a missing / invalid user pick.
#          * VLM ``proportions_natural=false`` now surfaces a soft
#            user-facing notice ("На фото пропорции тела могут
#            выглядеть необычно. Попробуй фото, где видно плечи и
#            часть торса.") on the result screen. No retry — zero
#            extra cost.
#
#          Documentation:
#          * ``docs/ARCHITECTURE.md`` §8.9 rewritten for the v1.65
#            cinematic hint + extended padding gate + auto-framing
#            resolver flow; §8.7 rollout table extended with W6
#            ("Anatomy v1.65").
#          * ``docs/master_product_constitution.md`` §9.3 updated to
#            require cinematic vocabulary in composition hints and
#            forbid duplicate framing-phrases across prompt stages.
#
#          Cost guarantee (every line audited):
#          * PIL padding: $0 (local, +50-200 ms only on tight selfies
#            already in the gate).
#          * Auto-framing resolver: $0.
#          * Prompt rewrite: $0 (same resolution / quality / model).
#          * VLM ``proportions_natural`` warning: $0 (uses the
#            existing single-pass VLM call, no retry).
#          * Quality tier, ``thinking_level``, image_size,
#            aspect_ratio, identity_retry, CodeFormer, Real-ESRGAN:
#            untouched.
# 1.66.0 — Style Catalog Normalization. The v1.65 prompt-assembly fix
#          made the wire prompt consistent across styles, but a follow-
#          up production audit found that CV/career styles (legal_finance,
#          boardroom, corporate, decision_moment, speaker_stage,
#          intellectual, video_call …) still produced "giant head"
#          artefacts despite identical inputs, while lifestyle/sport
#          styles (gym_fitness, dating_park, hiking) did not. Root
#          cause: the *style data* in ``data/styles.json`` carried
#          hidden portrait-pose directives:
#
#            * ``expression`` fields encoded a studio-headshot mood:
#              ``Authoritative steady expression, distinguished gravitas,
#              composed gaze``, ``steady leadership gaze``, ``executive
#              vision``, ``timeless authority``, ``commanding charismatic
#              presence``. Edit models read those as "render this person
#              as a cropped studio portrait" and they overrode the v1.65
#              cinematic anchor through recency bias.
#            * ``scene_anchor`` / ``base_scene`` encoded implicit poses
#              (``leather chair``, ``behind a desk``, ``webcam-friendly
#              framing``) that made models compress the torso.
#            * Tailored-suit ``default_clothing`` strings lacked an
#              explicit shoulder cue, which made edit models draw an
#              over-narrow silhouette and exaggerated the head.
#
#          Scope: 33 non-studio styles across all three modes
#          (CV, dating, social). Studio-portrait styles
#          (``formal_portrait``, ``studio_elegant``) and document styles
#          (``photo_3x4``, ``passport_rf``, ``visa_eu`` / ``visa_us``,
#          ``photo_4x6``, ``driver_license``) are exempt — those genres
#          are by-design tight headshots.
#
#          Implementation:
#          * ``scripts/migrations/2026_05_styles_v4_anatomy/migrate.py``
#            — one-shot, idempotent, token-level JSON migration. Writes
#            a backup to ``data/styles.json.bak.v165`` on first run.
#            Migration log lands in ``MIGRATION_LOG.md`` alongside the
#            script.
#          * ``src/prompts/image_gen.py``:
#              - New ``_STUDIO_PORTRAIT_STYLE_KEYS`` frozenset +
#                ``is_studio_portrait_style`` helper (mirrors the
#                existing ``_DOCUMENT_STYLE_KEYS`` pattern).
#              - ``PHOTOREAL_BLOCK`` renamed the lens descriptor from
#                ``85mm portrait lens`` to ``85mm short-telephoto lens``
#                (and the matching string in ``_COMPOSITION_NUMERICAL_HINT``).
#                The duplicate ``portrait`` mention in the prompt was
#                acting as a recency-bias headshot pull that fought the
#                cinematic ``bust shot`` anchor.
#          * ``src/services/composition_safety.py``:
#              - ``resolve_effective_framing`` gained an
#                ``is_studio_portrait`` kwarg (default False) that
#                short-circuits to ``portrait``, mirroring the existing
#                ``is_document`` branch. Callers (executor +
#                ``bot/handlers/mode_select``) pass the new flag.
#          * ``src/orchestrator/executor.py``:
#              - CV-mode reference-padding boost. ``mode=cv`` +
#                non-studio style now uses
#                ``settings.csl_reference_pad_face_ratio_cv`` (0.22)
#                instead of the default 0.28. CV users upload
#                passport-style selfies far more often than dating /
#                social users; the boost catches the
#                ``face_area_ratio ≈ 0.22..0.28`` band that the v1.65
#                threshold missed. Studio-portrait styles do NOT inherit
#                the boost — they're meant to be tight crops.
#          * ``src/config.py``:
#              - New ``csl_reference_pad_face_ratio_cv: float = 0.22``.
#          * ``src/services/style_lint.py``:
#              - Three new rules with a shared exempt-whitelist:
#                ``EXPRESSION_PORTRAIT_LEAK`` (error),
#                ``SCENE_POSE_LEAK`` (error), ``WARDROBE_TIGHT_SUIT``
#                (warning). The catalog test
#                ``tests/test_prompts/test_style_catalog_clean.py``
#                pins the migrated form so a future admin edit can't
#                silently regress.
#
#          Tests:
#          * New ``tests/test_prompts/test_style_catalog_clean.py``
#            walks every catalog entry and asserts the v1.66 invariants.
#          * New ``tests/test_services/test_style_lint_v166.py`` covers
#            the three new rules end-to-end (positive + exempt branches).
#          * New ``tests/test_orchestrator/test_executor_padding_cv_mode.py``
#            pins the CV-mode boost matrix: pads at 0.25 for
#            ``legal_finance`` (CV) but not for ``warm_outdoor`` (dating)
#            or ``formal_portrait`` (studio whitelist).
#          * ``test_v4_1_anchors.py`` / ``test_prompt_diversity_v4.py``
#            / ``test_prompt_anatomy_catalog.py`` updated for the new
#            ``85mm short-telephoto lens`` token; the legacy
#            ``85mm portrait lens`` is now asserted absent.
#          * ``test_resolve_effective_framing.py`` extended with
#            studio-portrait short-circuit cases.
#
#          Documentation:
#          * ``docs/ARCHITECTURE.md`` §8.9 gained a new subsection 5
#            ("Style Catalog Normalization (v1.66)"); §8.7 rollout
#            table gained row W7.
#          * ``docs/master_product_constitution.md`` §9.3 updated to
#            forbid portrait-pose tokens in expression / scene_anchor /
#            background.base on non-studio styles, and to document the
#            CV-mode padding boost.
#
#          Cost guarantee:
#          * JSON normalisation: $0 (text edit of equal-or-shorter
#            length, no extra prompt tokens).
#          * Studio whitelist short-circuit: $0.
#          * CV-mode padding boost: $0 (preprocess, same as v1.65 path).
#          * Lens-token rename: $0 (substring substitution).
#          * Quality tier, ``thinking_level``, image_size,
#            aspect_ratio, identity_retry, CodeFormer, Real-ESRGAN,
#            VLM gate budget: untouched.
# 1.67.0 — Anatomy fix v3: padding gate + identity-tail. Production
#          audit of v1.66 generations confirmed that the "huge head"
#          pathology persists on standard half-body uploads (mirror_aesthetic,
#          legal_finance, executive_portrait at typical user shapes),
#          even though gym_fitness and similar body-cued styles produce
#          natural proportions. Root cause is structural, not stylistic:
#
#          1. **Padding gate dead-zone.** v1.65/v1.66 padding fired on
#             ``composition_class in ("face_closeup", "unknown") OR
#             face_area_ratio > 0.28``. The most common upload shape —
#             head-and-shoulders selfie with ``face_area_ratio ≈
#             0.10..0.17`` and ``composition_class = PORTRAIT`` — fell
#             through BOTH gates. With the reference unmodified the
#             edit-model copied its head/torso ratio verbatim, and the
#             cinematic ``Reframe …`` prompt directive could not
#             override that strong visual signal.
#          2. **Identity-block placement.** v1.65 placed
#             ``IDENTITY_PRESERVE_BLOCK`` immediately after the
#             cinematic anchor, with wording ``identical face shape, eye
#             shape and colour …``. Edit-models read ``identical face
#             shape`` geometrically — as "match the reference head's
#             relative size in the frame" — which directly fought the
#             composition anchor. Identity won this conflict because of
#             its position (early-attention) and emphatic word
#             (``identical``).
#
#          Fix:
#
#          * ``src/config.py``: ``csl_reference_pad_face_ratio`` lowered
#            0.28 → 0.10; ``csl_reference_pad_face_ratio_cv`` lowered
#            0.22 → 0.10 (boost collapsed into the main threshold —
#            both modes need the same low gate).
#          * ``src/orchestrator/executor.py``: ``is_tight`` widened
#            from ``composition_class in ("face_closeup", "unknown")``
#            to ``composition_class in ("face_closeup", "portrait",
#            "half_body", "unknown")``. Effect: padding now fires on
#            every non-FULL_BODY upload routed through portrait /
#            half_body / full_body framings (document and studio
#            portrait styles remain exempt by the framing gate and the
#            studio-portrait short-circuit respectively).
#          * ``src/prompts/image_gen.py``:
#              - ``IDENTITY_PRESERVE_BLOCK`` rewritten. Drop "face
#                shape" anchor (geometric reading). Reword to
#                "Use the reference photo as the identity source —
#                preserve the same person's facial features: eye shape
#                and colour, hairline, skin undertone." Identity is
#                textural now (eyes / hairline / skin undertone),
#                non-geometric.
#          * ``src/prompts/model_wrappers.py``:
#              - ``_assemble`` reorders anchors. Identity moved from
#                "between composition anchor and scene" to the very
#                tail (after ``PHOTOREAL_BLOCK``). Composition owns
#                the early-attention budget; identity owns the
#                recency-bias slot. The doc-style branch is unchanged
#                (vendor policy is non-negotiable).
#
#          Tests:
#          * ``test_executor_reference_padding.py``: pinned new gate.
#            Two new regression tests:
#              - ``test_pad_fires_on_typical_half_body_upload_v167`` —
#                face_area_ratio=0.13 + composition_class="portrait"
#                MUST trigger padding (THE main fix).
#              - ``test_pad_fires_on_half_body_class_at_low_ratio_v167`` —
#                HALF_BODY class triggers padding even at ratio 0.07.
#            ``test_pad_skipped_on_loose_portrait_under_threshold`` was
#            inverted (now ``test_pad_fires_on_portrait_class_under_old_threshold``)
#            because v1.67 explicitly DOES pad portrait-class uploads.
#            ``test_pad_skipped_when_face_small`` renamed to
#            ``test_pad_skipped_only_for_true_full_body`` and adjusted
#            to use composition_class=full_body + face_area_ratio=0.05
#            (the only path that still skips padding under v1.67).
#          * ``test_executor_padding_cv_mode.py`` deleted — v1.66 CV
#            boost collapsed into the main threshold in v1.67, so the
#            mode-divergence semantics it pinned no longer apply.
#          * ``test_v4_1_anchors.py``, ``test_prompt_diversity_v4.py``,
#            ``test_prompt_anatomy_catalog.py``,
#            ``test_numerical_composition_anchor.py``: updated to the
#            new identity wording (``preserve the same person's facial
#            features``) and to forbid the legacy ``identical face
#            shape`` token.
#
#          Documentation:
#          * ``docs/ARCHITECTURE.md`` §8.7 rollout table gained row
#            W8 ("Padding Gate + Identity-Tail v1.67"); §8.9 gained a
#            new subsection 6 ("Padding Gate Audit & Identity Tail
#            (v1.67)") detailing the structural diagnosis and the
#            three-rivet fix.
#          * ``docs/master_product_constitution.md`` §9.3 updated:
#            point 4 ("Reference padding") rewritten to reflect the
#            v1.67 gate (padding fires on every non-full-body
#            upload); IDENTITY_PRESERVE_BLOCK description updated to
#            the new wording.
#
#          Cost guarantee:
#          * Padding is a local PIL preprocessing step — no FAL cost,
#            no extra roundtrip. The gate expansion just shifts MORE
#            uploads through that no-cost path.
#          * Prompt reorder: same tokens, just shuffled — identical
#            token count, no compression-budget impact.
#          * Identity wording change: ``-9 chars`` net (slightly
#            shorter), no cost impact.
#          * No model/quality/tier/size change. The 5–6.5¢ per image
#            average (gpt_image_2 medium) inherited from v1.66 stays
#            put.
# v1.70.0 (May 2026): Anatomy Cleanup — drop all head-anchor clauses.
#          The v1.65..v1.69 doctrine accreted FIVE head-cues into the
#          non-document wire prompt (cinematic ``head-and-shoulders
#          bust shot``, face-area percentage anchor, ``head subtly
#          turned`` pose hint, ``head, shoulders and torso`` opener
#          tail, ``head-to-body proportions`` multi-pass clauses) plus
#          per-framing lens specs and a separate light-match clause.
#          The May 2026 audit (docs/ANATOMY_INVESTIGATION.md) showed
#          that the head/body cue ratio in the wire prompt had crept
#          to 5:1 — which over-anchored portrait perspective on every
#          framing and reproduced the "huge head, tiny shoulders"
#          pathology on tight-selfie references. ``gym_fitness``
#          worked as the control because its ``clothing.default``
#          already showed the shoulder line (``fitted athletic tank
#          top``).
#
#          v1.70 reverses the direction. Every head-cue clause is
#          deleted; the wire prompt is now 500–700 chars (was ~1450)
#          and carries only: opener + scene + wardrobe + (per-framing
#          pose, head-free) + expression + skin texture + light match
#          + identity preserve. The catalog migration v5 appends
#          ``, shoulder line visible`` to ~114 non-sport, non-doc,
#          non-studio styles so the model receives the body
#          geometry from the wardrobe channel (the only one that
#          actually controls torso scaling under FAL edit models).
#
#          Touchpoints (8 in prompt code):
#          * ``src/prompts/image_gen.py``:
#              - ``_COMPOSITION_NUMERICAL_HINT`` → ``{}`` (was 3 entries
#                of cinematic ``Reframe ... bust shot ... head
#                occupying upper third`` wording).
#              - ``_FACE_AREA_ANCHOR_BY_FRAMING`` → ``{}`` (was 3
#                ``Anchor: the face occupies ...`` strings).
#              - ``_POSE_BY_FRAMING["portrait"]`` rewritten without
#                "head" (``subject turned slightly off the central
#                axis`` instead of ``head subtly turned off ...``).
#              - ``_FRAMING_PROMPT_DIRECTIVES``: portrait dropped
#                ``head-and-shoulders close-up``; full_body dropped
#                ``head-to-toe``.
#              - ``_dating_social_change_instruction`` opener tail
#                changed from ``Recompose the body so head, shoulders
#                and torso read at natural human proportions.`` to
#                ``Show the subject naturally with realistic body
#                proportions.``
#              - ``PHOTOREAL_BLOCK`` collapsed: lens + DoF wording
#                removed; only skin texture + light-match instruction
#                survive. ``_PHOTOREAL_BY_FRAMING`` becomes a stub
#                pointing at the single block.
#              - ``_STEP_CHANGE`` clauses: ``head-to-body proportions``
#                → ``body proportions``.
#          * ``src/prompts/model_wrappers.py``:
#              - ``_assemble`` document fallback changed from
#                ``Centered head-and-shoulders framing.`` to
#                ``Centered framing.`` (document styles still receive
#                the doc hint when present; only the fallback wording
#                changed).
#          * ``src/config.py``:
#              - ``numerical_percent_anchor_enabled``: True → False.
#              - ``light_match_clause_enabled``: True → False
#                (clause dissolved into PHOTOREAL_BLOCK).
#
#          Defensive lint:
#          * ``src/services/style_lint.py`` — new
#            ``forbidden_head_tokens_in_prompt`` helper backing the
#            ``NO_HEAD_TOKEN_IN_PROMPT`` rule. Used by the new
#            ``test_no_head_cues.py`` to sweep every registered style
#            × every framing on CI.
#
#          Catalog migration:
#          * ``scripts/migrations/2026_05_styles_v5_shoulders/migrate.py``
#            appends ``, shoulder line visible`` to ``default_clothing``
#            and ``clothing.default.{male,female,neutral}`` for 114
#            non-sport, non-document, non-studio-portrait styles.
#            Idempotent (a re-run finds the cue and leaves the field
#            alone). Backup written to
#            ``data/styles.json.bak.v169``.
#
#          UX:
#          * ``web/src/components/wizard/StyleSettingsModal.tsx``
#            shows an inline hint under the framing chip-row when the
#            user manually picks "По пояс" or "В полный рост". Two new
#            keys in ``wizard.json`` (ru/en): ``framingManualHintHalf``
#            and ``framingManualHintFull``. The auto-framing path is
#            unchanged (no hint is shown when the wizard chose the
#            framing).
#
#          Tests:
#          * Deleted: ``test_percent_anchor.py``,
#            ``test_numerical_hint_matches_geometry.py``,
#            ``test_executor_head_crop_hint.py``.
#          * Rewritten: ``test_prompt_anatomy_catalog.py``,
#            ``test_photoreal_by_framing.py``,
#            ``test_no_lens_duplication.py``,
#            ``test_v4_1_anchors.py``, ``test_prompt_diversity_v4.py``,
#            ``test_numerical_composition_anchor.py``,
#            ``test_positive_framing.py`` — every assertion now
#            FORBIDS the head/lens/DoF tokens instead of requiring
#            them.
#          * New: ``test_no_head_cues.py`` — sweeps every photo style
#            × framing and asserts the lint helper returns no leaks.
#          * Goldens: all 30 fixtures in
#            ``tests/fixtures/golden_prompts/*.txt`` regenerated.
#
#          Cost guarantee:
#          * Prompt is now shorter (-50%, ~750 fewer chars on
#            average) — slight compression-budget gain, no FAL cost
#            change. No model / quality / tier / size change.
#          * Migration is a one-shot JSON edit + one-line APP_VERSION
#            bump.
# 1.70.1 — Wizard "stale-result" fix: clicking a step pill in the
#          StepBar to navigate BACK from a completed generation
#          (e.g. step 4 -> step 1) now drops the cached
#          ``generatedImageUrl`` before changing the active step.
#          Previously the user would walk forward through steps 2-3
#          without re-uploading and see the OLD photo on step 4
#          instead of the "Generate" CTA. The fix mirrors the
#          ``resetGeneration`` already wired into the "Ещё стиль" /
#          "Ещё фото" buttons inside ``StepGenerate`` — backward
#          navigation has the same "redo from here" intent.
#
#          Additional symmetric reset: ``uploadPhoto`` in
#          ``AppContext`` now clears ``framing`` (back to
#          ``portrait``) and ``selectedStyleKey`` (back to empty)
#          on every fresh photo. Without that, a previous
#          ``full_body`` choice could survive into a face-closeup
#          upload and briefly show "full_body locked" before the
#          ``allowedFramings`` useEffect snapped it; ``selectedStyleKey``
#          could survive a mode switch via re-upload. ``setMode``
#          already does both resets — the upload path now matches.
#
#          Frontend-only patch: zero backend changes, zero prompt
#          changes, zero new flags. No DB or contract changes.
# 1.70.2 — Wizard UX polish (Stage 2 of audit fix-up).
#          Three independent frontend-only patches:
#          * F1: snap ``selectedStyleKey`` to ``''`` when the
#            ``effectiveStyleList`` no longer contains it. Previously
#            switching mode/scenario kept the stale key — the UI fell
#            back to ``effectiveStyleList[0]`` for display but
#            ``generate()`` still sent the dead key downstream, which
#            either 404'd inside ``style_loader`` or rendered the
#            wrong style. Implemented as a small ``useEffect`` in
#            ``AppContext`` next to the ``effectiveStyleList``
##            memo.
#          * F7: trim ``verifyImageUrl`` from ``retries=3,
#            delayMs=2000`` (worst-case 6s "hang" before refund) to
#            ``retries=2, delayMs=1200`` (worst-case 1.2s). When an
#            R2/CDN URL is bad it stays bad — the extra 4.8s of
#            retries virtually never recovered and felt like a
#            stalled UI. Refund path is unchanged.
#          * F8: when ``handleStepClick`` navigates BACK in the
#            wizard, prune ``visitedSteps`` to ``<= stepIdx`` so the
#            StepBar no longer shows checkmarks on steps the user
#            hasn't traversed on this fresh pass. Keeps the
#            "completed" set in sync with actual forward progress
#            after a redo, complementing the 1.70.1
#            ``resetGeneration`` call on the same path.
#
#          Zero backend changes, zero prompt changes, zero new flags.
# 1.70.3 — Prompt-pipeline dead-code cleanup (Stage 3 of audit fix-up).
#          The v1.70 anatomy cleanup emptied two of the head-anchor
#          dicts (``_COMPOSITION_NUMERICAL_HINT`` and
#          ``_FACE_AREA_ANCHOR_BY_FRAMING``) to ``{}`` but left the
#          ``if ir.framing in <empty_dict>: …`` branches in
#          ``model_wrappers._assemble``. Those branches were 100%
#          unreachable in production — every framing key missed the
#          empty dict and the body never executed.
#
#          This patch drops both unreachable branches (19 lines) and
#          rewrites the file-level and function-level docstrings so
#          they document the assembly order that actually ships
#          today. The dicts and their feature flags
#          (``numerical_percent_anchor_enabled``,
#          ``photoreal_by_framing_enabled``) are deliberately kept
#          in ``image_gen``/``config`` as REGRESSION MARKERS — the
#          ``tests/test_prompts/`` suite asserts they stay empty, so
#          a future PR cannot silently re-introduce the v1.65/v1.68
#          head-cue cluster without breaking a guard test.
#
#          Behaviour is BYTE-FOR-BYTE identical to 1.70.2 — every
#          framing × every model already produced the same wire
#          prompt because the deleted branches never ran. Verified
#          locally with the 30-style golden fixtures and the full
#          2466-test suite (0 failures).
# 1.70.4 — Remove flags that became no-op after 1.70 / 1.70.3
#          (Stage 4 of audit fix-up). Two ``settings`` knobs are
#          dropped:
#
#          * ``numerical_percent_anchor_enabled`` — gated the
#            ``_FACE_AREA_ANCHOR_BY_FRAMING`` injection. v1.70
#            emptied the dict and v1.70.3 removed the assembler
#            branch, leaving the flag with zero consumers in
#            production. Default was already ``False``.
#          * ``photoreal_by_framing_enabled`` — gated the per-framing
#            tail swap in ``model_wrappers._resolve_tail``. v1.70
#            collapsed every entry of ``_PHOTOREAL_BY_FRAMING`` to
#            ``PHOTOREAL_BLOCK`` so the gate was a verified no-op
#            (the ``test_flag_is_no_op_on_wire_prompt`` parametrised
#            test asserted it for every framing × ON/OFF in the
#            test suite for a full release cycle).
#
#          The companion ``test_flag_is_no_op_on_wire_prompt`` is
#          renamed to ``test_wire_prompt_has_skin_anchor_and_no_lens``
#          and parametrised only on framing — the flag dimension
#          collapsed naturally. The ``_PHOTOREAL_BY_FRAMING`` dict
#          and the ``_FACE_AREA_ANCHOR_BY_FRAMING={}`` /
#          ``_COMPOSITION_NUMERICAL_HINT={}`` markers survive in
#          ``image_gen`` purely as regression guards: tests assert
#          they remain in the expected shape so a future PR cannot
#          silently bring the v1.65/v1.68 head-cue cluster back.
#
#          Wire prompt: byte-for-byte identical to 1.70.3.
# 1.70.5 — executor.single_pass partial decomposition (Stage 6 of
#          audit fix-up). Two pure-ish extracts from the 1100+ line
#          monolith:
#
#          * :meth:`ImageGenerationExecutor._resolve_framing` — owns
#            the CSL-aware framing pick. Reads ``framing`` /
#            ``user_input_hints`` / ``input_quality``, writes
#            ``result_dict["resolved_framing"]`` (and
#            ``user_picked_framing`` when present), emits the
#            ``framing_resolved`` INFO log, and returns
#            ``(framing_norm, is_document, is_studio_portrait_style,
#            user_picked_framing)``. ~75 lines lifted.
#          * :meth:`ImageGenerationExecutor._build_prompt` — owns
#            the v2 prompt build. Wraps
#            ``PromptEngine.build_image_prompt_v2`` plus the path-tag
#            derivation (v2 / v3 / v3_promoted), the
#            substitution-warning bucket and the
#            ``resolved_slots`` / ``variant_id`` persistence. Raises
#            ``RuntimeError`` on a missing StyleSpec (same as before).
#            ~100 lines lifted.
#
#          Behaviour is BYTE-FOR-BYTE identical — same writes to
#          ``result_dict``, same metrics, same error path, same log
#          lines. Verified locally with the full 2568-test backend
#          suite (0 failures). The five remaining decomposition
#          candidates (provider params, reference padding, retry
#          loop, post-processing, persist / metric) touch the
#          critical retry / VLM gate path and are intentionally
#          deferred to a dedicated PR with full goldens.
# 1.70.6 — Fail-fast on broken styles.json (Stage 7 of audit fix-up).
#          The legacy hardcoded fallback in ``image_gen`` —
#          ``DATING_STYLES`` / ``CV_STYLES`` / ``SOCIAL_STYLES`` re-
#          registered via ``build_spec_from_legacy`` when JSON load
#          raised — was retired. The data was last touched in 2025
#          and would silently ship STALE specs to users while the
#          real catalogue was broken. The new behaviour escalates
#          a missing or corrupt ``data/styles.json`` into a
#          ``RuntimeError`` at import time, logged at ``CRITICAL``
#          with the original exception chained.
#
#          Companion cleanup in ``prompts/engine.py``: the
#          ``_MODE_STYLE_DICTS`` and ``_MODE_PERSONALITY_DICTS``
#          module-level maps were dead code (defined here, consumed
#          nowhere in ``src/``). Removed.
#
#          Unused imports follow-on: ``build_spec_from_legacy`` and
#          ``STYLE_VARIANTS`` were imported only by the deleted
#          fallback and are dropped from ``image_gen``'s import
#          block. ``image_gen`` itself still exports the legacy
#          ``DATING_STYLES`` / ``DATING_PERSONALITIES`` / etc. dicts
#          because ``style_lint`` and ``test_style_spec_hygiene``
#          read a few of them — eliminating those big literals is
#          a separate, larger cleanup PR.
#
#          Happy-path behaviour identical to 1.70.5 — JSON loads
#          fine in every prod / staging / test environment we
#          touch. The only visible change is that a future deploy
#          with a broken styles.json will refuse to start instead
#          of silently downgrading to last-year's catalogue.
# 1.70.7 — Tech-debt cleanup Phase 1, step 1.1: dormant image-gen
#          providers removed. ``src/providers/image_gen/chain.py``
#          (the ``ChainImageGen`` fallback wrapper) had no runtime
#          consumer in ``src/`` and is dropped. The companion files
#          ``fal_pulid.py``, ``fal_seedream.py`` and
#          ``reve_provider.py`` had already been deleted in an
#          earlier round but were still referenced in
#          ``docs/DEVELOPMENT.md``, ``docs/architecture/reserved.md``
#          and the ``_fal_queue_base.py`` module docstring — those
#          references are now refreshed to describe the unified FAL
#          pipeline (GPT Image 2 + Nano Banana 2). No behaviour
#          change; pure repo hygiene preparing for Phase 1 step 1.2
#          (flux_kontext wire removal).
# 1.70.8 — Tech-debt cleanup Phase 1, step 1.2: ``flux_kontext`` wire
#          removed from ``src/prompts/model_wrappers``. The model has
#          been off the AB whitelist (``AB_MODELS_ALLOWED = {nano_banana_2,
#          gpt_image_2}``) and absent from ``data/styles.json`` for
#          several releases, so ``wrap_for_flux_kontext`` and the
#          ``model == "flux_kontext"`` branch of ``wrap_for_model``
#          were dead code. Dropped together with the
#          ``QUALITY_PHOTO_FLUX`` constant and the
#          ``"flux_kontext": QUALITY_PHOTO_FLUX`` entry of
#          ``_MODEL_DEFAULT_TAIL``. ``wrap_for_model`` now falls back
#          to GPT Image 2 for any unknown model name (matches the
#          previous default-via-dict-key behaviour through the
#          executor). Companion test rename in
#          ``test_output_size_ssot.test_unknown_model_returns_none``
#          to a neutral placeholder model name. No behaviour change
#          on the supported wire.
# 1.70.9 — Tech-debt cleanup Phase 1, step 1.3:
#          ``src/prompts/style_variants.py`` removed (2 767 lines).
#          ``STYLE_VARIANTS`` and ``variants_for`` had a single
#          documented consumer — the JSON-load exception fallback in
#          ``src/prompts/image_gen.py`` — which was converted to a
#          hard ``RuntimeError`` in v1.70.6 (Stage 7). With no
#          runtime importer left, the legacy variant table is gone.
#          ``docs/CLEANUP_STYLE_V2.md`` updated to mark Step 4 of
#          the cleanup roadmap done. No behaviour change.
# 1.70.10 — Tech-debt cleanup Phase 1, step 1.4: ~815 lines of
#          legacy text-prompt dictionaries dropped from
#          ``src/prompts/image_gen.py`` (``DATING_STYLES``,
#          ``CV_STYLES``, ``SOCIAL_STYLES``, ``DATING_PERSONALITIES``,
#          ``CV_PERSONALITIES``, ``SOCIAL_PERSONALITIES`` and the
#          ``_STYLE_OVERRIDES`` gender-clothing override table).
#          They were the JSON-load fallback content; v1.70.6 converted
#          that path into a hard ``RuntimeError`` and v1.70.9 removed
#          ``STYLE_VARIANTS``, leaving these maps with no consumer.
#          The hygiene regression
#          ``test_no_edit_compatible_false_overrides`` was renamed to
#          ``test_no_edit_compatible_false_specs`` and now iterates
#          ``STYLE_REGISTRY`` directly. ``image_gen`` shrank from
#          1 552 to ~720 lines. No runtime behaviour change.
APP_VERSION = "1.70.10"

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
APP_VERSION = "1.25.5"

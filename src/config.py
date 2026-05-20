from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Telegram
    telegram_bot_token: str = ""
    telegram_bot_username: str = "AI_Look_Studio_bot"
    # ``peer_bot_username`` is a legacy field kept for backward-compat
    # with older .env files.  In 1.60–1.61 the project ran two bots
    # (RU on VPS + Global on Railway) and this name was used by the
    # now-removed ``LanguageGuardMiddleware`` to redirect users across
    # regions.  Since 1.62.0 there is only one bot
    # (``@AI_Look_Studio_bot`` on Railway), so the value is ignored.
    peer_bot_username: str = ""

    # OpenRouter (LLM)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "google/gemini-2.0-flash-001"

    # Database
    database_url: str = "postgresql+asyncpg://ratemeai:ratemeai@localhost:5432/ratemeai"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    # Staged upload bytes for worker (same Redis as ARQ); avoids broken bind-mounts between API/worker
    task_input_redis_ttl_seconds: int = 3600
    # TTL for generated image cache in Redis (seconds); bridges worker→app on Railway (3 days default)
    gen_image_redis_ttl_seconds: int = 259200
    # TTL for staged (sanitized) image bytes in Redis before worker picks them up
    privacy_stash_ttl_seconds: int = 900
    # Privacy GC: physical deletion of generated/* + share cards after N seconds
    privacy_result_retention_seconds: int = 259200  # 72h

    # Storage
    storage_provider: str = "local"
    storage_local_path: str = "./storage"
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "ratemeai"
    s3_region: str = "auto"
    s3_public_base_url: str = ""
    s3_presign_ttl_seconds: int = 3600
    # If local file missing, try GET {base}/storage/{key} (e.g. worker -> http://app:8000 in Docker)
    storage_http_fallback_base: str = ""

    # Image generation provider selector.
    # ``mock``   — local stub (dev / CI).
    # ``unified`` — production FAL queue clients (GPT Image 2 / Nano
    # Banana 2 picked per-request by the AB router; only ``unified``
    # remains after the v1.20→v1.64 cleanup of Reve / Replicate /
    # PuLID / Seedream).
    # The factory normalises any non-``mock`` value to ``unified`` so
    # legacy ``.env`` files (``auto``, ``fal_flux2``, ``reve``…) still
    # boot — the field stays a plain ``str`` for backward compatibility.
    image_gen_provider: str = "unified"

    # FAL.ai (https://fal.ai — FLUX.1 Kontext [pro] / image-to-image edit)
    # Получить токен: https://fal.ai → Dashboard → Keys (формат: uuid:secret).
    # В .env храним под именем FAL_API_KEY, но fal-client также читает FAL_KEY.
    fal_api_key: str = ""
    # v1.24.2: default to the async queue endpoint. The previous
    # ``https://fal.run`` default was the sync ``subscribe``-style host,
    # which does NOT return ``status_url`` / ``response_url`` in the
    # submit response and pushes our queue providers into the fallback
    # URL synthesis path. Production always overrides this via
    # ``FAL_API_HOST=https://queue.fal.run`` (see ``.env.example``), but
    # a missing env var on a fresh deploy used to silently land on the
    # sync host and 404 on every status poll.
    fal_api_host: str = "https://queue.fal.run"
    fal_model: str = "fal-ai/flux-pro/v1.1"
    fal_guidance_scale: float = 2.5
    fal_safety_tolerance: str = "6"
    fal_output_format: str = "jpeg"
    fal_max_retries: int = 3
    fal_request_timeout: float = 120.0
    fal_poll_interval: float = 1.0

    # YooKassa payments
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = "https://t.me/{bot_username}"

    # Credit packs: pack_size:price_rub (comma-separated), edge / YooKassa
    credit_packs: str = "5:227,10:427,20:727,50:1527"
    # Primary / Xsolla (USD), decimal prices allowed
    credit_packs_usd: str = "5:3.27,10:5.27,20:8.27,50:19.27"
    # Telegram Stars (XTR) — used only inside the bot via sendInvoice.
    # Format: ``credits:stars,credits:stars,…``.  Telegram requires
    # integer star amounts.  Telegram takes a ~30% IAP fee, so prices
    # account for the cut.  Adjust via env var ``CREDIT_PACKS_XTR``.
    credit_packs_xtr: str = "5:127,10:227,20:427,50:927"

    # Xsolla Pay Station (primary deployment only)
    xsolla_merchant_id: str = ""
    xsolla_project_id: str = ""
    xsolla_api_key: str = ""
    xsolla_webhook_secret: str = ""
    xsolla_return_url: str = ""
    # Use Xsolla sandbox endpoints (no project activation required for test cards).
    # Set to True until Publisher Account → Project → "Activate" is granted.
    xsolla_sandbox_mode: bool = False
    # Bot / tooling: public HTTPS URL of primary API for USD checkout session
    primary_api_url: str = ""

    # Admin (bootstrap API keys for B2B)
    admin_secret: str = ""
    api_key_pepper: str = ""
    # Comma-separated list of user IDs (string form, matches DB.User.id)
    # that are allowed to call the /api/v1/admin/* endpoints. Empty
    # value (default) means the admin surface is locked down for every
    # request, returning 403. Set on Railway via
    # ``ADMIN_USER_IDS=uuid1,uuid2,uuid3`` for the operators who manage
    # the style catalog through the admin panel.
    admin_user_ids: str = ""
    # 1.50.9 — alternative whitelist by email. Easier to onboard new
    # admins: drop ``ADMIN_EMAILS=alice@x.com,bob@y.com`` and the gate
    # accepts any user whose google/yandex/vk-id identity carries one
    # of the listed emails in ``profile_data.email``. Either env var
    # alone is enough; both can be combined.
    admin_emails: str = ""

    # Identity preservation gate thresholds.
    # Identity check is a VLM-based 1:1 photo comparison at quality-gate time;
    # no embeddings are extracted or stored. The LLM returns ``identity_match``
    # on a 0–10 scale (see QUALITY_CHECK_PROMPT in quality_gates.py).
    identity_match_threshold: float = 7.0
    identity_match_soft_threshold: float = 5.0

    # v1.17 introduced a VLM-based identity-retry loop: when the first
    # generation came back with identity_match < identity_match_threshold,
    # ``ImageGenProvider.generate()`` was re-run with a fresh random seed
    # and the higher-scoring candidate kept.
    #
    # v1.70.12 unification: the AB-pipeline shipped its own
    # ``ab_identity_retry_enabled`` flag (default ``False``) because
    # Nano Banana 2 / GPT Image 2 ignore the PuLID-style identity knobs
    # the retry used to bump — so a retry only doubled cost without
    # improving the face. With the legacy hybrid StyleRouter retired,
    # AB is the only path; the old ``identity_retry_enabled=True``
    # branch was unreachable. We keep a single setting here and accept
    # the historical ``AB_IDENTITY_RETRY_ENABLED`` env var via an alias
    # so prod ``.env`` files keep working without touch.
    identity_retry_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "identity_retry_enabled",
            "ab_identity_retry_enabled",
        ),
    )
    identity_retry_max_attempts: int = 1

    # v1.17: conditional GFPGAN pre-clean before the main generation.
    # Activated only when the input is clearly blurry (see
    # ``src/services/face_prerestore.py`` for the activation rules).
    # v1.17.1: default flipped to ON — v1.17.0 was shipped OFF for a
    # smoke-test rollout, but the adaptive 1 MP full-body branch depends
    # on a diffusion-aware upscaler downstream and was degrading face
    # sharpness on "bad input" cases as long as these stayed disabled.
    # Any provider failure still falls back to the original bytes, so
    # pre-restoration remains strictly additive — never load-bearing.
    gfpgan_preclean_enabled: bool = True
    gfpgan_model: str = "fal-ai/gfpgan"

    # v1.17: Real-ESRGAN final upscale instead of the PIL LANCZOS
    # fallback used since 1.16. v1.17.1: default flipped to ON for the
    # same reason as ``gfpgan_preclean_enabled`` — the adaptive 1 MP
    # full-body branch bets on Real-ESRGAN x2 to restore resolution
    # afterwards. Fallback to LANCZOS on any provider failure is
    # automatic in the executor, so turning this on cannot regress
    # below the previous (LANCZOS-only) behaviour.
    real_esrgan_enabled: bool = True
    real_esrgan_model: str = "fal-ai/real-esrgan"

    # Flat USD cost estimates for the new auxiliary providers (used by
    # metrics/cost reporting; actual FAL invoice is what we pay).
    model_cost_fal_gfpgan: float = 0.002
    model_cost_fal_real_esrgan: float = 0.002

    # ------------------------------------------------------------------
    # v1.18 hybrid image-gen pipeline — PuLID + Seedream v4 Edit + CodeFormer
    # ------------------------------------------------------------------
    # v1.64 — PuLID, Seedream and the StyleRouter were retired. The
    # production path is FAL-only edit-mode with two A/B models
    # (GPT Image 2 Edit + Nano Banana 2 Edit) selected per-request via
    # ``image_model``. See ``src/providers/factory.py``.
    #
    # Settings removed in v1.64 (kept here as historical anchors for
    # ``git log -S`` searches; do NOT reintroduce):
    #   * ``image_gen_strategy``     — single FAL path, no strategy fork.
    #   * ``pulid_*`` (10 keys)      — PuLID provider gone.
    #   * ``seedream_*`` (3 keys)    — Seedream provider gone.

    # CodeFormer — post-generation face polish.
    # https://fal.ai/models/fal-ai/codeformer
    #
    # v1.64 policy: CodeFormer runs on every edit-model output that
    # survives the local post-processing (crop / x2 LANCZOS) when
    # the gate fires (``codeformer_enabled`` + valid FAL key + face
    # large enough). Pre-v1.64 the gate excluded ``identity_scene``
    # (PuLID) outputs because the 25-step PuLID config produced
    # already-sharp faces that CodeFormer @ fidelity=0.85 would
    # reshape. With PuLID retired, that exclusion no longer applies.
    # ``codeformer_upscale_factor=1.0`` avoids double-paying for a
    # resolution bump that Real-ESRGAN does later. Tiny faces
    # (``face_area_ratio < codeformer_min_face_ratio``) skip the call
    # entirely — polish is invisible at that scale and costs $0.01+.
    codeformer_enabled: bool = True
    codeformer_model: str = "fal-ai/codeformer"
    # v1.19: 0.85 — close to input, fixes artefacts without reshaping.
    codeformer_fidelity: float = 0.85
    # v1.19: no upscale inside CodeFormer — Real-ESRGAN handles that.
    codeformer_upscale_factor: float = 1.0
    # Skip CodeFormer when the detected face is tiny (face_area_ratio
    # below this) — polish is imperceptible and bills ~$0.01/call.
    codeformer_min_face_ratio: float = 0.05
    # Skip CodeFormer on retry attempts (we already polished attempt 1
    # and don't want to pay twice when the retry is about identity,
    # not sharpness).
    codeformer_on_retry: bool = False
    # Bills per megapixel (output). At 2 MP input with upscale_factor=1
    # we pay roughly $0.0021 × 2 MP = $0.0042.
    model_cost_fal_codeformer_per_mp: float = 0.0021

    # ------------------------------------------------------------------
    # v1.21 A/B test — FAL edit-mode models. When ``ab_test_enabled``
    # is True the /analyze endpoint accepts ``image_model`` +
    # ``image_quality`` form fields and the executor routes such
    # requests to the per-model provider via a structured prompt
    # adapter (``model_wrappers._assemble``).
    # v1.22: the A/B path is now the default for every web request.
    # v1.64: there is no longer a legacy StyleRouter alternative —
    # the unified provider IS the path. Flip ``AB_TEST_ENABLED=false``
    # only as a degraded "skip the form field" mode where the default
    # model is used unconditionally.
    # ------------------------------------------------------------------
    ab_test_enabled: bool = True
    # Default A/B model when the client does not send ``image_model``
    # (old bot builds, edge proxy, curl, tests). GPT Image 2 at
    # ``quality=medium`` is the recommended starting tier to guarantee background details.
    ab_default_model: str = "gpt_image_2"
    # When True, UnifiedImageGen retries the other A/B model on transient
    # failures (same policy for web, bot, and internal callers).
    allow_cross_model_image_fallback: bool = True
    # ------------------------------------------------------------------
    # variation_engine_v2_enabled stays as a behavioural flag for the
    # composition builder — it controls whether the builder uses the
    # multi-channel weather / time_of_day / season pools or the legacy
    # single-channel VariationEngine. Always on in v4.1 (no legacy
    # caller depends on the off path), kept here as a kill switch.
    variation_engine_v2_enabled: bool = True
    # ------------------------------------------------------------------
    # v4.1 (May 2026): the runtime routing flags
    # ``style_schema_v2_enabled``, ``unified_prompt_v2_enabled`` and
    # ``style_schema_v3_enabled`` were REMOVED. The pipeline now has
    # exactly one path: ``engine.build_image_prompt_v2`` → v3 spec
    # (with v2-promoted spec auto-fallback for non-migrated styles)
    # → ``composition_builder.build_composition_v3`` → per-model
    # wrapper. There is no longer a v1 fallback for photo styles.
    # ------------------------------------------------------------------
    # prompt-pipeline-v4 (May 2026) — natural faces + diversity overhaul.
    # When True (default) the per-model wrappers use the new
    # preserve-first prompt ordering (change → IDENTITY_PRESERVE_BLOCK →
    # scene → clothing → expression → framing → PHOTOREAL_BLOCK →
    # PASTED_ON_GUARD) and the short v4 tails (~250 chars vs the v1
    # ~1100-char SCENE_BLEND/ANATOMY/CAMERA stack). The v4 layout fixes
    # the "вклеенное лицо" failure mode by hoisting identity to the
    # first third of the prompt and removing the skin-tone-vs-scene-tone
    # contradiction in the legacy tail. Set to False to instantly roll
    # back to the v1 layout — useful if the v4 prompts regress on a
    # specific style. Cost is unchanged either way (no extra FAL calls).
    prompt_pipeline_v4_enabled: bool = True
    # When True (default in v4) and the user did NOT pass an explicit
    # mood / expression override, the composition builder emits
    # ``EXPRESSION_NATURAL`` ("Keep the subject's natural facial
    # expression and gaze from the reference photo.") instead of the
    # style-spec ``expression`` string. This stops the pipeline from
    # forcing a "warm genuine smile" on every photo regardless of the
    # user's actual mood in the reference. Independent of
    # ``prompt_pipeline_v4_enabled`` — both flags can be toggled
    # separately for finer rollback granularity.
    use_reference_expression_default: bool = True
    # Default quality tier for the A/B models when the web client does
    # not pass an explicit one. Minimum for production is medium.
    ab_default_quality: str = "medium"
    # Nano Banana 2 Edit (Google Gemini 3.1 Flash Image).
    # https://fal.ai/models/fal-ai/nano-banana-2/edit
    # Pricing directly from fal model page:
    #   base = $0.08 / image at 1K resolution, 2K = 1.5×, 4K = 2×,
    #   0.5K = 0.75×. v1.22 bumps the UI ``low`` tier floor from
    #   0.5K (512px — too blurry for prod) to 1K (1024px) so the
    #   cheapest user-visible output is a 1MP picture.
    # v1.24: ``high`` repurposed as "2K + thinking_level=high" (reasoning
    #   edit); 4K tier retired — added latency/cost without a perceptible
    #   realism gain. Price per image matches medium (same pixel budget).
    nano_banana_model: str = "fal-ai/nano-banana-2/edit"
    model_cost_fal_nano_banana_low: float = 0.08  # 1K  (1024px long edge)
    model_cost_fal_nano_banana_medium: float = 0.12  # 2K  (2048px long edge)
    model_cost_fal_nano_banana_high: float = 0.12  # 2K + thinking=high

    # GPT Image 2 Edit (OpenAI ChatGPT Images 2.0 via fal).
    # https://fal.ai/models/openai/gpt-image-2/edit
    # Token-based pricing. Per-tier averages below assume a 1-reference
    # portrait edit with our standard prompt length.
    gpt_image_2_model: str = "openai/gpt-image-2/edit"
    model_cost_gpt_image_2_low: float = 0.02  # 1024² output
    model_cost_gpt_image_2_medium: float = 0.06  # 1536² output
    model_cost_gpt_image_2_high: float = 0.25  # 2048² output

    # Pipeline budget — single hard cap shared by every generation
    # branch. The historical ``segmentation_enabled`` (MediaPipe region
    # masks) and ``multi_pass_enabled`` (advanced multi-stage planner)
    # flags were retired in v1.70.14: segmentation hardcoded to ``off``
    # because the active FAL providers never accepted ``mask_image``;
    # multi-pass is reserved code under ``orchestrator/advanced/`` and
    # only the planner reads its own internal default. Re-introducing
    # either feature should ship behind a fresh, scope-specific flag.
    pipeline_budget_max_usd: float = 0.15

    # Quality gates
    aesthetic_threshold: float = 6.0
    artifact_threshold: float = 0.15
    photorealism_enabled: bool = True
    photorealism_threshold: float = 0.5

    # Pre-flight input quality gate (evaluated locally, no external API calls)
    input_min_resolution: int = 400
    input_min_face_area_ratio: float = 0.04
    input_warn_face_area_ratio: float = 0.10
    input_min_blur_face: float = 40.0
    input_min_blur_full: float = 60.0

    # ------------------------------------------------------------------
    # Composition Safety Layer (CSL) — see src/services/composition_safety.py.
    # ------------------------------------------------------------------
    # Master kill-switch. Off → input_quality still runs but the
    # classifier output is forced to UNKNOWN (= fail-closed-safe
    # ``["portrait"]`` policy); UI continues to receive the field and
    # hides full-body styles. Default ON because CSL ships at warn-only
    # for the first rollout phase.
    composition_safety_enabled: bool = True
    # Phase 2 toggle. When True the heuristic result is refined by
    # MediaPipe Pose (shoulders / hips / knees). Off by default until
    # the Phase 4 calibration confirms Pose is at least as good as the
    # heuristic across the seed dataset.
    body_landmarks_enabled: bool = False
    # CSL heuristic thresholds. Mirrored from
    # src.services.composition_safety.classify_heuristic defaults — exposed
    # here so the Phase 4 calibration script can override them via env
    # without touching code.
    csl_face_closeup_face_ratio: float = 0.35
    csl_face_closeup_space_below: float = 1.0
    csl_portrait_face_ratio: float = 0.18
    csl_portrait_space_below: float = 2.0
    csl_half_body_face_ratio: float = 0.06
    csl_half_body_space_below: float = 4.0
    # Phase 3 advanced override. When True the server honours the
    # ``skip_composition_safety=true`` form field on /api/v1/analyze and
    # the bot / web reveal the "Advanced settings" entry. Off by default
    # — the override exists for power users / QA, not as a default
    # escape hatch.
    composition_safety_advanced_override: bool = False

    # CSL Phase 1.5 (v1.64) — geometric reference padding for tight
    # selfies. When True and the executor's gate passes (non-document
    # style + portrait/half/full_body framing + face_closeup/unknown
    # class OR ``face_area_ratio`` above
    # ``csl_reference_pad_face_ratio``), the executor reshapes the
    # reference image so the face already sits at the correct relative
    # size for the requested framing before the bytes reach the
    # edit-model provider. Implemented in
    # :mod:`src.services.reference_preprocess`. Default ON because the
    # gate itself is the no-op for loose-crop inputs.
    csl_reference_pad_enabled: bool = True

    # v1.65 — reference-padding-specific face_area_ratio threshold.
    # Separate from ``csl_face_closeup_face_ratio`` (0.35) which drives
    # the CSL FACE_CLOSEUP / PORTRAIT classification. Padding triggers
    # on a softer threshold so it also fires on portrait-class uploads
    # with above-typical face size — that is the most common
    # tight-selfie regime where the "huge head" pathology shows up
    # without the upload being technically a face_closeup.
    #
    # v1.67 — lowered 0.28 → 0.10 across all modes. Audit of v1.66
    # production traffic showed the "huge head" pathology persists on
    # standard half-body uploads (face_area_ratio ≈ 0.10..0.17,
    # composition_class=PORTRAIT) because they fell under the 0.28
    # gate. Padding is a local PIL op with no FAL cost and no latency
    # impact, so the new default fires on virtually every non-full-body
    # upload — the upload that *does not need* padding (true full-body
    # at 0.05 face_area_ratio) is excluded by the framing gate, and
    # studio-portrait styles short-circuit to ``portrait`` framing
    # which intentionally keeps a tight crop.
    csl_reference_pad_face_ratio: float = 0.10

    # v1.66 — CV-mode-only override of the padding threshold. CV users
    # routinely upload "passport-style" selfies that fall right above
    # the portrait/face_closeup boundary, so we lower the trigger for
    # mode=cv (excluding studio-portrait styles, which are intended
    # tight headshots). Studio whitelist is enforced in the executor
    # via :func:`src.prompts.image_gen.is_studio_portrait_style`.
    #
    # v1.67 — collapsed to the same 0.10 default. The CV-specific
    # override is retained for forward-compatibility but no longer
    # diverges from the main threshold; both modes need the same low
    # gate after the audit.
    csl_reference_pad_face_ratio_cv: float = 0.10

    # ------------------------------------------------------------------
    # v1.68 — image-quality systemic fix (May 2026).
    # Seven independent feature flags, each gating one piece of the
    # audit remediation plan. Defaults were initially staged (only
    # ``csl_padding_v2_enabled`` shipped on so each prompt-level change
    # could bake under a 24-48h QA window). v1.69 (May 2026) audit
    # showed the prompt-level changes never reached production because
    # no env override was applied; the staging was the bottleneck, not
    # any specific regression in the flagged code. All six remaining
    # flags are now flipped to True by default so the full remediation
    # is active out of the box. Each flag is still individually
    # toggleable via ``<FLAG_NAME>=false`` env override for instant
    # rollback if a specific axis regresses in production.
    # ------------------------------------------------------------------
    # P0.1 — fix ``pad_reference_for_framing`` to interpret ``face_bbox``
    # as ``(x1, y1, x2, y2)`` (the format actually produced by
    # ``input_quality.analyze_input_quality``). The legacy code
    # destructured the tuple as ``(x, y, w, h)``, which mis-computed
    # the face centre and scale on every call. Kill-switch: set to
    # False to fall back to the legacy interpretation.
    csl_padding_v2_enabled: bool = True
    # P1.5 — extend ``_STUDIO_PORTRAIT_STYLE_KEYS`` beyond the two
    # legacy styles to all career-class portraits where tight crop is
    # the intended creative output. When True the wider whitelist
    # forces ``portrait`` framing policy for the listed styles.
    # v1.69 — flipped to True by default.
    studio_portrait_whitelist_v2: bool = True
    # P2.9 — insert ``LIGHT_MATCH_CLAUSE`` before ``IDENTITY_PRESERVE_BLOCK``
    # to explicitly instruct the model to match the subject's lighting
    # to the scene's ambient light (colour temperature, direction,
    # softness). Counters the "studio key light on a sunset terrace"
    # failure mode.
    #
    # v1.70 — flipped back to ``False`` by default. The light-match
    # instruction is now dissolved into the shorter ``PHOTOREAL_BLOCK``
    # ("The lighting matches the scene's ambient light in direction,
    # colour temperature, and softness."), so the separate clause is
    # redundant. Flag preserved for back-compat / instant rollback.
    light_match_clause_enabled: bool = False
    # P2.10 — emit a per-framing pose hint after wardrobe. Anchors a
    # relaxed natural posture so the model does not default to
    # symmetrical "hero stance" framing on full_body or stiff
    # passport-style framing on portrait. v1.69 — flipped to True
    # by default.
    pose_hint_enabled: bool = True
    # P2.7 — single source of truth for output size per (model, framing).
    # Off → legacy ``resolve_output_size`` (style-level
    # ``output_aspect`` → ``_ASPECT_PIXEL_SIZE``) drives the request,
    # which lets each provider snap differently (GPT-2 snaps 1280×1600
    # to 1024×1536 ≈ 2:3, NB2 with ``aspect_ratio=auto`` projects to
    # the closest enum). On → executor consults
    # ``_OUTPUT_SIZE_BY_MODEL_FRAMING`` and:
    #   * GPT Image 2 receives the model's native portrait pixel size
    #     (1024×1536) so there is no snap.
    #   * Nano Banana 2 receives a concrete ``aspect_ratio`` enum +
    #     ``resolution`` tier instead of ``auto``.
    # Each generation result also carries an ``effective_aspect_ratio``
    # string so the web client can crop previews to the actual canvas
    # the model produced. Independent of the other v1.68 flags.
    # v1.69 — flipped to True by default.
    output_size_ssot_enabled: bool = True

    # Legacy prompt_strength (unused in edit mode)
    image_gen_strength: float = 0.45

    # Model cost estimates (USD per call). v1.64 retired ``model_cost_reve``
    # together with the Reve provider; the per-quality A/B numbers above
    # (``model_cost_gpt_image_2_*``, ``model_cost_fal_nano_banana_*``) are
    # the source of truth for ``BUDGET_OVERSPEND_TOTAL``.
    model_cost_gpt_image_2_medium: float = 0.06
    model_cost_gpt_image_2_high: float = 0.12
    model_cost_nano_banana_2: float = 0.02

    # Scoring reproducibility
    scoring_temperature: float = 0.0
    scoring_consensus_samples: int = 1

    # Rate Limits
    rate_limit_daily: int = 3
    # Telegram @username без лимита (через запятую, без @): RATE_LIMIT_EXEMPT_USERNAMES=scrumux
    rate_limit_exempt_usernames: str = ""

    # Одна строка из CI (Railway / GitHub): git rev-parse --short HEAD — для проверки, что на сервере нужный commit
    deploy_git_sha: str = ""

    # OK Mini App
    ok_app_id: str = ""
    ok_app_secret_key: str = ""
    ok_app_public_key: str = ""

    # VK Mini App
    vk_app_id: str = ""
    vk_app_secret: str = ""
    vk_service_token: str = ""

    # Yandex ID OAuth
    yandex_client_id: str = ""
    yandex_client_secret: str = ""

    # VK ID OAuth (web site login, separate from VK Mini App)
    vk_id_app_id: str = ""
    vk_id_app_secret: str = ""

    # Google OAuth (foreign users, main domain only)
    google_client_id: str = ""
    google_client_secret: str = ""

    # Phone SMS OTP (provider: log | sms_aero | twilio)
    sms_provider: str = "log"
    sms_aero_api_key: str = ""
    sms_aero_email: str = ""
    sms_aero_sign: str = "AI Look"

    # WhatsApp Business API
    whatsapp_api_token: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_phone_number_id: str = ""

    # Sessions (Bearer tokens for web / mini apps)
    session_ttl_seconds: int = 86400

    # Phone-OTP auth feature flag.  Default OFF — the /auth/phone/* API
    # exists but no SMS provider is wired up yet (codes only land in
    # logs).  Flip to True once a real SMS provider is integrated.
    phone_auth_enabled: bool = False

    # CORS — extra origins for mini apps (comma-separated)
    cors_extra_origins: str = ""

    # Geo-split deployment: primary (Railway, full AI processing) | edge (RU server, proxies AI to primary)
    deployment_mode: str = "primary"
    # Product-level market boundary: global | ru | th ...
    market_id: str = "global"
    # api | worker | bot | web
    service_role: str = "api"
    # local = compute in this stack, remote = delegate compute to central core
    compute_mode: str = ""
    # URL of the primary Railway API (only used in edge mode)
    remote_ai_backend_url: str = ""
    # Shared secret between edge and primary for /internal/* endpoints
    internal_api_key: str = ""
    # URL of the RU edge server (bot on Railway uses it for payments/auth so webhook + DB match)
    edge_api_url: str = ""
    # ------------------------------------------------------------------
    # CMS replication (Variant B — single CMS hub on Railway).
    # ------------------------------------------------------------------
    # ``editor`` (Railway) accepts admin write requests on
    # ``/api/v1/admin/landing/*`` and pushes every successful save to the
    # configured ``cms_follower_urls``. ``follower`` (RU edge) refuses
    # admin writes (HTTP 403) and only mutates ``data/landing_content.json``
    # via the signed ``POST /internal/cms/replicate`` receiver or the
    # hourly safety-pull ARQ cron. An empty / unrecognised value defaults
    # to ``editor`` so a misconfigured deploy still serves CMS content
    # locally without breaking the public read path.
    cms_role: str = "editor"
    # Master CMS URL — set on followers (e.g. ``https://app-production-6986.up.railway.app``).
    # Empty on the editor itself.
    cms_master_url: str = ""
    # Comma-separated list of follower base URLs (editor only). Each
    # entry is a full HTTPS origin (e.g. ``https://ailookstudio.ru``)
    # without a trailing slash; the replication client appends
    # ``/internal/cms/replicate``.
    cms_follower_urls: str = ""
    # HMAC-SHA256 shared secret used to sign replication payloads. If
    # left empty, the existing ``internal_api_key`` is reused so no
    # extra rotation is required for the initial rollout.
    cms_replication_secret: str = ""
    # Hourly safety-pull on followers compares Railway snapshot hashes
    # to the local CMS file and rewrites it on mismatch. Disabled when
    # ``cms_master_url`` is empty.
    cms_safety_pull_enabled: bool = True
    # v1.26: URL соседнего инстанса, к которому ``/storage`` обратится за
    # файлом, если его нет локально/в Redis/в DB b64. На RU edge ставится
    # в URL primary; на primary — в URL edge. Запрос идёт с заголовком
    # ``X-Internal-Key`` и отвечает пиру полным байтовым стримом (на
    # внутреннем контуре, не публично). Пустая строка отключает fallback
    # — оставляем legacy-поведение.
    edge_peer_url: str = ""

    # App
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = ""
    # 1.62.0 — the single bot routes "go to the website" links by the
    # Telegram ``language_code`` of the sender.  RU-family locales get
    # ``bot_web_landing_url_ru`` (ailookstudio.ru), everyone else
    # ``bot_web_landing_url_default`` (ailookstudio.vercel.app).
    # ``bot_web_landing_url`` is the pre-1.62 single-value form, kept
    # as a fallback so a partial rollback works without env edits.
    bot_web_landing_url: str = ""
    bot_web_landing_url_ru: str = "https://ailookstudio.ru"
    bot_web_landing_url_default: str = "https://ailookstudio.vercel.app"
    bot_webhook_url: str = ""
    bot_webhook_secret: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    @property
    def is_edge(self) -> bool:
        return self.deployment_mode == "edge"

    @property
    def resolved_market_id(self) -> str:
        value = (self.market_id or "").strip().lower()
        return value or "global"

    @property
    def resolved_service_role(self) -> str:
        value = (self.service_role or "").strip().lower()
        return value or "api"

    @property
    def resolved_compute_mode(self) -> str:
        value = (self.compute_mode or "").strip().lower()
        if value:
            return value
        return "remote" if self.is_edge else "local"

    @property
    def uses_remote_ai(self) -> bool:
        return self.resolved_compute_mode == "remote"

    @property
    def payment_provider(self) -> Literal["yookassa", "xsolla"]:
        return "yookassa" if self.is_edge else "xsolla"

    @property
    def resolved_cms_role(self) -> Literal["editor", "follower"]:
        value = (self.cms_role or "").strip().lower()
        return "follower" if value == "follower" else "editor"

    @property
    def is_cms_editor(self) -> bool:
        return self.resolved_cms_role == "editor"

    @property
    def is_cms_follower(self) -> bool:
        return self.resolved_cms_role == "follower"

    @property
    def resolved_cms_replication_secret(self) -> str:
        secret = (self.cms_replication_secret or "").strip()
        if secret:
            return secret
        return (self.internal_api_key or "").strip()

    @property
    def resolved_bot_web_landing_url(self) -> str:
        """Legacy single-value landing URL (pre-1.62 fallback).

        New call-sites should use :func:`resolve_landing_url` to get a
        per-language URL.  We keep this property so older code paths
        (e.g. partial rollbacks) keep working.
        """
        candidate = (self.bot_web_landing_url or self.web_base_url or "").strip()
        return candidate.rstrip("/")

    def resolve_landing_url(self, language_code: str | None = None) -> str:
        """Pick the landing URL by Telegram ``language_code``.

        RU-family languages (ru / be / kk / uk / ky) → RU landing.
        Empty / unknown / non-RU → default landing.

        Falls back to :attr:`resolved_bot_web_landing_url` if either
        of the per-language URLs is unset (covers the case where
        someone partially rolls back env vars).
        """
        primary = (language_code or "").split("-", 1)[0].strip().lower()
        ru_family = {"ru", "be", "kk", "uk", "ky"}
        ru_url = (self.bot_web_landing_url_ru or "").strip().rstrip("/")
        default_url = (self.bot_web_landing_url_default or "").strip().rstrip("/")
        fallback = self.resolved_bot_web_landing_url
        if primary in ru_family:
            return ru_url or fallback or default_url
        return default_url or fallback or ru_url

    @property
    def resolved_cms_follower_urls(self) -> list[str]:
        raw = (self.cms_follower_urls or "").strip()
        if not raw:
            return []
        return [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]

    def xsolla_project_secret(self) -> str:
        """Secret used to verify webhook signatures (defaults to API key)."""
        return (self.xsolla_webhook_secret or self.xsolla_api_key or "").strip()


settings = Settings()

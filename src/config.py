from typing import Literal

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

    # Image generation: mock | reve | auto
    # auto — gpt_image_2 при наличии FAL_API_KEY, иначе Reve, иначе mock/ошибка.
    image_gen_provider: str = "auto"

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

    # Reve (https://api.reve.com — /v1/image/edit only)
    reve_api_token: str = ""
    reve_api_host: str = "https://api.reve.com"
    reve_version: str = "latest"
    # Максимум HTTP-вызовов Reve на одну generate()-операцию. На 429 ретрай
    # мы НЕ делаем: повторный запрос попадает в то же burst-окно Reve и
    # только усугубляет rate-limit, а пользователю всё равно отдаётся
    # "попробуйте ещё раз". Для 5xx/транспорта ретрай всё равно сработает
    # через внешний worker-retry. Значение 1 = ровно один HTTP-запрос на
    # generate().
    reve_max_retries: int = 1

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
    credit_packs_xtr: str = "5:25,10:45,20:85,50:200"

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

    # v1.17: VLM-based identity retry loop. When the first generation
    # comes back with identity_match < identity_match_threshold, we
    # re-run ``ImageGenProvider.generate()`` once with a fresh random
    # seed and keep whichever output has the higher identity_match score.
    # No biometric embeddings involved — the decision is driven purely
    # by the existing VLM quality gate. Budget impact: +$0.045 per
    # triggered retry (empirical ~15 % rate) ≈ +$0.007 / image average.
    identity_retry_enabled: bool = True
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
    # Image-gen strategy.
    #   - ``legacy``    — use ``image_gen_provider`` alone (v1.17 behaviour).
    #   - ``hybrid``    — StyleRouter → PuLID (identity_scene) / Seedream
    #                     (scene_preserve) / fallback (FLUX.2) per style.
    #   - ``pulid_only``— route every request through PuLID regardless of
    #                     style mode.
    # v1.19: ``hybrid`` is the default. The ``legacy`` canary branch is
    # kept only as a manual rollback escape hatch via env override.
    image_gen_strategy: str = "hybrid"

    # PuLID — identity-conditioned text-to-image (FLUX + ID adapter)
    # https://fal.ai/models/fal-ai/pulid
    #
    # v1.19.2 HOTFIX: fal-ai/pulid is strictly a Lightning model. The
    # API schema caps ``num_inference_steps`` at 12 and
    # ``guidance_scale`` at 1.5. v1.19.0 widened the defaults to
    # 25 steps / CFG 3.5 "for quality" which caused FAL to reject
    # every request with HTTP 422 (see smoke-test logs for v1.19.0 /
    # v1.19.1 runs). The quality preset that works within the
    # schema is ~8–12 steps at CFG 1.2–1.4 with id_scale 1.0. Cost
    # remains ~$0.015 per image.
    #
    # DO NOT raise ``pulid_steps`` above 12 or ``pulid_guidance_scale``
    # above 1.5 — the provider clamps them anyway and the tests in
    # ``tests/test_providers/test_fal_pulid.py`` + ``tests/test_config.py``
    # guard the defaults.
    pulid_enabled: bool = True
    pulid_model: str = "fal-ai/pulid"
    # 0 = no identity lock, 1.0+ = very strong. PuLID paper runs at
    # 1.0 for faithful portraits; the retry loop pushes to 1.2.
    pulid_id_scale: float = 1.0
    pulid_steps: int = 4
    pulid_guidance_scale: float = 1.2
    # ``fidelity`` (default) keeps face closer to reference. DO NOT
    # switch to ``extreme style`` on retry — that knob is for artistic
    # stylisation, not identity recovery. The retry path stays on
    # ``fidelity`` and instead raises id_scale / steps / guidance.
    pulid_mode: str = "fidelity"
    # NOTE: ``pulid_max_sequence_length`` was added in v1.19.0 under
    # the wrong assumption that fal-ai/pulid mirrors the FLUX.1
    # text-to-image schema. It does not — PuLID's schema rejects the
    # field with HTTP 422. Do NOT re-add; the constant is kept out of
    # the request body in v1.19.1+.
    #
    # Retry-escalation knobs (used only when the VLM gate flags
    # identity_match below the soft threshold). v1.19.2: previously
    # ``pulid_retry_steps=35`` / ``pulid_retry_guidance_scale=5.0`` —
    # both out of schema, so retries also 422-ed. Now capped at the
    # top of Lightning range.
    pulid_retry_id_scale: float = 1.2
    pulid_retry_steps: int = 8
    pulid_retry_guidance_scale: float = 1.4
    # Flat cost estimate. PuLID on FAL bills per GPU-second; empirical
    # mean at the 25-step quality config on H100 is ~$0.012–$0.018.
    model_cost_fal_pulid: float = 0.015

    # Seedream v4 Edit — image-to-image edit, 4 MP capable.
    # https://fal.ai/models/fal-ai/bytedance/seedream/v4/edit
    seedream_enabled: bool = True
    seedream_model: str = "fal-ai/bytedance/seedream/v4/edit"
    # ``standard`` (default) keeps the prompt close; ``fast`` rewrites
    # more aggressively but can drift on identity.
    seedream_enhance_prompt_mode: str = "standard"
    # Flat $0.03 per image up to 4 MP.
    model_cost_fal_seedream: float = 0.03

    # CodeFormer — post-generation face polish.
    # https://fal.ai/models/fal-ai/codeformer
    #
    # v1.19 policy: CodeFormer only runs for ``scene_preserve`` outputs
    # (Seedream edits) — PuLID already outputs sharp 25-step faces and
    # CodeFormer was **damaging** identity on those by rewriting
    # features at fidelity=0.5. For Seedream edits a high fidelity
    # (0.85) keeps the source face geometry while smoothing codec
    # artefacts. ``codeformer_upscale_factor=1.0`` avoids double-paying
    # for a resolution bump that Real-ESRGAN does later. Tiny faces
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
    # v1.19: disabled for identity_scene (PuLID). The 25-step quality
    # config outputs sharp faces by itself and CodeFormer @ fidelity
    # 0.85 was still nudging identity off on retries.
    codeformer_for_identity_scene: bool = False
    # Skip CodeFormer on retry attempts (we already polished attempt 1
    # and don't want to pay twice when the retry is about identity,
    # not sharpness).
    codeformer_on_retry: bool = False
    # Bills per megapixel (output). At 2 MP input with upscale_factor=1
    # we pay roughly $0.0021 × 2 MP = $0.0042.
    model_cost_fal_codeformer_per_mp: float = 0.0021

    # ------------------------------------------------------------------
    # v1.21 A/B test — additive path for Nano Banana 2 Edit and
    # GPT Image 2 Edit. When ``ab_test_enabled`` is True the /analyze
    # endpoint accepts ``image_model`` + ``image_quality`` form fields
    # and the executor routes such requests to the per-model provider
    # via a structured 8-block prompt adapter instead of StyleRouter.
    # v1.22: the A/B path is now the default for every web request.
    # Flip ``AB_TEST_ENABLED=false`` on Railway to return all traffic
    # to the legacy hybrid StyleRouter (PuLID / Seedream / FLUX.2) —
    # that code path stays in the repo as a rollback safety net.
    # ------------------------------------------------------------------
    ab_test_enabled: bool = True
    # Default A/B model when the client does not send ``image_model``
    # (old bot builds, edge proxy, curl, tests). GPT Image 2 at
    # ``quality=medium`` is the recommended starting tier to guarantee background details.
    ab_default_model: str = "gpt_image_2"
    # ------------------------------------------------------------------
    # style-schema-v2 migration — PR1..PR4.
    # Controls whether the StyleSpecV2 loader registers v2-tagged
    # entries from data/styles.json (otherwise they are ignored and
    # the v1 path handles everything). Default false so existing
    # deployments keep loading exactly what they load today.
    style_schema_v2_enabled: bool = True
    # When true AND the resolved StyleSpec is a StyleSpecV2, the
    # executor routes the prompt through
    # ``PromptEngine.build_image_prompt_v2`` → composition_builder →
    # per-model wrappers. Default false so the v2 prompt path is
    # opt-in per environment.
    unified_prompt_v2_enabled: bool = True
    # When true the v2 composition builder uses VariationEngineV2 with
    # separated weather / time_of_day / season / background channels
    # instead of the legacy VariationEngine (which conflates weather
    # with lighting). Has no effect when ``unified_prompt_v2_enabled``
    # is false.
    variation_engine_v2_enabled: bool = True
    # ------------------------------------------------------------------
    # style-schema-v3 — prompt-pipeline-overhaul (April 2026).
    # Controls whether the StyleSpecV3 loader registers v3-tagged
    # entries from data/styles.json and routes generation through the
    # SlotSampler (random pick per channel by default; user-overridable
    # via input_hints; immutable trigger pool ensures the headline
    # motif always reaches the prompt).
    # Default false because Stage 1 ships the schema additively;
    # data/styles.json doesn't yet contain ``schema_version: 3`` rows.
    # Stage 2 will flip the migration script's output to v3 and tests
    # will set the flag explicitly.
    style_schema_v3_enabled: bool = False
    # Default quality tier for the A/B models when the web client does
    # not pass an explicit one. Minimum for production is medium.
    ab_default_quality: str = "medium"
    # v1.23: identity-retry is intentionally DISABLED on the A/B path.
    # The legacy retry loop re-runs the provider with PuLID-specific
    # parameters (``pulid_mode``, ``id_scale``) that Nano Banana 2 and
    # GPT Image 2 simply ignore — so the second call only burns budget
    # and latency without actually improving the face. VLM quality
    # scoring is still computed and logged for analytics, but it no
    # longer triggers a re-generation. Legacy PuLID / StyleRouter path
    # continues to honour ``identity_retry_enabled`` independently.
    ab_identity_retry_enabled: bool = False

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

    # Segmentation / multi-pass pipeline.
    # Segmentation is DISABLED because Reve SDK 0.1.2 does not accept a
    # `mask_image` kwarg in edit() — passing one raises TypeError and ends
    # the generation as a generic failure. Until the SDK supports masking,
    # we fall back to a textual "change only the background" hint driven
    # by `mask_region` in executor.single_pass. Re-enable when SDK learns
    # mask_image.
    # Multi-pass is intentionally OFF so every task stays within one Reve call.
    segmentation_enabled: bool = False
    multi_pass_enabled: bool = False
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

    # Legacy prompt_strength (unused in edit mode)
    image_gen_strength: float = 0.45

    # Model cost estimates (USD per call)
    model_cost_reve: float = 0.02
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

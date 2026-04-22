from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str = ""
    telegram_bot_username: str = "RateMeAIBot"

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

    # Image generation: mock | reve | replicate | fal_flux | fal_flux2 | auto
    # Default: fal_flux2 (FLUX.2 [pro] edit через FAL.ai — identity-preserving
    # edit с поддержкой ``image_size`` до 4 МП, 2 МП портрет по умолчанию
    # для headshot / dating / social / CV). ``fal_flux`` (Kontext Pro, 1 МП)
    # остаётся на один релиз как rollback-target: переключается одной env
    # переменной ``IMAGE_GEN_PROVIDER=fal_flux`` без передеплоя провайдера.
    # auto — fal_flux2 при наличии FAL_API_KEY, иначе Reve, иначе mock/ошибка.
    image_gen_provider: str = "fal_flux2"

    # FAL.ai (https://fal.ai — FLUX.1 Kontext [pro] / image-to-image edit)
    # Получить токен: https://fal.ai → Dashboard → Keys (формат: uuid:secret).
    # В .env храним под именем FAL_API_KEY, но fal-client также читает FAL_KEY.
    fal_api_key: str = ""
    fal_model: str = "fal-ai/flux-pro/kontext"
    fal_api_host: str = "https://queue.fal.run"
    # Guidance scale для Kontext Pro (default 3.5, ниже = больше свободы).
    fal_guidance_scale: float = 3.5
    # Safety tolerance 1..5 (1 — строже всего). API требует строковый enum.
    fal_safety_tolerance: str = "2"
    # Output format у FAL: jpeg | png. Локально в pipeline всё равно нормализуем.
    fal_output_format: str = "jpeg"
    # Максимум HTTP-попыток на один generate(). 1 = без ретраев (единственный
    # запрос). Ретраим только небиллящиеся исходы (5xx / transport / queue stall).
    fal_max_retries: int = 2
    # Таймаут одной операции (POST submit + polling) в секундах.
    fal_request_timeout: float = 180.0
    # Интервал опроса статуса в очереди (секунды).
    fal_poll_interval: float = 1.5

    # FAL.ai FLUX.2 [pro] edit (https://fal.ai/models/fal-ai/flux-2-pro/edit).
    # Активный image-gen провайдер с v1.16 — поддерживает ``image_size``
    # (preset или ``{width, height}``), multi-reference, до 4 МП на выход.
    # Используется тот же FAL_API_KEY что и для Kontext Pro.
    fal2_model: str = "fal-ai/flux-2-pro/edit"
    # Целевой выход (для калькулятора стоимости; фактический размер
    # резолвится per-style через StyleSpec.output_aspect).
    fal2_output_mp: float = 2.0

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

    # Replicate (image generation)
    replicate_api_token: str = ""
    replicate_model_version: str = ""

    # YooKassa payments
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = "https://t.me/{bot_username}"

    # Credit packs: pack_size:price_rub (comma-separated)
    credit_packs: str = "1:59,5:199,15:499,30:899"

    # Admin (bootstrap API keys for B2B)
    admin_secret: str = ""
    api_key_pepper: str = ""

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
    #                     style mode (useful for A/B / canary experiments).
    # Default stays ``legacy`` until the canary rollout completes.
    image_gen_strategy: str = "legacy"

    # PuLID — identity-conditioned text-to-image (FLUX Lightning + ID adapter)
    # https://fal.ai/models/fal-ai/pulid
    pulid_enabled: bool = True
    pulid_model: str = "fal-ai/pulid"
    # 0 = no identity lock, 1.0 = very strong (face can dominate scene).
    # 0.8 is the sweet spot for photorealistic scenes; retry loop can
    # push it to 1.0 when identity_match fails.
    pulid_id_scale: float = 0.8
    # FLUX Lightning default — 4 steps at 1.2 guidance is the canonical
    # PuLID config. Retry loop can bump to 8 for sharper detail on
    # identity_match failures.
    pulid_steps: int = 4
    pulid_guidance_scale: float = 1.2
    # ``fidelity`` (default) keeps face closer to reference; ``extreme
    # style`` lets the prompt dominate more, useful on retry when the
    # identity lock made the scene look off.
    pulid_mode: str = "fidelity"
    # Flat cost estimate. PuLID on FAL bills per GPU-second; empirical
    # mean at the default 4-step config on H100 is ~$0.005–$0.008.
    model_cost_fal_pulid: float = 0.006

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
    codeformer_enabled: bool = True
    codeformer_model: str = "fal-ai/codeformer"
    # 0 = strongest restoration (most "perfect" features, risk of
    # identity drift), 1 = closest to the input. 0.5 is a safe default
    # that fixes Lightning-caused face blur without reshaping features.
    codeformer_fidelity: float = 0.5
    codeformer_upscale_factor: float = 2.0
    # Bills per megapixel. At 1 MP input + upscale_factor=2 we pay
    # roughly $0.0021 × 4 MP = $0.0084. Use a conservative $0.003 in
    # budget math.
    model_cost_fal_codeformer_per_mp: float = 0.0021

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

    # Legacy prompt_strength (unused in edit mode, kept for replicate fallback)
    image_gen_strength: float = 0.45

    # Model cost estimates (USD per call)
    model_cost_reve: float = 0.02
    model_cost_replicate: float = 0.05
    # FLUX.1 Kontext [pro] through FAL.ai: $0.04 per image (fixed, не зависит от MP).
    model_cost_fal_flux: float = 0.04
    # FLUX.2 [pro] edit: $0.03 за первый MP + $0.015 за каждый
    # дополнительный (округление вверх, до 4 МП). Калькулятор стоимости
    # использует ``fal2_output_mp`` для оценки: 2 МП ≈ $0.045/фото.
    model_cost_fal_flux2_first_mp: float = 0.03
    model_cost_fal_flux2_extra_mp: float = 0.015

    # Replicate inpainting model (FLUX-inpaint or similar)
    replicate_inpaint_model_version: str = ""

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

    # App
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = ""
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


settings = Settings()

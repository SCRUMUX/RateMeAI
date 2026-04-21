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

    # Image generation (CV / emoji): mock | reve | replicate | auto
    # Default: reve (Replicate временно отключён до ручного переключения обратно на auto).
    image_gen_provider: str = "reve"

    # Reve (https://api.reve.com — official SDK)
    reve_api_token: str = ""
    reve_api_host: str = "https://api.reve.com"
    reve_aspect_ratio: str = "1:1"
    reve_version: str = "latest"
    reve_test_time_scaling: int = 4
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

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
    image_gen_provider: str = "auto"

    # Reve (https://api.reve.com — official SDK)
    reve_api_token: str = ""
    reve_api_host: str = "https://api.reve.com"
    reve_aspect_ratio: str = "1:1"
    reve_version: str = "latest"
    reve_test_time_scaling: int = 5

    # Replicate (image generation)
    replicate_api_token: str = ""
    replicate_model_version: str = ""

    # YooKassa payments
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = "https://t.me/{bot_username}"

    # Credit packs: pack_size:price_rub (comma-separated)
    credit_packs: str = "5:200,25:500,70:1000"

    # Admin (bootstrap API keys for B2B)
    admin_secret: str = ""
    api_key_pepper: str = ""

    # Rate Limits
    rate_limit_daily: int = 3
    # Telegram @username без лимита (через запятую, без @): RATE_LIMIT_EXEMPT_USERNAMES=scrumux
    rate_limit_exempt_usernames: str = ""

    # Одна строка из CI (Railway / GitHub): git rev-parse --short HEAD — для проверки, что на сервере нужный commit
    deploy_git_sha: str = ""

    # App
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_base_url: str = "http://localhost:8000"
    bot_webhook_url: str = ""
    bot_webhook_secret: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"


settings = Settings()

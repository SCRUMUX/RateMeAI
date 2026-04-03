from __future__ import annotations

from functools import lru_cache

from src.config import settings
from src.providers.base import LLMProvider, StorageProvider, ImageGenProvider


@lru_cache(maxsize=1)
def get_storage() -> StorageProvider:
    if settings.storage_provider == "s3":
        from src.providers.storage.s3 import S3StorageProvider
        pub = settings.s3_public_base_url.strip() or None
        return S3StorageProvider(
            endpoint_url=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            public_base_url=pub,
            presign_ttl_seconds=settings.s3_presign_ttl_seconds,
        )
    from src.providers.storage.local import LocalStorageProvider
    base = settings.api_base_url.rstrip("/")
    fb = settings.storage_http_fallback_base.strip() or None
    return LocalStorageProvider(
        settings.storage_local_path,
        base,
        http_fallback_base=fb,
    )


def _image_gen_provider_mode() -> str:
    p = (settings.image_gen_provider or "auto").strip().lower()
    if p in ("auto", "reve", "replicate", "mock"):
        return p
    return "auto"


def _missing_replicate_config() -> bool:
    return not (
        settings.replicate_api_token and settings.replicate_model_version
    )


@lru_cache(maxsize=1)
def get_image_gen() -> ImageGenProvider:
    from src.providers.image_gen.mock import MockImageGen
    from src.providers.image_gen.replicate import ReplicateImageGen
    from src.providers.image_gen.reve_provider import ReveImageGen

    mode = _image_gen_provider_mode()
    prod = settings.is_production

    if mode == "mock":
        return MockImageGen()

    if mode == "reve":
        if not settings.reve_api_token.strip():
            if prod:
                raise RuntimeError(
                    "IMAGE_GEN_PROVIDER=reve requires REVE_API_TOKEN",
                )
            return MockImageGen()
        return ReveImageGen(
            api_token=settings.reve_api_token,
            api_host=settings.reve_api_host,
            aspect_ratio=settings.reve_aspect_ratio,
            version=settings.reve_version,
            test_time_scaling=settings.reve_test_time_scaling,
        )

    if mode == "replicate":
        if _missing_replicate_config():
            if prod:
                raise RuntimeError(
                    "IMAGE_GEN_PROVIDER=replicate requires "
                    "REPLICATE_API_TOKEN and REPLICATE_MODEL_VERSION",
                )
            return MockImageGen()
        return ReplicateImageGen(
            api_token=settings.replicate_api_token,
            model_version=settings.replicate_model_version,
            storage=get_storage(),
        )

    # auto
    if settings.reve_api_token.strip():
        return ReveImageGen(
            api_token=settings.reve_api_token,
            api_host=settings.reve_api_host,
            aspect_ratio=settings.reve_aspect_ratio,
            version=settings.reve_version,
            test_time_scaling=settings.reve_test_time_scaling,
        )
    if not _missing_replicate_config():
        return ReplicateImageGen(
            api_token=settings.replicate_api_token,
            model_version=settings.replicate_model_version,
            storage=get_storage(),
        )
    return MockImageGen()


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    from src.providers.llm.openrouter import OpenRouterLLM
    return OpenRouterLLM(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=settings.openrouter_model,
    )

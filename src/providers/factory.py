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
    if p in ("auto", "reve", "replicate", "mock", "fal_flux", "fal_flux2"):
        return p
    return "auto"


def _missing_replicate_config() -> bool:
    return not (
        settings.replicate_api_token and settings.replicate_model_version
    )


def _build_fal_flux():
    """Construct :class:`FalFluxImageGen` from settings.

    Legacy Kontext Pro provider — kept on as a one-release rollback
    target via ``IMAGE_GEN_PROVIDER=fal_flux``. New traffic goes to
    ``fal_flux2`` (FLUX.2 Pro Edit) by default; see ``_build_fal_flux2``.
    """
    from src.providers.image_gen.fal_flux import FalFluxImageGen

    return FalFluxImageGen(
        api_key=settings.fal_api_key,
        model=settings.fal_model,
        api_host=settings.fal_api_host,
        guidance_scale=settings.fal_guidance_scale,
        safety_tolerance=settings.fal_safety_tolerance,
        output_format=settings.fal_output_format,
        max_retries=settings.fal_max_retries,
        request_timeout=settings.fal_request_timeout,
        poll_interval=settings.fal_poll_interval,
    )


def _build_fal_flux2():
    """Construct :class:`FalFlux2ImageGen` (FLUX.2 Pro Edit) from settings.

    This is the default provider as of v1.16. Shares the FAL auth key
    with the legacy Kontext provider (same FAL account), but targets a
    different model and accepts ``image_size`` for 2 MP output.
    """
    from src.providers.image_gen.fal_flux2 import FalFlux2ImageGen

    return FalFlux2ImageGen(
        api_key=settings.fal_api_key,
        model=settings.fal2_model,
        api_host=settings.fal_api_host,
        safety_tolerance=settings.fal_safety_tolerance,
        output_format=settings.fal_output_format,
        max_retries=settings.fal_max_retries,
        request_timeout=settings.fal_request_timeout,
        poll_interval=settings.fal_poll_interval,
    )


@lru_cache(maxsize=1)
def get_image_gen() -> ImageGenProvider:
    from src.providers._testing import MockImageGen
    from src.providers.image_gen.replicate import ReplicateImageGen
    from src.providers.image_gen.reve_provider import ReveImageGen

    mode = _image_gen_provider_mode()
    prod = settings.is_production

    if mode == "mock":
        return MockImageGen()

    if mode == "fal_flux2":
        if not (settings.fal_api_key or "").strip():
            if prod:
                raise RuntimeError(
                    "IMAGE_GEN_PROVIDER=fal_flux2 requires FAL_API_KEY",
                )
            return MockImageGen()
        return _build_fal_flux2()

    if mode == "fal_flux":
        if not (settings.fal_api_key or "").strip():
            if prod:
                raise RuntimeError(
                    "IMAGE_GEN_PROVIDER=fal_flux requires FAL_API_KEY",
                )
            return MockImageGen()
        return _build_fal_flux()

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
            version=settings.reve_version,
            max_retries=settings.reve_max_retries,
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

    # auto — FLUX.2 Pro Edit через FAL предпочитаем для сценариев с
    # лицами (2 МП выход, native image_size support), Kontext Pro и
    # Reve остаются как резерв. Порядок выбора:
    # fal_flux2 → fal_flux → Reve → Mock (dev) / RuntimeError (prod).
    # Replicate в auto-режиме не подключается по умолчанию —
    # см. docs/architecture/reserved.md.
    if (settings.fal_api_key or "").strip():
        return _build_fal_flux2()
    if settings.reve_api_token.strip():
        return ReveImageGen(
            api_token=settings.reve_api_token,
            api_host=settings.reve_api_host,
            version=settings.reve_version,
            max_retries=settings.reve_max_retries,
        )
    if prod:
        raise RuntimeError(
            "IMAGE_GEN_PROVIDER=auto requires FAL_API_KEY (flux-2-pro/edit "
            "or kontext) or REVE_API_TOKEN (Replicate is reserved and not "
            "auto-selected)",
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

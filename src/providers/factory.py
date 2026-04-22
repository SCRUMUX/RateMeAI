from __future__ import annotations

import logging
from functools import lru_cache

from src.config import settings
from src.providers.base import LLMProvider, StorageProvider, ImageGenProvider

logger = logging.getLogger(__name__)


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


def _build_fal_pulid():
    """Construct :class:`FalPuLIDImageGen` from settings (v1.18 hybrid)."""
    from src.providers.image_gen.fal_pulid import FalPuLIDImageGen

    return FalPuLIDImageGen(
        api_key=settings.fal_api_key,
        model=settings.pulid_model,
        api_host=settings.fal_api_host,
        id_scale=settings.pulid_id_scale,
        pulid_mode=settings.pulid_mode,
        num_inference_steps=settings.pulid_steps,
        guidance_scale=settings.pulid_guidance_scale,
        max_sequence_length=getattr(
            settings, "pulid_max_sequence_length", 512,
        ),
        max_retries=settings.fal_max_retries,
        request_timeout=settings.fal_request_timeout,
        poll_interval=settings.fal_poll_interval,
    )


def _build_fal_seedream():
    """Construct :class:`FalSeedreamImageGen` from settings (v1.18 hybrid)."""
    from src.providers.image_gen.fal_seedream import FalSeedreamImageGen

    return FalSeedreamImageGen(
        api_key=settings.fal_api_key,
        model=settings.seedream_model,
        api_host=settings.fal_api_host,
        enhance_prompt_mode=settings.seedream_enhance_prompt_mode,
        max_retries=settings.fal_max_retries,
        request_timeout=settings.fal_request_timeout,
        poll_interval=settings.fal_poll_interval,
    )


def _build_style_router():
    """Assemble :class:`StyleRouter` for hybrid / pulid_only strategies.

    PuLID handles identity_scene requests; Seedream handles
    scene_preserve. The fallback is FLUX.2 Pro Edit — kept as the "safe
    choice" when generation_mode is missing, the face crop fails, or a
    feature flag is off.
    """
    from src.providers.image_gen.style_router import StyleRouter

    strategy = (settings.image_gen_strategy or "legacy").strip().lower()
    pulid = None
    if settings.pulid_enabled:
        try:
            pulid = _build_fal_pulid()
        except Exception as exc:
            logger.warning("StyleRouter: PuLID init failed (%s)", exc)
    seedream = None
    if settings.seedream_enabled:
        try:
            seedream = _build_fal_seedream()
        except Exception as exc:
            logger.warning("StyleRouter: Seedream init failed (%s)", exc)

    fallback = _build_fal_flux2()

    # ``pulid_only``: wire Seedream to the same PuLID provider so every
    # request lands on PuLID regardless of style mode. The face-crop
    # fallback still routes through the real seedream / fallback path.
    if strategy == "pulid_only" and pulid is not None:
        router = StyleRouter(
            pulid=pulid,
            seedream=pulid,
            fallback=fallback,
        )
    else:
        router = StyleRouter(
            pulid=pulid,
            seedream=seedream,
            fallback=fallback,
        )
    return router


def _log_image_gen_choice(provider: ImageGenProvider, *, reason: str) -> None:
    """Emit a single, high-signal line identifying the chosen provider.

    Shows up exactly once per process (``get_image_gen`` is ``lru_cache``-d)
    near the top of the Railway deployment log, so `/health` correlations
    and "why is it still Kontext?" debugging are a single grep away.
    """
    cls = type(provider).__name__
    model = (
        getattr(provider, "_model", None)
        or getattr(provider, "model", None)
        or "—"
    )
    strategy = (
        getattr(settings, "image_gen_strategy", "legacy") or "legacy"
    )
    router_summary = ""
    if hasattr(provider, "backend_summary"):
        try:
            summary = provider.backend_summary()  # type: ignore[attr-defined]
            router_summary = (
                f" backends={summary}"
            )
        except Exception:
            router_summary = ""
    logger.info(
        "image-gen strategy=%s provider selected: class=%s model=%s "
        "reason=%s%s (IMAGE_GEN_PROVIDER=%s, gfpgan=%s, esrgan=%s, "
        "identity_retry=%s, codeformer=%s)",
        strategy, cls, model, reason, router_summary,
        (settings.image_gen_provider or "auto"),
        bool(getattr(settings, "gfpgan_preclean_enabled", False)),
        bool(getattr(settings, "real_esrgan_enabled", False)),
        bool(getattr(settings, "identity_retry_enabled", False)),
        bool(getattr(settings, "codeformer_enabled", False)),
    )


def _image_gen_strategy() -> str:
    s = (
        getattr(settings, "image_gen_strategy", "legacy") or "legacy"
    ).strip().lower()
    if s in ("legacy", "hybrid", "pulid_only"):
        return s
    return "legacy"


@lru_cache(maxsize=1)
def get_image_gen() -> ImageGenProvider:
    from src.providers._testing import MockImageGen
    from src.providers.image_gen.replicate import ReplicateImageGen
    from src.providers.image_gen.reve_provider import ReveImageGen

    strategy = _image_gen_strategy()
    prod = settings.is_production

    # Hybrid / pulid_only: assemble StyleRouter (PuLID + Seedream +
    # FLUX.2 fallback). Any init failure in the sub-providers degrades
    # gracefully — StyleRouter already handles a missing PuLID/Seedream.
    if strategy in ("hybrid", "pulid_only"):
        if not (settings.fal_api_key or "").strip():
            if prod:
                raise RuntimeError(
                    f"IMAGE_GEN_STRATEGY={strategy} requires FAL_API_KEY "
                    "(PuLID + Seedream + FLUX.2 all live on FAL)",
                )
            p = MockImageGen()
            _log_image_gen_choice(
                p, reason=f"strategy={strategy} but no FAL_API_KEY (dev)",
            )
            return p
        try:
            p = _build_style_router()
        except Exception as exc:
            logger.exception(
                "StyleRouter assembly failed, falling back to FLUX.2: %s",
                exc,
            )
            p = _build_fal_flux2()
            _log_image_gen_choice(
                p, reason=f"strategy={strategy} → router failed, FLUX.2",
            )
            return p
        _log_image_gen_choice(p, reason=f"strategy={strategy}")
        return p

    # Legacy strategy: honour IMAGE_GEN_PROVIDER as before.
    mode = _image_gen_provider_mode()

    if mode == "mock":
        p = MockImageGen()
        _log_image_gen_choice(p, reason="mode=mock")
        return p

    if mode == "fal_flux2":
        if not (settings.fal_api_key or "").strip():
            if prod:
                raise RuntimeError(
                    "IMAGE_GEN_PROVIDER=fal_flux2 requires FAL_API_KEY",
                )
            p = MockImageGen()
            _log_image_gen_choice(p, reason="mode=fal_flux2 but no FAL_API_KEY (dev)")
            return p
        p = _build_fal_flux2()
        _log_image_gen_choice(p, reason="mode=fal_flux2")
        return p

    if mode == "fal_flux":
        if not (settings.fal_api_key or "").strip():
            if prod:
                raise RuntimeError(
                    "IMAGE_GEN_PROVIDER=fal_flux requires FAL_API_KEY",
                )
            p = MockImageGen()
            _log_image_gen_choice(p, reason="mode=fal_flux but no FAL_API_KEY (dev)")
            return p
        p = _build_fal_flux()
        _log_image_gen_choice(p, reason="mode=fal_flux (legacy Kontext rollback)")
        return p

    if mode == "reve":
        if not settings.reve_api_token.strip():
            if prod:
                raise RuntimeError(
                    "IMAGE_GEN_PROVIDER=reve requires REVE_API_TOKEN",
                )
            p = MockImageGen()
            _log_image_gen_choice(p, reason="mode=reve but no REVE_API_TOKEN (dev)")
            return p
        p = ReveImageGen(
            api_token=settings.reve_api_token,
            api_host=settings.reve_api_host,
            version=settings.reve_version,
            max_retries=settings.reve_max_retries,
        )
        _log_image_gen_choice(p, reason="mode=reve")
        return p

    if mode == "replicate":
        if _missing_replicate_config():
            if prod:
                raise RuntimeError(
                    "IMAGE_GEN_PROVIDER=replicate requires "
                    "REPLICATE_API_TOKEN and REPLICATE_MODEL_VERSION",
                )
            p = MockImageGen()
            _log_image_gen_choice(p, reason="mode=replicate but missing config (dev)")
            return p
        p = ReplicateImageGen(
            api_token=settings.replicate_api_token,
            model_version=settings.replicate_model_version,
            storage=get_storage(),
        )
        _log_image_gen_choice(p, reason="mode=replicate")
        return p

    # auto — FLUX.2 Pro Edit через FAL предпочитаем для сценариев с
    # лицами (2 МП выход, native image_size support), Kontext Pro и
    # Reve остаются как резерв. Порядок выбора:
    # fal_flux2 → fal_flux → Reve → Mock (dev) / RuntimeError (prod).
    # Replicate в auto-режиме не подключается по умолчанию —
    # см. docs/architecture/reserved.md.
    if (settings.fal_api_key or "").strip():
        p = _build_fal_flux2()
        _log_image_gen_choice(p, reason="auto → FAL_API_KEY present")
        return p
    if settings.reve_api_token.strip():
        p = ReveImageGen(
            api_token=settings.reve_api_token,
            api_host=settings.reve_api_host,
            version=settings.reve_version,
            max_retries=settings.reve_max_retries,
        )
        _log_image_gen_choice(p, reason="auto → REVE_API_TOKEN only")
        return p
    if prod:
        raise RuntimeError(
            "IMAGE_GEN_PROVIDER=auto requires FAL_API_KEY (flux-2-pro/edit "
            "or kontext) or REVE_API_TOKEN (Replicate is reserved and not "
            "auto-selected)",
        )
    p = MockImageGen()
    _log_image_gen_choice(p, reason="auto → no keys (dev)")
    return p


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    from src.providers.llm.openrouter import OpenRouterLLM
    return OpenRouterLLM(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=settings.openrouter_model,
    )


@lru_cache(maxsize=1)
def get_codeformer():
    """Return a CodeFormer post-processor or ``None`` when disabled.

    v1.18+ — the executor runs CodeFormer after the main generator to
    polish Lightning-soft faces. Any missing FAL_API_KEY or disabled
    feature flag returns ``None`` and the executor skips the stage.
    """
    if not bool(getattr(settings, "codeformer_enabled", False)):
        return None
    if not (settings.fal_api_key or "").strip():
        return None
    from src.providers.image_gen.fal_codeformer import FalCodeFormerRestorer

    try:
        return FalCodeFormerRestorer(
            api_key=settings.fal_api_key,
            model=settings.codeformer_model,
            api_host=settings.fal_api_host,
            fidelity=settings.codeformer_fidelity,
            upscale_factor=settings.codeformer_upscale_factor,
            max_retries=settings.fal_max_retries,
            request_timeout=settings.fal_request_timeout,
            poll_interval=settings.fal_poll_interval,
        )
    except Exception as exc:
        logger.warning("CodeFormer init failed: %s", exc)
        return None

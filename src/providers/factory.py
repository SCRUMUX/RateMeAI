from __future__ import annotations

import logging
from functools import lru_cache

from src.config import settings
from src.providers.base import ImageGenProvider, LLMProvider, StorageProvider

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


# ---------------------------------------------------------------------------
# v1.21 A/B test providers. Selected per-request via the
# ``image_model`` form field on ``/api/v1/analyze``, routed from the
# executor. Both models are FAL-hosted edit-mode providers; the
# UnifiedImageGenProvider dispatches between them based on the
# requested ``image_model``. v1.64 collapsed the legacy StyleRouter
# (PuLID + Seedream + FLUX.2 fallback) into this two-model pair — the
# generation_mode-based routing was effectively bypassed in production
# because ``ab_test_enabled=True`` always set the requested model
# upstream.
# ---------------------------------------------------------------------------


def _build_nano_banana_2():
    """Construct :class:`FalNanoBanana2Edit` from settings (v1.21 A/B)."""
    from src.providers.image_gen.fal_nano_banana import FalNanoBanana2Edit

    return FalNanoBanana2Edit(
        api_key=settings.fal_api_key,
        model=settings.nano_banana_model,
        api_host=settings.fal_api_host,
        output_format=settings.fal_output_format,
        default_quality=settings.ab_default_quality,
        max_retries=settings.fal_max_retries,
        request_timeout=settings.fal_request_timeout,
        poll_interval=settings.fal_poll_interval,
    )


def _build_gpt_image_2():
    """Construct :class:`FalGptImage2Edit` from settings (v1.21 A/B)."""
    from src.providers.image_gen.fal_gpt_image_2 import FalGptImage2Edit

    return FalGptImage2Edit(
        api_key=settings.fal_api_key,
        model=settings.gpt_image_2_model,
        api_host=settings.fal_api_host,
        output_format=settings.fal_output_format,
        default_quality=settings.ab_default_quality,
        max_retries=settings.fal_max_retries,
        # GPT Image 2 runs through OpenAI's backend — a bit slower p95
        # than FLUX/Seedream, so we give it a longer timeout ceiling.
        request_timeout=max(settings.fal_request_timeout, 240.0),
        poll_interval=settings.fal_poll_interval,
    )


AB_IMAGE_MODELS: frozenset[str] = frozenset({"nano_banana_2", "gpt_image_2"})

# Historical ``get_ab_image_gen`` helper was retired in v1.70.15 —
# every call site now reads the single :func:`get_image_gen`
# (``UnifiedImageGenProvider``) and steers the underlying model via
# the ``image_model`` request param. ``AB_IMAGE_MODELS`` survives as
# the whitelist used by the analysis-request validator.


def _build_unified_provider():
    """Assemble :class:`UnifiedImageGenProvider` (v1.64 FAL-only).

    Model A: GPT Image 2 Edit (default)
    Model B: Nano Banana 2 Edit (A/B alternative)

    v1.64 removed the optional PuLID / Seedream legs because the
    ``ab_test_enabled=True`` request path always supplied an explicit
    ``image_model`` upstream, meaning ``UnifiedImageGenProvider``
    never reached the ``generation_mode``-based fork in production.
    """
    from src.providers._testing import MockImageGen
    from src.providers.image_gen.unified import UnifiedImageGenProvider

    try:
        model_a = _build_gpt_image_2()
    except Exception as exc:
        logger.warning(
            "UnifiedProvider: Model A (GPT-2) init failed (%s), using Mock",
            exc,
        )
        model_a = MockImageGen()

    try:
        model_b = _build_nano_banana_2()
    except Exception as exc:
        logger.warning(
            "UnifiedProvider: Model B (Nano Banana) init failed (%s), using Mock",
            exc,
        )
        model_b = MockImageGen()

    return UnifiedImageGenProvider(model_a=model_a, model_b=model_b)


def _log_image_gen_choice(provider: ImageGenProvider, *, reason: str) -> None:
    """Emit a single, high-signal line identifying the chosen provider.

    Shows up exactly once per process (``get_image_gen`` is
    ``lru_cache``-d) near the top of the Railway deployment log, so
    `/health` correlations and "why is it still Kontext?" debugging
    are a single grep away.
    """
    cls = type(provider).__name__
    model = getattr(provider, "_model", None) or getattr(provider, "model", None) or "—"
    router_summary = ""
    if hasattr(provider, "backend_summary"):
        try:
            summary = provider.backend_summary()  # type: ignore[attr-defined]
            router_summary = f" backends={summary}"
        except Exception:
            router_summary = ""
    logger.info(
        "image-gen provider selected: class=%s model=%s reason=%s%s "
        "(gfpgan=%s, esrgan=%s, identity_retry=%s, codeformer=%s)",
        cls,
        model,
        reason,
        router_summary,
        bool(getattr(settings, "gfpgan_preclean_enabled", False)),
        bool(getattr(settings, "real_esrgan_enabled", False)),
        bool(getattr(settings, "identity_retry_enabled", False)),
        bool(getattr(settings, "codeformer_enabled", False)),
    )


@lru_cache(maxsize=1)
def get_image_gen() -> ImageGenProvider:
    """Return the production image-generation provider.

    v1.70.13 — single FAL-only path. ``IMAGE_GEN_PROVIDER`` is now a
    two-value enum ``{mock, unified}`` (with ``auto`` and any legacy
    value treated as a synonym of ``unified`` for backward
    compatibility with older ``.env`` files). Reve, Replicate,
    PuLID and Seedream legs were retired between v1.20 and v1.64;
    see ``docs/ARCHITECTURE.md``.
    """
    from src.providers._testing import MockImageGen

    mode = (settings.image_gen_provider or "unified").strip().lower()
    prod = settings.is_production

    if mode == "mock":
        p = MockImageGen()
        _log_image_gen_choice(p, reason="mode=mock")
        return p

    if (settings.fal_api_key or "").strip():
        p = _build_unified_provider()
        _log_image_gen_choice(p, reason=f"mode={mode} → FAL_API_KEY present")
        return p

    if prod:
        raise RuntimeError(
            "IMAGE_GEN_PROVIDER=unified requires FAL_API_KEY — the Reve "
            "and Replicate fallbacks were retired in v1.20, and the "
            "PuLID / Seedream legs were retired in v1.64.",
        )

    p = MockImageGen()
    _log_image_gen_choice(p, reason=f"mode={mode} → no FAL_API_KEY (dev)")
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

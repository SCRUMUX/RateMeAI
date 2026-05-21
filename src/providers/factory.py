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
# Single FAL-hosted edit-mode provider — GPT Image 2 Edit. The historic
# A/B layer (Nano Banana 2 + UnifiedImageGenProvider) was retired in
# the "Remove Nano Banana, Premium Upscale" cleanup: every UI tier
# (Standard / Premium) ships through the same GPT Image 2 base render,
# and the Premium tier adds a Clarity Upscaler post-pass downstream
# in :mod:`src.orchestrator.executor`. Cross-model fallback no longer
# exists; the in-pipeline ``identity_retry`` with a fresh seed on the
# same model covers transient FAL failures.
# ---------------------------------------------------------------------------


def _build_gpt_image_2():
    """Construct :class:`FalGptImage2Edit` from settings."""
    from src.providers.image_gen.fal_gpt_image_2 import FalGptImage2Edit

    return FalGptImage2Edit(
        api_key=settings.fal_api_key,
        model=settings.gpt_image_2_model,
        api_host=settings.fal_api_host,
        output_format=settings.fal_output_format,
        default_quality=settings.ab_default_quality,
        max_retries=settings.fal_max_retries,
        # GPT Image 2 runs through OpenAI's backend, so we give it a
        # longer timeout ceiling than the FAL queue baseline.
        request_timeout=max(settings.fal_request_timeout, 240.0),
        poll_interval=settings.fal_poll_interval,
    )


def _log_image_gen_choice(provider: ImageGenProvider, *, reason: str) -> None:
    """Emit a single, high-signal line identifying the chosen provider.

    Shows up exactly once per process (``get_image_gen`` is
    ``lru_cache``-d) near the top of the Railway deployment log, so
    `/health` correlations and "which provider is wired in?" debugging
    are a single grep away.
    """
    cls = type(provider).__name__
    model = getattr(provider, "_model", None) or getattr(provider, "model", None) or "—"
    logger.info(
        "image-gen provider selected: class=%s model=%s reason=%s "
        "(gfpgan=%s, esrgan=%s, identity_retry=%s, codeformer=%s)",
        cls,
        model,
        reason,
        bool(getattr(settings, "gfpgan_preclean_enabled", False)),
        bool(getattr(settings, "real_esrgan_enabled", False)),
        bool(getattr(settings, "identity_retry_enabled", False)),
        bool(getattr(settings, "codeformer_enabled", False)),
    )


@lru_cache(maxsize=1)
def get_image_gen() -> ImageGenProvider:
    """Return the production image-generation provider.

    Single FAL-only path: GPT Image 2 Edit. ``IMAGE_GEN_PROVIDER`` is
    a two-value enum ``{mock, unified}`` (any other / legacy value is
    treated as ``unified`` for backward compatibility with older
    ``.env`` files — it now means "the single GPT Image 2 provider").
    Reve / Replicate / PuLID / Seedream / Nano Banana 2 legs were
    retired between v1.20 and the Nano-Banana cleanup; see
    ``docs/ARCHITECTURE.md``.
    """
    from src.providers._testing import MockImageGen

    mode = (settings.image_gen_provider or "unified").strip().lower()
    prod = settings.is_production

    if mode == "mock":
        p = MockImageGen()
        _log_image_gen_choice(p, reason="mode=mock")
        return p

    if (settings.fal_api_key or "").strip():
        try:
            p = _build_gpt_image_2()
        except Exception as exc:
            logger.warning(
                "get_image_gen: GPT Image 2 init failed (%s), using Mock",
                exc,
            )
            p = MockImageGen()
        _log_image_gen_choice(p, reason=f"mode={mode} → FAL_API_KEY present")
        return p

    if prod:
        raise RuntimeError(
            "IMAGE_GEN_PROVIDER=unified requires FAL_API_KEY — the Reve "
            "and Replicate fallbacks were retired in v1.20, the "
            "PuLID / Seedream legs in v1.64, and Nano Banana 2 in the "
            "Nano-Banana cleanup.",
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

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
    # v1.20: "reve" and "replicate" values are accepted and silently
    # remapped to "auto" below to preserve one-release compatibility
    # with stale Railway env files. The fabricate-Reve / Replicate
    # code path is gone — see v1.20 release notes.
    if p in ("reve", "replicate"):
        logger.warning(
            "IMAGE_GEN_PROVIDER=%s is no longer supported; "
            "falling back to auto (FAL-only pipeline).",
            p,
        )
        return "auto"
    if p in ("auto", "mock"):
        return p
    return "auto"


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


# ---------------------------------------------------------------------------
# v1.21 A/B test providers — additive. Selected per-request via the
# ``image_model`` form field on /api/v1/analyze, routed from the executor.
# The default hybrid StyleRouter pipeline is untouched when the A/B path
# is not requested. Disabled wholesale via ``settings.ab_test_enabled``.
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


@lru_cache(maxsize=8)
def get_ab_image_gen(model_key: str) -> ImageGenProvider:
    """Return an A/B image-gen provider for the given model key.

    Cached per key so each Railway process holds at most one client per
    model. Raises :class:`RuntimeError` if the key is unknown or FAL
    credentials are missing — the executor catches this and degrades
    back to the default StyleRouter path.
    """
    key = (model_key or "").strip().lower()
    if key not in AB_IMAGE_MODELS:
        raise RuntimeError(
            f"unknown AB image_model={key!r}; allowed={sorted(AB_IMAGE_MODELS)}",
        )
    if not (settings.fal_api_key or "").strip():
        raise RuntimeError(
            f"AB image_model={key} requires FAL_API_KEY",
        )
    if key == "nano_banana_2":
        return _build_nano_banana_2()
    if key == "gpt_image_2":
        return _build_gpt_image_2()
    # Unreachable — guarded by the whitelist above.
    raise RuntimeError(f"unreachable AB provider branch: {key}")


def _build_unified_provider():
    """Assemble :class:`UnifiedImageGenProvider` for the new pipeline.

    Model A: GPT-2
    Model B: Nano Banana
    """
    from src.providers.image_gen.unified import UnifiedImageGenProvider

    model_a = _build_gpt_image_2()
    model_b = _build_nano_banana_2()

    pulid = None
    if settings.pulid_enabled:
        try:
            pulid = _build_fal_pulid()
        except Exception as exc:
            logger.warning("UnifiedProvider: PuLID init failed (%s)", exc)

    seedream = None
    if settings.seedream_enabled:
        try:
            seedream = _build_fal_seedream()
        except Exception as exc:
            logger.warning("UnifiedProvider: Seedream init failed (%s)", exc)

    return UnifiedImageGenProvider(
        model_a=model_a,
        model_b=model_b,
        pulid=pulid,
        seedream=seedream,
    )


def _log_image_gen_choice(provider: ImageGenProvider, *, reason: str) -> None:
    """Emit a single, high-signal line identifying the chosen provider.

    Shows up exactly once per process (``get_image_gen`` is ``lru_cache``-d)
    near the top of the Railway deployment log, so `/health` correlations
    and "why is it still Kontext?" debugging are a single grep away.
    """
    cls = type(provider).__name__
    model = getattr(provider, "_model", None) or getattr(provider, "model", None) or "—"
    strategy = getattr(settings, "image_gen_strategy", "legacy") or "legacy"
    router_summary = ""
    if hasattr(provider, "backend_summary"):
        try:
            summary = provider.backend_summary()  # type: ignore[attr-defined]
            router_summary = f" backends={summary}"
        except Exception:
            router_summary = ""
    logger.info(
        "image-gen strategy=%s provider selected: class=%s model=%s "
        "reason=%s%s (IMAGE_GEN_PROVIDER=%s, gfpgan=%s, esrgan=%s, "
        "identity_retry=%s, codeformer=%s)",
        strategy,
        cls,
        model,
        reason,
        router_summary,
        (settings.image_gen_provider or "auto"),
        bool(getattr(settings, "gfpgan_preclean_enabled", False)),
        bool(getattr(settings, "real_esrgan_enabled", False)),
        bool(getattr(settings, "identity_retry_enabled", False)),
        bool(getattr(settings, "codeformer_enabled", False)),
    )


def _image_gen_strategy() -> str:
    s = (getattr(settings, "image_gen_strategy", "legacy") or "legacy").strip().lower()
    if s in ("legacy", "hybrid", "pulid_only"):
        return s
    return "legacy"


@lru_cache(maxsize=1)
def get_image_gen() -> ImageGenProvider:
    # v1.20: Reve and Replicate providers are no longer wired into the
    # factory. The modules remain in ``src/providers/image_gen/`` for
    # historical tests and manual rollback scripts, but the public
    # factory path is FAL-only (hybrid StyleRouter + legacy fal_flux2 /
    # fal_flux direct modes). See ``docs/architecture/reserved.md``.
    from src.providers._testing import MockImageGen

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
                p,
                reason=f"strategy={strategy} but no FAL_API_KEY (dev)",
            )
            return p
        try:
            p = _build_unified_provider()
        except Exception as exc:
            logger.exception(
                "StyleRouter assembly failed: %s",
                exc,
            )
            if prod:
                raise RuntimeError(f"StyleRouter failed to initialize in production: {exc}") from exc
            p = MockImageGen()
            _log_image_gen_choice(
                p,
                reason=f"strategy={strategy} → router failed, falling back to mock",
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

    # v1.20: auto — FAL-only. Unified provider is the default because
    # it matches the StyleRouter fallback and accepts the same 2 MP
    # ``image_size`` knob the rest of the pipeline uses. Reve /
    # Replicate fallbacks are retired — see module-level comment and
    # ``docs/architecture/reserved.md``.
    if (settings.fal_api_key or "").strip():
        p = _build_unified_provider()
        _log_image_gen_choice(p, reason="auto → FAL_API_KEY present")
        return p
    if prod:
        raise RuntimeError(
            "IMAGE_GEN_PROVIDER=auto requires FAL_API_KEY — the Reve "
            "and Replicate fallbacks were retired in v1.20.",
        )
    p = MockImageGen()
    _log_image_gen_choice(p, reason="auto → no FAL_API_KEY (dev)")
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

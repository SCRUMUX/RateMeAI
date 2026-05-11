"""Unit tests for UnifiedImageGenProvider."""

import pytest
from unittest.mock import AsyncMock

from src.providers.image_gen.unified import UnifiedImageGenProvider


@pytest.fixture
def mock_model_a():
    provider = AsyncMock()
    provider.generate.return_value = b"model_a_bytes"
    return provider


@pytest.fixture
def mock_model_b():
    provider = AsyncMock()
    provider.generate.return_value = b"model_b_bytes"
    return provider


@pytest.fixture
def mock_pulid():
    provider = AsyncMock()
    provider.generate.return_value = b"pulid_bytes"
    return provider


@pytest.fixture
def unified_provider(mock_model_a, mock_model_b, mock_pulid):
    return UnifiedImageGenProvider(
        model_a=mock_model_a,
        model_b=mock_model_b,
        pulid=mock_pulid,
    )


@pytest.mark.asyncio
async def test_routes_to_gpt_by_default(unified_provider, mock_model_a):
    res = await unified_provider.generate("prompt", b"ref")
    assert res == b"model_a_bytes"
    mock_model_a.generate.assert_called_once()


@pytest.mark.asyncio
async def test_routes_to_nano_banana_when_requested(unified_provider, mock_model_b):
    res = await unified_provider.generate(
        "prompt", b"ref", params={"image_model": "nano_banana_2"}
    )
    assert res == b"model_b_bytes"
    mock_model_b.generate.assert_called_once()


@pytest.mark.asyncio
async def test_routes_to_pulid_for_identity_scene(unified_provider, mock_pulid):
    res = await unified_provider.generate(
        "prompt", b"ref", params={"generation_mode": "identity_scene"}
    )
    assert res == b"pulid_bytes"
    mock_pulid.generate.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_to_model_b_on_model_a_failure(
    unified_provider, mock_model_a, mock_model_b
):
    mock_model_a.generate.side_effect = Exception("Model A failed")

    res = await unified_provider.generate("prompt", b"ref")

    assert res == b"model_b_bytes"
    mock_model_a.generate.assert_called_once()
    mock_model_b.generate.assert_called_once()


# ----------------------------------------------------------------------
# v1.24.2 — explicit A/B routing + symmetric fallback
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_to_gpt_image_2_when_explicitly_requested(
    unified_provider, mock_model_a, mock_model_b
):
    """Explicit ``image_model=gpt_image_2`` picks model_a, not model_b."""
    res = await unified_provider.generate(
        "prompt", b"ref", params={"image_model": "gpt_image_2"}
    )
    assert res == b"model_a_bytes"
    mock_model_a.generate.assert_called_once()
    mock_model_b.generate.assert_not_called()


@pytest.mark.asyncio
async def test_symmetric_fallback_b_to_a_on_nano_banana_failure(
    unified_provider, mock_model_a, mock_model_b
):
    """v1.24.2: when the caller picks Nano Banana 2 and it raises, the
    unified provider must retry on GPT-2 (the "other" model), not give
    up. Pre-v1.24.2 the fallback branch was A→B only, so B-first users
    would receive the raw exception.
    """
    mock_model_b.generate.side_effect = Exception("NB2 failed")

    res = await unified_provider.generate(
        "prompt", b"ref", params={"image_model": "nano_banana_2"}
    )

    assert res == b"model_a_bytes"
    mock_model_b.generate.assert_called_once()
    mock_model_a.generate.assert_called_once()


@pytest.mark.asyncio
async def test_symmetric_fallback_preserves_params(
    unified_provider, mock_model_a, mock_model_b
):
    """Fallback forwards the same ``params`` dict (prompt, reference, extras)."""
    mock_model_a.generate.side_effect = Exception("Model A failed")
    params = {"image_model": "gpt_image_2", "quality": "high"}

    await unified_provider.generate("the prompt", b"refbytes", params=params)

    fallback_call = mock_model_b.generate.await_args
    assert fallback_call.kwargs["prompt"] == "the prompt"
    assert fallback_call.kwargs["reference_image"] == b"refbytes"
    assert fallback_call.kwargs["params"]["quality"] == "high"


@pytest.mark.asyncio
async def test_pulid_failure_does_not_fall_back(unified_provider, mock_pulid):
    """Specialised providers (PuLID / Seedream / Rave) are not covered by
    the A/B backstop — they re-raise as before."""
    mock_pulid.generate.side_effect = RuntimeError("pulid down")

    with pytest.raises(RuntimeError, match="pulid down"):
        await unified_provider.generate(
            "prompt", b"ref", params={"generation_mode": "identity_scene"}
        )
    mock_pulid.generate.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_sets_routed_backend_to_other_model(
    unified_provider, mock_model_b
):
    """After a B→A fallback, ``get_routed_backend()`` must report ``gpt_image_2``
    so downstream metrics / logs reflect the actual generator that produced
    the bytes.
    """
    from src.providers.image_gen.unified import get_routed_backend

    mock_model_b.generate.side_effect = Exception("NB2 transient error")
    await unified_provider.generate(
        "p", b"r", params={"image_model": "nano_banana_2"}
    )
    assert get_routed_backend() == "gpt_image_2"


# ----------------------------------------------------------------------
# v1.59.6 — caller-identity guard: bot traffic must NEVER drift to NB2
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bot_source_does_not_fall_back_to_nano_banana_on_gpt_failure(
    unified_provider, mock_model_a, mock_model_b
):
    """Regression: when the Telegram bot picks GPT Image 2 and the call
    raises, the unified provider MUST propagate the exception instead of
    silently retrying on Nano Banana 2.

    Why: the bot is a contractually "always-GPT" client (Telegram has no
    Premium picker, ``src/bot/handlers/mode_select.py`` hard-codes
    ``image_model=gpt_image_2``). Pre-v1.59.6 the symmetric A→B fallback
    kicked in on any GPT-2 hiccup (FAL timeout, OpenAI 5xx, content
    policy on the face), the request was re-run on NB2 with a prompt
    built for GPT-2, and the user got back an image with drifted
    identity. The user-reported incident on 2026-05-10 ~19:24 UTC was
    one of these.
    """
    boom = RuntimeError("GPT Image 2 transient FAL timeout")
    mock_model_a.generate.side_effect = boom

    with pytest.raises(RuntimeError, match="GPT Image 2 transient FAL timeout"):
        await unified_provider.generate(
            "prompt",
            b"ref",
            params={"image_model": "gpt_image_2", "source": "telegram_bot"},
        )

    mock_model_a.generate.assert_called_once()
    mock_model_b.generate.assert_not_called()


@pytest.mark.asyncio
async def test_bot_source_routed_backend_stays_gpt_image_2_on_failure(
    unified_provider, mock_model_a, mock_model_b
):
    """After the guard re-raises, ``get_routed_backend()`` must still
    report ``gpt_image_2`` — we never actually started running NB2, so
    cost metrics / Grafana dashboards must not show a phantom NB2 hit.
    """
    from src.providers.image_gen.unified import get_routed_backend

    mock_model_a.generate.side_effect = RuntimeError("OpenAI 503")

    with pytest.raises(RuntimeError):
        await unified_provider.generate(
            "p", b"r", params={"image_model": "gpt_image_2", "source": "telegram_bot"}
        )
    assert get_routed_backend() == "gpt_image_2"
    mock_model_b.generate.assert_not_called()


@pytest.mark.asyncio
async def test_web_caller_still_falls_back_a_to_b_on_gpt_failure(
    unified_provider, mock_model_a, mock_model_b
):
    """The guard MUST be scoped to ``source=telegram_bot`` only. A web
    client (no ``source`` tag or any other value) must keep getting the
    legacy A→B backstop so a transient GPT-2 error still produces a
    user-visible image, even if it is from NB2.
    """
    mock_model_a.generate.side_effect = Exception("GPT-2 transient")

    res = await unified_provider.generate(
        "prompt", b"ref", params={"image_model": "gpt_image_2"}
    )

    assert res == b"model_b_bytes"
    mock_model_a.generate.assert_called_once()
    mock_model_b.generate.assert_called_once()


@pytest.mark.asyncio
async def test_bot_source_with_nano_banana_choice_still_falls_back_to_gpt(
    unified_provider, mock_model_a, mock_model_b
):
    """Edge case: if some future client tags ``source=telegram_bot`` AND
    explicitly picks Nano Banana 2 (today's bot does not, but the schema
    allows it), the B→A fallback must still apply. The guard only
    disables the A→B direction — falling forward to GPT-2 is always
    safe for the bot contract.
    """
    mock_model_b.generate.side_effect = Exception("NB2 timeout")

    res = await unified_provider.generate(
        "prompt",
        b"ref",
        params={"image_model": "nano_banana_2", "source": "telegram_bot"},
    )

    assert res == b"model_a_bytes"
    mock_model_b.generate.assert_called_once()
    mock_model_a.generate.assert_called_once()

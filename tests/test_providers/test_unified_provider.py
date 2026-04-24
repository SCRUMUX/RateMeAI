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

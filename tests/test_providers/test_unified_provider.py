"""Unit tests for :class:`UnifiedImageGenProvider` (v1.64).

v1.64 collapsed the unified provider to a two-model A/B router
(GPT Image 2 Edit + Nano Banana 2 Edit). The historical PuLID /
Seedream / Rave legs were retired alongside the StyleRouter and the
``generation_mode`` fork; these tests pin the slimmer contract:

* Default model: Model A (GPT Image 2).
* Explicit override: ``params["image_model"]`` picks Model B
  (Nano Banana 2) or stays on Model A.
* Symmetric A↔B fallback when ``allow_cross_model_fallback`` is True
  (default). Same policy for web and bot callers.
"""

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
def unified_provider(mock_model_a, mock_model_b):
    return UnifiedImageGenProvider(
        model_a=mock_model_a,
        model_b=mock_model_b,
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
async def test_unknown_image_model_falls_back_to_default(
    unified_provider, mock_model_a, mock_model_b
):
    """An unrecognised ``image_model`` value defaults to Model A — the
    same fallback the legacy StyleRouter used."""
    res = await unified_provider.generate(
        "prompt", b"ref", params={"image_model": "made_up_v9"}
    )
    assert res == b"model_a_bytes"
    mock_model_a.generate.assert_called_once()
    mock_model_b.generate.assert_not_called()


@pytest.mark.asyncio
async def test_fallback_to_model_b_on_model_a_failure(
    unified_provider, mock_model_a, mock_model_b
):
    mock_model_a.generate.side_effect = Exception("Model A failed")

    res = await unified_provider.generate("prompt", b"ref")

    assert res == b"model_b_bytes"
    mock_model_a.generate.assert_called_once()
    mock_model_b.generate.assert_called_once()


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
async def test_allow_cross_model_fallback_false_skips_retry(
    unified_provider, mock_model_a, mock_model_b
):
    mock_model_a.generate.side_effect = RuntimeError("fail")

    with pytest.raises(RuntimeError, match="fail"):
        await unified_provider.generate(
            "p",
            b"r",
            params={
                "image_model": "gpt_image_2",
                "allow_cross_model_fallback": False,
            },
        )
    mock_model_a.generate.assert_called_once()
    mock_model_b.generate.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_tagged_source_falls_back_a_to_b_on_gpt_failure(
    unified_provider, mock_model_a, mock_model_b
):
    """Bot-tagged traffic uses the same cross-model fallback as web."""
    mock_model_a.generate.side_effect = Exception("GPT-2 transient")

    res = await unified_provider.generate(
        "prompt",
        b"ref",
        params={
            "image_model": "gpt_image_2",
            "source": "telegram_bot",
            "allow_cross_model_fallback": True,
        },
    )

    assert res == b"model_b_bytes"
    mock_model_a.generate.assert_called_once()
    mock_model_b.generate.assert_called_once()

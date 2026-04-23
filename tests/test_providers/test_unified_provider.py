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
    res = await unified_provider.generate("prompt", b"ref", params={"image_model": "nano_banana_2"})
    assert res == b"model_b_bytes"
    mock_model_b.generate.assert_called_once()

@pytest.mark.asyncio
async def test_routes_to_pulid_for_identity_scene(unified_provider, mock_pulid):
    res = await unified_provider.generate("prompt", b"ref", params={"generation_mode": "identity_scene"})
    assert res == b"pulid_bytes"
    mock_pulid.generate.assert_called_once()

@pytest.mark.asyncio
async def test_fallback_to_model_b_on_model_a_failure(unified_provider, mock_model_a, mock_model_b):
    mock_model_a.generate.side_effect = Exception("Model A failed")
    
    res = await unified_provider.generate("prompt", b"ref")
    
    assert res == b"model_b_bytes"
    mock_model_a.generate.assert_called_once()
    mock_model_b.generate.assert_called_once()

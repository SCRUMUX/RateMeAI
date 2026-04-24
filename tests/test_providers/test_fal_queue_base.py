"""Unit tests for the shared FAL queue client (:mod:`_fal_queue_base`).

v1.24.2 regression coverage for two specific behaviours that the
per-provider tests don't exercise directly:

* ``_fallback_status_url`` / ``_fallback_result_url`` must keep the
  FULL appId (every path segment), including ``/edit`` subpaths on
  proxy models. Prior to v1.24.2 the helpers truncated to the first
  two segments and 404'd against FAL for 3+ segment apps.
* ``_submit_url`` also uses the full model path.

Both helpers are pure URL builders — no HTTP needed.
"""

from __future__ import annotations

import pytest

from src.providers.image_gen._fal_queue_base import FalQueueClient


def _client(model: str) -> FalQueueClient:
    """Instantiate the base class directly; we only use the URL helpers."""
    return FalQueueClient(
        api_key="dummy-key",
        model=model,
        api_host="https://queue.fal.run",
        label="test",
    )


REQ_ID = "019dbdd0-b9fa-76e3-8dd1-b00399a1d567"


@pytest.mark.parametrize(
    "model,expected_status,expected_result,expected_submit",
    [
        # 2-segment apps (legacy FLUX / GFPGAN / Real-ESRGAN path).
        (
            "fal-ai/gfpgan",
            f"https://queue.fal.run/fal-ai/gfpgan/requests/{REQ_ID}/status",
            f"https://queue.fal.run/fal-ai/gfpgan/requests/{REQ_ID}",
            "https://queue.fal.run/fal-ai/gfpgan",
        ),
        # 3-segment proxy apps (Nano Banana 2 Edit, GPT Image 2 Edit,
        # FLUX.2 Pro Edit). Pre-v1.24.2 these lost the last segment.
        (
            "fal-ai/nano-banana-2/edit",
            f"https://queue.fal.run/fal-ai/nano-banana-2/edit/requests/{REQ_ID}/status",
            f"https://queue.fal.run/fal-ai/nano-banana-2/edit/requests/{REQ_ID}",
            "https://queue.fal.run/fal-ai/nano-banana-2/edit",
        ),
        (
            "openai/gpt-image-2/edit",
            f"https://queue.fal.run/openai/gpt-image-2/edit/requests/{REQ_ID}/status",
            f"https://queue.fal.run/openai/gpt-image-2/edit/requests/{REQ_ID}",
            "https://queue.fal.run/openai/gpt-image-2/edit",
        ),
        # 5-segment app (Seedream v4). Pre-v1.24.2 was truncated to
        # ``fal-ai/bytedance`` which is not even a valid FAL endpoint.
        (
            "fal-ai/bytedance/seedream/v4/edit",
            (
                "https://queue.fal.run/fal-ai/bytedance/seedream/v4/edit"
                f"/requests/{REQ_ID}/status"
            ),
            (
                "https://queue.fal.run/fal-ai/bytedance/seedream/v4/edit"
                f"/requests/{REQ_ID}"
            ),
            "https://queue.fal.run/fal-ai/bytedance/seedream/v4/edit",
        ),
    ],
)
def test_url_helpers_keep_full_app_path(
    model: str,
    expected_status: str,
    expected_result: str,
    expected_submit: str,
) -> None:
    c = _client(model)
    assert c._submit_url() == expected_submit
    assert c._fallback_status_url(REQ_ID) == expected_status
    assert c._fallback_result_url(REQ_ID) == expected_result


def test_fallback_urls_do_not_strip_edit_segment() -> None:
    """Regression: the bug that produced ``Path /requests/.../status not found``.

    Specifically guards against returning ``fal-ai/nano-banana-2`` when
    the actual app is ``fal-ai/nano-banana-2/edit``.
    """
    c = _client("fal-ai/nano-banana-2/edit")
    assert "/edit/" in c._fallback_status_url(REQ_ID)
    assert "/edit/" in c._fallback_result_url(REQ_ID)
    assert c._fallback_status_url(REQ_ID).endswith(f"{REQ_ID}/status")


def test_model_with_trailing_slash_is_normalised() -> None:
    """``self._model`` is stripped of leading/trailing slashes on init."""
    c = _client("/fal-ai/nano-banana-2/edit/")
    assert c._model == "fal-ai/nano-banana-2/edit"
    assert (
        c._fallback_status_url(REQ_ID)
        == f"https://queue.fal.run/fal-ai/nano-banana-2/edit/requests/{REQ_ID}/status"
    )


def test_host_trailing_slash_is_normalised() -> None:
    """Trailing slash on ``api_host`` must not produce ``//requests/``."""
    c = FalQueueClient(
        api_key="dummy-key",
        model="fal-ai/nano-banana-2/edit",
        api_host="https://queue.fal.run/",
        label="test",
    )
    assert "//requests/" not in c._fallback_status_url(REQ_ID)
    assert c._submit_url() == "https://queue.fal.run/fal-ai/nano-banana-2/edit"

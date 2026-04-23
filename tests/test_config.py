"""Guards for sensitive defaults in :mod:`src.config`.

Keep these small and strict — every assertion here exists because a
wrong default shipped to production and bricked the image pipeline.
"""

from __future__ import annotations

from src.config import Settings


def test_pulid_defaults_within_lightning_schema():
    """fal-ai/pulid is strictly a Lightning model.

    The public API schema caps ``num_inference_steps`` at 12 and
    ``guidance_scale`` at 1.5. v1.19.0 shipped 25 / 3.5 and every
    production request was rejected with HTTP 422 for a week. This
    test makes sure the defaults can never silently drift back.
    """
    s = Settings()

    assert 1 <= s.pulid_steps <= 12, (
        f"pulid_steps={s.pulid_steps} is outside the fal-ai/pulid "
        f"Lightning schema [1, 12]. The API will reject the request "
        f"with HTTP 422. See v1.19.2 hotfix."
    )
    assert 1.0 <= s.pulid_guidance_scale <= 1.5, (
        f"pulid_guidance_scale={s.pulid_guidance_scale} is outside the "
        f"fal-ai/pulid Lightning schema [1.0, 1.5]. The API will reject "
        f"the request with HTTP 422. See v1.19.2 hotfix."
    )

    assert 1 <= s.pulid_retry_steps <= 12, (
        f"pulid_retry_steps={s.pulid_retry_steps} is outside the "
        f"Lightning schema. Retries 422 just like first attempts."
    )
    assert 1.0 <= s.pulid_retry_guidance_scale <= 1.5, (
        f"pulid_retry_guidance_scale={s.pulid_retry_guidance_scale} "
        f"is outside the Lightning schema. Retries 422."
    )


def test_pulid_retry_escalates_over_baseline():
    """The retry knob set must be stronger than the first-pass knobs.

    Otherwise retries do nothing for identity recovery.
    """
    s = Settings()
    assert s.pulid_retry_id_scale >= s.pulid_id_scale
    assert s.pulid_retry_steps >= s.pulid_steps
    assert s.pulid_retry_guidance_scale >= s.pulid_guidance_scale

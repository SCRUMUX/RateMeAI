"""v1.72 — unit tests for :class:`FalClarityUpscaler`.

Pins the request body shape and the parameter clamping rules. We
do NOT exercise the HTTP queue protocol end-to-end here — that is
the shared ``FalQueueClient`` contract, covered by Real-ESRGAN /
GFPGAN tests. The tier-specific surface we lock here is:

* default ``creativity`` / ``resemblance`` / ``dynamic`` /
  ``upscale_factor`` values from ``fal_clarity_upscaler.py`` are
  identity-preserving (low creativity, high resemblance, no
  upscale);
* explicit values are clamped to their valid ranges so a future
  config tweak can't accidentally ship ``creativity=12``.
"""

from __future__ import annotations

from src.providers.image_gen.fal_clarity_upscaler import (
    FalClarityUpscaler,
    _DEFAULT_CREATIVITY,
    _DEFAULT_DYNAMIC,
    _DEFAULT_RESEMBLANCE,
)


def _client() -> FalClarityUpscaler:
    return FalClarityUpscaler(api_key="test")


class TestBodyDefaults:
    def test_defaults_lock_identity_preserving_values(self):
        body = _client()._build_body(reference_image=b"\xff\xd8\xff\xd9")
        # Body-builder default for ``upscale_factor`` is 1.0 (same-res
        # polish). The premium-tier ×2 bump comes from
        # ``settings.clarity_refiner_upscale_factor`` which the
        # orchestrator passes in as ``params["upscale_factor"]``.
        assert body["upscale_factor"] == 1.0
        assert body["creativity"] == _DEFAULT_CREATIVITY == 0.2
        assert body["resemblance"] == _DEFAULT_RESEMBLANCE == 0.8
        assert body["dynamic"] == _DEFAULT_DYNAMIC == 5
        assert body["sync_mode"] is True
        assert body["image_url"].startswith("data:image/")

    def test_explicit_overrides_passed_through(self):
        body = _client()._build_body(
            reference_image=b"\xff\xd8\xff\xd9",
            params={
                "creativity": 0.4,
                "resemblance": 1.2,
                "dynamic": 8,
                "upscale_factor": 2.0,
            },
        )
        assert body["creativity"] == 0.4
        assert body["resemblance"] == 1.2
        assert body["dynamic"] == 8
        assert body["upscale_factor"] == 2.0

    def test_premium_default_upscale_factor_round_trips(self):
        # The new Premium-tier default — float so operators can dial
        # to 1.5 mid-incident without a code change.
        body = _client()._build_body(
            reference_image=b"\xff\xd8\xff\xd9",
            params={"upscale_factor": 1.5},
        )
        assert body["upscale_factor"] == 1.5


class TestParameterClamping:
    def test_creativity_clamped_to_unit_interval(self):
        body = _client()._build_body(
            reference_image=b"\xff\xd8\xff\xd9",
            params={"creativity": 12.0},
        )
        assert body["creativity"] == 1.0

    def test_creativity_clamped_negative(self):
        body = _client()._build_body(
            reference_image=b"\xff\xd8\xff\xd9",
            params={"creativity": -0.5},
        )
        assert body["creativity"] == 0.0

    def test_resemblance_clamped_to_four(self):
        body = _client()._build_body(
            reference_image=b"\xff\xd8\xff\xd9",
            params={"resemblance": 99.0},
        )
        assert body["resemblance"] == 4.0

    def test_dynamic_clamped_to_max(self):
        body = _client()._build_body(
            reference_image=b"\xff\xd8\xff\xd9",
            params={"dynamic": 1000.0},
        )
        assert body["dynamic"] == 50.0

    def test_dynamic_clamped_below_one(self):
        body = _client()._build_body(
            reference_image=b"\xff\xd8\xff\xd9",
            params={"dynamic": 0.1},
        )
        assert body["dynamic"] == 1.0

    def test_upscale_factor_clamped_above_four(self):
        body = _client()._build_body(
            reference_image=b"\xff\xd8\xff\xd9",
            params={"upscale_factor": 8},
        )
        assert body["upscale_factor"] == 4.0

    def test_upscale_factor_clamped_below_one(self):
        body = _client()._build_body(
            reference_image=b"\xff\xd8\xff\xd9",
            params={"upscale_factor": 0},
        )
        assert body["upscale_factor"] == 1.0

    def test_garbage_values_fall_back_to_defaults(self):
        body = _client()._build_body(
            reference_image=b"\xff\xd8\xff\xd9",
            params={
                "creativity": "nan",
                "resemblance": None,
                "dynamic": object(),
                "upscale_factor": "abc",
            },
        )
        assert body["creativity"] == _DEFAULT_CREATIVITY
        assert body["resemblance"] == _DEFAULT_RESEMBLANCE
        assert body["dynamic"] == _DEFAULT_DYNAMIC
        assert body["upscale_factor"] == 1.0


class TestEmptyInputs:
    def test_missing_image_raises(self):
        try:
            _client()._build_body(reference_image=None)
        except ValueError as exc:
            assert "FalClarityUpscaler" in str(exc)
        else:  # pragma: no cover — defensive
            raise AssertionError("expected ValueError")

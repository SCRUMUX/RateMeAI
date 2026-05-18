"""Guards for sensitive defaults in :mod:`src.config`.

Keep these small and strict — every assertion here exists because a
wrong default shipped to production and bricked the image pipeline.
"""

from __future__ import annotations

from src.config import Settings


def test_csl_reference_pad_defaults_enabled():
    """v1.64 anatomy fix kill-switch must default ON in production.

    The pad gate itself is composition-class-bounded (only fires on
    ``face_closeup`` / ``unknown`` half/full-body inputs), so a True
    default is a no-op for loose-crop photos and only kicks in
    where it's needed.
    """
    s = Settings()
    assert s.csl_reference_pad_enabled is True, (
        f"csl_reference_pad_enabled defaulted to {s.csl_reference_pad_enabled} — "
        f"v1.64 anatomy fix relies on this being ON. See "
        f"src/orchestrator/executor.py:should_pad gate and "
        f"docs/ARCHITECTURE.md §8.9."
    )


def test_credit_pack_defaults_documented():
    """Tariff CSV defaults in Settings must match product grid (env may override)."""
    packs_default = Settings.model_fields["credit_packs"].default
    usd_default = Settings.model_fields["credit_packs_usd"].default
    assert "5:227" in packs_default
    assert "50:1527" in packs_default
    assert "3.27" in usd_default
    assert "19.27" in usd_default

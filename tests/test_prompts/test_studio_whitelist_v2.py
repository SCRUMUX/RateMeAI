"""v1.68 P1.5 — extended studio-portrait whitelist behaviour.

The v1.66 whitelist contained only ``formal_portrait`` and
``studio_elegant``. v1.68 extends it (under feature flag
``studio_portrait_whitelist_v2``) to cover ``corporate``,
``boardroom``, ``legal_finance``, ``neutral`` and ``medical`` —
career styles that ship the same design intent (controlled
environment, formal wardrobe, classic head-and-shoulders
composition) but historically routed to ``half_body`` framing and
inherited the "huge head" pathology.

These tests pin three contracts:

* :func:`is_studio_portrait_style` returns True for the new entries
  iff the flag is True.
* :func:`resolve_effective_framing` short-circuits the new entries
  to ``"portrait"`` when the flag is True, regardless of CSL
  classification or user pick.
* The v1.66 entries (``formal_portrait``, ``studio_elegant``)
  remain in the whitelist with or without the flag — the flag
  EXTENDS the set, never shrinks it.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.prompts.image_gen import (
    _STUDIO_PORTRAIT_STYLE_KEYS,
    _STUDIO_PORTRAIT_STYLE_KEYS_V2,
    is_studio_portrait_style,
)
from src.services.composition_safety import (
    CompositionClass,
    resolve_effective_framing,
)


# Career-style keys newly added in v1.68. Kept explicit (not derived
# from the dict difference) so a typo in the implementation file
# fails this test loudly instead of silently passing.
_NEW_IN_V168 = ("corporate", "boardroom", "legal_finance", "neutral", "medical")


@pytest.mark.parametrize("style", _NEW_IN_V168)
def test_new_entries_are_studio_portrait_when_flag_on(style: str, monkeypatch):
    monkeypatch.setattr(settings, "studio_portrait_whitelist_v2", True)
    assert is_studio_portrait_style(style) is True


@pytest.mark.parametrize("style", _NEW_IN_V168)
def test_new_entries_are_not_studio_portrait_when_flag_off(
    style: str, monkeypatch
):
    monkeypatch.setattr(settings, "studio_portrait_whitelist_v2", False)
    assert is_studio_portrait_style(style) is False


@pytest.mark.parametrize("style", ["formal_portrait", "studio_elegant"])
def test_v166_entries_unchanged_with_or_without_flag(style: str, monkeypatch):
    monkeypatch.setattr(settings, "studio_portrait_whitelist_v2", False)
    assert is_studio_portrait_style(style) is True
    monkeypatch.setattr(settings, "studio_portrait_whitelist_v2", True)
    assert is_studio_portrait_style(style) is True


def test_v2_whitelist_is_superset_of_v166():
    assert _STUDIO_PORTRAIT_STYLE_KEYS <= _STUDIO_PORTRAIT_STYLE_KEYS_V2, (
        "studio_portrait_whitelist_v2 must be a SUPERSET of the v1.66 set; "
        "shrinking it would silently regress the v1.66 anatomy fix."
    )


@pytest.mark.parametrize("style", _NEW_IN_V168)
def test_resolve_effective_framing_pins_new_entries_to_portrait(
    style: str, monkeypatch
):
    """End-to-end: with the flag on, the executor's framing resolver
    short-circuits the new entries to ``portrait`` even if the upload
    is a full-body shot (the path that historically routed the user
    into ``half_body``).
    """
    monkeypatch.setattr(settings, "studio_portrait_whitelist_v2", True)
    is_studio = is_studio_portrait_style(style)
    effective = resolve_effective_framing(
        user_framing="half_body",
        composition_class=CompositionClass.FULL_BODY,
        spec=None,
        is_document=False,
        is_studio_portrait=is_studio,
    )
    assert effective == "portrait", (
        f"style={style!r} should be pinned to portrait under "
        f"studio_portrait_whitelist_v2; got {effective!r}"
    )


@pytest.mark.parametrize("style", _NEW_IN_V168)
def test_resolve_effective_framing_respects_user_when_flag_off(
    style: str, monkeypatch
):
    """Flag OFF: the resolver returns the user's pick (``half_body``)
    — that is the legacy behaviour the flag was designed to fix.
    """
    monkeypatch.setattr(settings, "studio_portrait_whitelist_v2", False)
    is_studio = is_studio_portrait_style(style)
    effective = resolve_effective_framing(
        user_framing="half_body",
        composition_class=CompositionClass.FULL_BODY,
        spec=None,
        is_document=False,
        is_studio_portrait=is_studio,
    )
    assert effective == "half_body", (
        f"style={style!r} with flag OFF should return the user's pick; "
        f"got {effective!r}"
    )

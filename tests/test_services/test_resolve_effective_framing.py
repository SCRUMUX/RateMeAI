"""Unit tests for :func:`resolve_effective_framing`.

The resolver is the single source of truth for "what framing should
this generation actually run with". Both the executor (server-side
auto-resolution) and the bot (UI default picker) call it, so a
silent regression in priority handling here would cascade everywhere.

The test matrix below pins every documented branch of the priority
ladder:

1. Document style → ``portrait`` regardless of every other signal.
2. ``user_framing`` wins when it is in ``allowed_framings`` for
   the upload's composition class.
3. ``user_framing`` is dropped when it is NOT in
   ``allowed_framings`` — auto-pick takes over.
4. ``needs_full_body`` style boosts to ``full_body`` when the
   composition class allows it.
5. Otherwise the first canonical framing in
   ``(portrait, half_body, full_body)`` that is allowed wins.
6. UNKNOWN class is fail-closed-safe to ``portrait``.
"""

from __future__ import annotations

import pytest

from src.services.composition_safety import (
    CompositionClass,
    resolve_effective_framing,
)


class _Spec:
    """Tiny stand-in for a StyleSpec — only ``needs_full_body`` matters."""

    def __init__(self, *, needs_full_body: bool = False) -> None:
        self.needs_full_body = needs_full_body


@pytest.mark.parametrize("user_framing", [None, "", "portrait", "half_body", "full_body", "square"])
def test_document_short_circuits_to_portrait(user_framing):
    """Document styles always run portrait regardless of user pick."""
    assert (
        resolve_effective_framing(
            user_framing=user_framing,
            composition_class=CompositionClass.FULL_BODY,
            spec=_Spec(needs_full_body=True),
            is_document=True,
        )
        == "portrait"
    )


@pytest.mark.parametrize(
    "composition_class,user_pick,expected",
    [
        # FACE_CLOSEUP allowed = (portrait,). Only portrait survives.
        (CompositionClass.FACE_CLOSEUP, "portrait", "portrait"),
        (CompositionClass.FACE_CLOSEUP, "half_body", "portrait"),
        (CompositionClass.FACE_CLOSEUP, "full_body", "portrait"),
        # PORTRAIT allowed = (portrait, half_body). full_body collapses to portrait.
        (CompositionClass.PORTRAIT, "portrait", "portrait"),
        (CompositionClass.PORTRAIT, "half_body", "half_body"),
        (CompositionClass.PORTRAIT, "full_body", "portrait"),
        # HALF_BODY allows everything → user pick wins.
        (CompositionClass.HALF_BODY, "portrait", "portrait"),
        (CompositionClass.HALF_BODY, "half_body", "half_body"),
        (CompositionClass.HALF_BODY, "full_body", "full_body"),
        # FULL_BODY allows everything → user pick wins.
        (CompositionClass.FULL_BODY, "portrait", "portrait"),
        (CompositionClass.FULL_BODY, "full_body", "full_body"),
    ],
)
def test_user_pick_wins_when_allowed(composition_class, user_pick, expected):
    """Explicit user pick is respected if the policy admits it."""
    assert (
        resolve_effective_framing(
            user_framing=user_pick,
            composition_class=composition_class,
            spec=_Spec(),
            is_document=False,
        )
        == expected
    )


@pytest.mark.parametrize(
    "user_pick",
    [None, "", "square", "panoramic", "weird-token"],
)
def test_no_pick_falls_back_to_first_allowed(user_pick):
    """When there is no valid user pick, the resolver returns the
    first canonical framing in (portrait → half_body → full_body)
    that the policy allows. For HALF_BODY that's ``portrait``."""
    assert (
        resolve_effective_framing(
            user_framing=user_pick,
            composition_class=CompositionClass.HALF_BODY,
            spec=_Spec(),
            is_document=False,
        )
        == "portrait"
    )


def test_needs_full_body_boost_when_full_body_allowed():
    """A style asking for ``needs_full_body`` jumps to ``full_body``
    when the policy allows it AND the user gave no explicit pick."""
    assert (
        resolve_effective_framing(
            user_framing=None,
            composition_class=CompositionClass.FULL_BODY,
            spec=_Spec(needs_full_body=True),
            is_document=False,
        )
        == "full_body"
    )


def test_needs_full_body_ignored_when_policy_forbids():
    """``needs_full_body=True`` on a FACE_CLOSEUP upload must NOT
    override the policy — the resolver picks ``portrait`` (the only
    allowed framing for the class)."""
    assert (
        resolve_effective_framing(
            user_framing=None,
            composition_class=CompositionClass.FACE_CLOSEUP,
            spec=_Spec(needs_full_body=True),
            is_document=False,
        )
        == "portrait"
    )


def test_unknown_class_is_fail_closed_to_portrait():
    """UNKNOWN class collapses to portrait — same as the policy
    table's ``allowed_framings`` for UNKNOWN."""
    for pick in (None, "half_body", "full_body"):
        assert (
            resolve_effective_framing(
                user_framing=pick,
                composition_class=CompositionClass.UNKNOWN,
                spec=_Spec(),
                is_document=False,
            )
            == "portrait"
        )


def test_string_composition_class_parsed():
    """Resolver accepts a raw string ``composition_class`` (the format
    persisted on :class:`InputQualityReport`) and parses it via
    :meth:`CompositionClass.parse`."""
    assert (
        resolve_effective_framing(
            user_framing="half_body",
            composition_class="half_body",
            spec=_Spec(),
            is_document=False,
        )
        == "half_body"
    )


def test_spec_none_does_not_crash():
    """Caller may pass ``spec=None`` for emoji-only / legacy flows;
    resolver must treat that as ``needs_full_body=False`` and walk
    the fallback ladder."""
    assert (
        resolve_effective_framing(
            user_framing=None,
            composition_class=CompositionClass.FULL_BODY,
            spec=None,
            is_document=False,
        )
        == "portrait"
    )


@pytest.mark.parametrize("user_framing", [None, "", "portrait", "half_body", "full_body"])
def test_studio_portrait_short_circuits_to_portrait(user_framing):
    """v1.66 — studio-portrait styles (``formal_portrait``,
    ``studio_elegant``) are by-design tight headshots. The resolver
    pins them to ``portrait`` regardless of user pick, CSL
    classification, or ``needs_full_body`` — mirroring the
    document-style short-circuit branch."""
    assert (
        resolve_effective_framing(
            user_framing=user_framing,
            composition_class=CompositionClass.FULL_BODY,
            spec=_Spec(needs_full_body=True),
            is_document=False,
            is_studio_portrait=True,
        )
        == "portrait"
    )


def test_studio_portrait_default_false_preserves_legacy_path():
    """The ``is_studio_portrait`` parameter is optional and defaults
    to ``False`` — callers that haven't been migrated keep behaving
    exactly as in v1.65."""
    assert (
        resolve_effective_framing(
            user_framing="full_body",
            composition_class=CompositionClass.FULL_BODY,
            spec=_Spec(needs_full_body=True),
            is_document=False,
        )
        == "full_body"
    )

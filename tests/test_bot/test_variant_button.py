"""Tests for the "Другой вариант" bot UX.

Covers:
 * result keyboard emits ``variant:*`` callback with the current style
 * ``variant:*`` handler resolves a variant via StyleVariationService and
   forwards it to ``_submit_analysis`` as ``variant_id`` form data
 * document styles skip variant resolution (seed-only reroll)
 * legacy ``enhance:*`` callback is accepted for one release
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def test_post_result_keyboard_emits_variant_callback_for_current_style():
    from src.bot.keyboards import post_result_keyboard

    kb = post_result_keyboard(
        mode="dating",
        user_id="1",
        bot_username="testbot",
        next_options=None,
        current_style="yoga_outdoor",
    )
    flat = [btn for row in kb.inline_keyboard for btn in row]
    variant_btns = [b for b in flat if b.callback_data == "variant:dating:yoga_outdoor"]
    assert variant_btns, (
        "Keyboard must include a 'variant:dating:yoga_outdoor' button for the current style"
    )
    assert "Другой вариант" in variant_btns[0].text


def test_post_result_keyboard_without_current_style_uses_fallback_variant_label():
    from src.bot.keyboards import post_result_keyboard

    kb = post_result_keyboard(
        mode="dating",
        user_id="1",
        bot_username="testbot",
    )
    flat = [btn for row in kb.inline_keyboard for btn in row]
    callback_datas = [b.callback_data for b in flat if b.callback_data]
    assert any(cd and cd.startswith("variant:dating:") for cd in callback_datas)


@pytest.mark.asyncio
async def test_variant_handler_resolves_and_forwards_variant_id(monkeypatch):
    """``on_variant_request`` must call resolve_next_variant and pass the
    returned id through to ``_submit_analysis`` as ``variant_id``.
    """
    from src.bot.handlers import mode_select as ms
    from src.prompts.style_spec import StyleVariant

    captured: dict[str, object] = {}

    async def fake_submit(callback, api_base_url, redis, mode, style, *, variant_id=""):
        captured["mode"] = mode
        captured["style"] = style
        captured["variant_id"] = variant_id

    monkeypatch.setattr(ms, "_submit_analysis", fake_submit)

    async def fake_maybe_warn(callback, redis, mode, style):  # noqa: ARG001
        return False

    monkeypatch.setattr(
        ms,
        "_maybe_warn_style_reference_mismatch",
        fake_maybe_warn,
    )

    chosen = StyleVariant(id="chosen_variant", scene="x", lighting="y")

    # Mock STYLE_REGISTRY to return a spec with variants so it passes the check
    from src.prompts.image_gen import STYLE_REGISTRY
    from src.prompts.style_spec import StyleSpec

    fake_spec = StyleSpec(
        key="yoga_outdoor",
        mode="dating",
        background="x",
        clothing_male="y",
        clothing_female="z",
        lighting="a",
        expression="b",
        variants=(chosen,),
    )
    monkeypatch.setattr(STYLE_REGISTRY, "get", lambda m, s: fake_spec)

    async def fake_resolve(redis, spec, user_id, mode, style):  # noqa: ARG001
        return chosen

    import src.services.variation as variation_mod

    monkeypatch.setattr(variation_mod, "resolve_next_variant", fake_resolve)

    callback = MagicMock()
    callback.data = "variant:dating:yoga_outdoor"
    callback.from_user.id = 42
    callback.answer = AsyncMock()
    callback.message = MagicMock()

    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)

    await ms._handle_variant_callback(
        callback, "http://api", redis, "dating", "yoga_outdoor"
    )

    assert captured["mode"] == "dating"
    assert captured["style"] == "yoga_outdoor"
    assert captured["variant_id"] == "chosen_variant"


@pytest.mark.asyncio
async def test_variant_handler_skips_resolver_for_document_styles(monkeypatch):
    from src.bot.handlers import mode_select as ms

    captured: dict[str, object] = {}

    async def fake_submit(callback, api_base_url, redis, mode, style, *, variant_id=""):
        captured["variant_id"] = variant_id

    monkeypatch.setattr(ms, "_submit_analysis", fake_submit)

    async def fake_maybe_warn(*args, **kwargs):  # noqa: ARG001
        return False

    monkeypatch.setattr(
        ms,
        "_maybe_warn_style_reference_mismatch",
        fake_maybe_warn,
    )

    import src.services.variation as variation_mod

    async def fake_resolve(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("resolver must NOT run for document styles")

    monkeypatch.setattr(variation_mod, "resolve_next_variant", fake_resolve)

    callback = MagicMock()
    callback.data = "variant:cv:passport_rf"
    callback.from_user.id = 1
    callback.answer = AsyncMock()
    callback.message = MagicMock()

    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)

    await ms._handle_variant_callback(
        callback, "http://api", redis, "cv", "passport_rf"
    )

    assert captured["variant_id"] == ""


@pytest.mark.asyncio
async def test_enhance_alias_forwards_to_variant_flow(monkeypatch):
    """The legacy ``enhance:*`` callback must still work — aliasing to the
    new variant flow for one release.
    """
    from src.bot.handlers import mode_select as ms

    captured: dict[str, object] = {}

    async def fake_variant(callback, api_base_url, redis, mode, style):
        captured["mode"] = mode
        captured["style"] = style

    monkeypatch.setattr(ms, "_handle_variant_callback", fake_variant)

    callback = MagicMock()
    callback.data = "enhance:dating:yoga_outdoor"
    callback.from_user.id = 5
    callback.answer = AsyncMock()
    callback.message = MagicMock()

    await ms.on_enhancement_choice(callback, "http://api", MagicMock())

    assert captured["mode"] == "dating"
    assert captured["style"] == "yoga_outdoor"

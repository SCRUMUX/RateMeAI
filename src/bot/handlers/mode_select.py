from __future__ import annotations

import io
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
import httpx
from redis.asyncio import Redis

from src.bot.middleware import PHOTO_KEY, get_bot_auth_headers
from src.bot.keyboards import (
    error_keyboard,
    scenario_keyboard,
    back_keyboard,
    style_keyboard,
    STYLE_CATALOG,
)
from src.config import settings
from src.services.enhancement_advisor import build_enhancement_preview
from src.services.input_quality import check_style_reference_compat
from src.utils.text_sanitize import sanitize_llm_text

logger = logging.getLogger(__name__)
router = Router()
PRE_ANALYSIS_REF_KEY = "ratemeai:preanalysis_ref:{}"
# face_area_ratio of the last uploaded photo, populated on pre-analyze and
# read at style-selection time for the style × reference compat check.
FACE_AREA_RATIO_KEY = "ratemeai:face_area:{}"
_FACE_AREA_TTL = 1800  # matches pre-analysis cache

# Composition Safety Layer — composition_class of the last uploaded
# photo (CompositionClass value: face_closeup | portrait | half_body
# | full_body | unknown). Populated alongside FACE_AREA_RATIO_KEY on
# successful pre-analyze and consumed by _framing_for_style /
# _maybe_warn_style_reference_mismatch to decide which framing /
# styles are allowed without a fresh /pre-analyze call. TTL mirrors
# the pre-analysis cache so the two never get out of sync.
COMPOSITION_CLASS_KEY = "ratemeai:composition_class:{}"
_COMPOSITION_CLASS_TTL = 1800

LAST_GEN_KEY = "ratemeai:last_gen:{}"

# Per-user set of "{mode}:{style}" tuples for which the reference-mismatch
# warning was already acknowledged. Keeps the "Другой вариант" loop clean
# — once the user taps "Продолжить с риском", we never re-show the
# warning for that specific style on the same photo.
# TTL mirrors the photo / face-area cache so a new upload restarts the
# consent surface naturally.
RISK_ACCEPTED_KEY = "ratemeai:risk_accepted:{}"
_RISK_ACCEPTED_TTL = 1800
USED_STYLES_KEY = "ratemeai:used_styles:{}:{}"


def _build_display_names() -> dict[str, dict[str, str]]:
    """Build display name mapping from STYLE_CATALOG, stripping emoji prefixes."""
    result: dict[str, dict[str, str]] = {}
    for mode, items in STYLE_CATALOG.items():
        mapping: dict[str, str] = {}
        for key, label, _hook, *_rest in items:
            clean = label.lstrip()
            parts = clean.split(" ", 1)
            mapping[key] = parts[1] if len(parts) > 1 else parts[0]
        result[mode] = mapping
    return result


_STYLE_DISPLAY_NAMES: dict[str, dict[str, str]] = _build_display_names()
_PROCESSING_LOCK = "ratemeai:processing:{}"
_LOCK_TTL = 300


async def _read_composition_class(
    redis: Redis | None, user_id: int | str
) -> str:
    """Read the cached ``composition_class`` for this user from Redis.

    Returns the CompositionClass *value string* (``portrait`` /
    ``half_body`` / ``full_body`` / ``face_closeup`` / ``unknown``).
    Defaults to ``unknown`` on any read failure — the policy table
    treats UNKNOWN as the most constrained bucket, so a transient
    Redis outage cannot accidentally unlock full-body styles.
    """
    if redis is None:
        return "unknown"
    try:
        raw = await redis.get(COMPOSITION_CLASS_KEY.format(user_id))
    except Exception:
        return "unknown"
    if raw is None:
        return "unknown"
    return raw.decode() if isinstance(raw, bytes) else str(raw)


async def _framing_for_style(
    mode: str,
    style: str,
    redis: Redis | None = None,
    user_id: int | str | None = None,
) -> str:
    """Pick the composition framing used by /analyze and the prompt engine.

    Telegram clients never expose a "ракурс" picker, so without this the
    executor would fall back to its compatibility default which is wrong
    for two of the three photo modes:

    * Telegram reference images are always ``message.photo[-1]`` previews
      (≤1280 px), and in practice that is a tight head-and-shoulders crop.
      ``half_body`` instructs the edit model to draw a torso around the
      same-sized head, which produces the "oversized head, pasted face"
      failure mode reported by users.
    * Web clients default to ``portrait`` (head and shoulders) — see
      ``web/src/context/AppContext.tsx``. Aligning the bot with the web
      default closes the most visible quality gap between the channels.

    v1.65 — thin wrapper over
    :func:`src.services.composition_safety.resolve_effective_framing`,
    which is now the single source of truth for "what framing should
    actually drive the generation". The executor and the bot share the
    same resolver so the UI shows the same framing the executor will
    end up generating, and a single fix to the priority matrix lands
    in both entrypoints atomically.
    """
    try:
        from src.prompts.image_gen import (
            STYLE_REGISTRY,
            is_document_style,
            is_studio_portrait_style,
        )
        from src.services.composition_safety import resolve_effective_framing

        cls_raw = (
            await _read_composition_class(redis, user_id)
            if user_id is not None
            else "unknown"
        )
        spec = STYLE_REGISTRY.get(mode, style)
        return resolve_effective_framing(
            user_framing=None,
            composition_class=cls_raw,
            spec=spec,
            is_document=is_document_style(style),
            is_studio_portrait=is_studio_portrait_style(style),
        )
    except Exception:
        logger.debug("framing_resolve_failed mode=%s style=%s", mode, style)
        return "portrait"

# P1.1: short-lived locks against rapid double-taps on read-only / cheap
# callbacks.  ``_PRE_ANALYZE_LOCK`` covers the expensive pre-analyze
# LLM call (no credits, but billable), while ``_UI_NAV_LOCK`` debounces
# pure UI navigation (styles paging / restyle) where the only damage
# is an ``edit_reply_markup`` race.
_PRE_ANALYZE_LOCK = "ratemeai:pre_analyze_lock:{}"
_PRE_ANALYZE_LOCK_TTL = 60
_UI_NAV_LOCK = "ratemeai:ui_nav_lock:{}"
_UI_NAV_LOCK_TTL = 3
DEPTH_KEY = "ratemeai:depth:{}:{}"

# Task polling (_poll_task): must cover worker latency + DB commit lag + slow image gen (Replicate).
# When Redis publishes task_done, we only need to wait until GET /tasks returns completed — often a few
# extra seconds; 3 HTTP retries was too few and showed "too long" while credits were already deducted.
_PUBSUB_ITERATIONS = 180
_POLL_MAX_IF_NOTIFIED = 45
_POLL_MAX_IF_NOT_NOTIFIED = 70
_POLL_SLEEP_NOTIFIED = 1.0
_POLL_SLEEP_FALLBACK = 3.0


_GENERIC_FAILED_MESSAGE = "\u274c Не удалось обработать фото. Попробуй ещё раз."


def _user_message_for_failed(error_message: str | None) -> str:
    """Pass the raw worker ``error_message`` through to the user.

    The sanitiser was intentionally removed — during pipeline recovery we
    need the real backend tail (``[stage=...] ExcType: ... http=... code=...
    req=rsid-...``) visible in both UI and chat so ops can diagnose at a
    glance without opening the DB / Railway logs. The fallback is used only
    when the worker wrote nothing at all.
    """
    if not error_message:
        return _GENERIC_FAILED_MESSAGE
    text = error_message.strip()
    if not text:
        return _GENERIC_FAILED_MESSAGE
    if len(text) > 500:
        text = text[:497].rstrip() + "..."
    return f"\u274c {text}"


@router.callback_query(F.data.startswith("pick_style:"))
async def on_pick_style(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Call pre-analyze, show scores + perception profile + style suggestions."""
    kind = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    file_id = await redis.get(PHOTO_KEY.format(user_id))
    if not file_id:
        await callback.answer("Сначала отправь фото!", show_alert=True)
        return

    # P1.1: guard against rapid double-taps on the scenario picker.
    # The LLM pre-analysis is free for the user but billable for us;
    # without the lock two quick clicks fire two parallel requests.
    pre_lock_key = _PRE_ANALYZE_LOCK.format(user_id)
    acquired = await redis.set(
        pre_lock_key, "1", ex=_PRE_ANALYZE_LOCK_TTL, nx=True
    )
    if not acquired:
        await callback.answer(
            "Ещё анализирую предыдущий запрос\u2026", show_alert=True
        )
        return

    await callback.answer()

    if kind not in ("dating", "cv", "social"):
        await redis.delete(pre_lock_key)
        await callback.message.answer(
            "Выбери направление:", reply_markup=scenario_keyboard()
        )
        return

    mode_headers = {
        "dating": "\U0001f495 *Образ для знакомств*",
        "cv": "\U0001f4bc *Профессиональный образ*",
        "social": "\U0001f4f8 *Образ для соцсетей*",
    }
    header = mode_headers.get(kind, "\u2728 *Твой образ*")

    status_msg = await callback.message.answer(
        f"{header}\n\n\U0001f50d Анализирую твоё фото..."
    )

    try:
        pre_analysis = await _call_pre_analyze(
            callback.bot, api_base_url, user_id, file_id, kind, redis
        )

        if pre_analysis is None:
            catalog = STYLE_CATALOG.get(kind, [])
            hooks = [
                f"\u2022 {label} \u2014 {hook}"
                for _key, label, hook, *_rest in catalog[:3]
            ]
            text = (
                f"{header}\n\n"
                "\U0001f680 *Что можно усилить:*\n"
                + "\n".join(hooks)
                + "\n\n*Выбери стиль:*"
            )
            try:
                await status_msg.edit_text(
                    text, parse_mode="Markdown", reply_markup=style_keyboard(kind)
                )
            except Exception:
                await callback.message.answer(
                    text, parse_mode="Markdown", reply_markup=style_keyboard(kind)
                )
            return

        pre_id = pre_analysis.get("pre_analysis_id", "")
        if pre_id:
            await redis.set(PRE_ANALYSIS_REF_KEY.format(user_id), pre_id, ex=1800)

        iq_block = pre_analysis.get("input_quality") or {}
        try:
            ratio = float(iq_block.get("face_area_ratio", 0.0) or 0.0)
        except (TypeError, ValueError):
            ratio = 0.0
        if ratio > 0.0:
            await redis.set(
                FACE_AREA_RATIO_KEY.format(user_id), f"{ratio:.4f}", ex=_FACE_AREA_TTL
            )

        # Composition Safety Layer — persist composition_class so style
        # picking and framing pickers can run their CSL checks without
        # re-querying the backend. Default to ``unknown`` (fail-closed-
        # safe) when the field is missing or malformed.
        composition_class = str(iq_block.get("composition_class") or "unknown")
        await redis.set(
            COMPOSITION_CLASS_KEY.format(user_id),
            composition_class,
            ex=_COMPOSITION_CLASS_TTL,
        )

        text = _format_pre_analysis_message(header, kind, user_id, pre_analysis)

        try:
            await status_msg.edit_text(
                text, parse_mode="Markdown", reply_markup=style_keyboard(kind)
            )
        except Exception:
            await callback.message.answer(
                text, parse_mode="Markdown", reply_markup=style_keyboard(kind)
            )
    finally:
        await redis.delete(pre_lock_key)


@router.callback_query(F.data.startswith("style:"))
async def on_style_selected(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """User picked a style — run the pipeline immediately."""
    parts = callback.data.split(":")
    mode = parts[1]
    style = parts[2] if len(parts) > 2 else ""
    if await _maybe_warn_style_reference_mismatch(callback, redis, mode, style):
        return
    await _submit_analysis(callback, api_base_url, redis, mode, style)


@router.callback_query(F.data.startswith("enhance:"))
async def on_enhancement_choice(
    callback: CallbackQuery, api_base_url: str, redis: Redis
):
    """Legacy alias for :func:`on_variant_request` — kept for one release
    so in-flight messages with old callback data still work. New
    keyboards always emit ``variant:*``.
    """
    parts = callback.data.split(":")
    mode = parts[1] if len(parts) > 1 else ""
    style = parts[2] if len(parts) > 2 else ""
    await _handle_variant_callback(callback, api_base_url, redis, mode, style)


@router.callback_query(F.data.startswith("variant:"))
async def on_variant_request(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Rotate to the next un-seen content variant of the current style.

    For document styles we skip variant resolution and simply rerun the
    same style with a fresh random seed (handled automatically by the
    FAL provider when no explicit seed is set).
    """
    parts = callback.data.split(":")
    mode = parts[1] if len(parts) > 1 else ""
    style = parts[2] if len(parts) > 2 else ""
    await _handle_variant_callback(callback, api_base_url, redis, mode, style)


async def _handle_variant_callback(
    callback: CallbackQuery,
    api_base_url: str,
    redis: Redis,
    mode: str,
    style: str,
) -> None:
    if not mode:
        last = await redis.get(LAST_GEN_KEY.format(callback.from_user.id))
        if last:
            last_s = last.decode() if isinstance(last, bytes) else last
            if ":" in last_s:
                parsed_mode, parsed_style = last_s.split(":", 1)
                mode = mode or parsed_mode
                style = style or parsed_style
    if not mode or not style:
        await callback.answer()
        await callback.message.answer(
            "Выбери направление:",
            reply_markup=scenario_keyboard(),
        )
        return

    if await _maybe_warn_style_reference_mismatch(callback, redis, mode, style):
        return

    variant_id = await _resolve_next_variant_id(
        redis, callback.from_user.id, mode, style
    )

    await _submit_analysis(
        callback,
        api_base_url,
        redis,
        mode,
        style,
        variant_id=variant_id,
    )


async def _resolve_next_variant_id(
    redis: Redis,
    user_id: int,
    mode: str,
    style: str,
) -> str:
    """Pick the next un-seen variant for (mode, style); '' on miss/error.

    Extracted so ``on_confirm_risk`` can reuse the same rotation logic
    when the user flows through the risk-accept path into a variant
    button — otherwise accepting the warning would pin the user to the
    base style forever.
    """
    try:
        from src.prompts.image_gen import STYLE_REGISTRY, is_document_style

        if is_document_style(style):
            return ""
        spec = STYLE_REGISTRY.get(mode, style)
        if spec is None or not spec.variants:
            return ""
        from src.services.variation import resolve_next_variant

        chosen = await resolve_next_variant(
            redis,
            spec,
            user_id,
            mode,
            style,
        )
        return chosen.id if chosen is not None else ""
    except Exception:
        logger.exception("variant resolve failed for %s:%s", mode, style)
        return ""


@router.callback_query(F.data.startswith("confirm_risk:"))
async def on_confirm_risk(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """User explicitly accepted the style × reference mismatch risk.

    Two post-conditions are needed here for the "Другой вариант" UX to
    work after the accept:

    1. Remember the accept in Redis so subsequent ``variant:*`` /
       ``style:*`` clicks for this ``(user, mode, style)`` do NOT
       re-trigger the warning. Without this, every variant rotation
       would repaint the warning keyboard and stall the flow (the
       v1.15 "Повторно улучшение отказывается делать" bug).
    2. Propagate the variant rotation on this first post-accept run
       too, so the user does not get the identical base variant twice
       after tapping through the warning.
    """
    parts = callback.data.split(":")
    mode = parts[1] if len(parts) > 1 else ""
    style = parts[2] if len(parts) > 2 else ""
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if mode and style:
        try:
            await redis.sadd(
                RISK_ACCEPTED_KEY.format(callback.from_user.id),
                f"{mode}:{style}",
            )
            await redis.expire(
                RISK_ACCEPTED_KEY.format(callback.from_user.id),
                _RISK_ACCEPTED_TTL,
            )
        except Exception:
            logger.exception(
                "risk_accepted cache write failed for user %s", callback.from_user.id
            )
    variant_id = await _resolve_next_variant_id(
        redis,
        callback.from_user.id,
        mode,
        style,
    )
    await _submit_analysis(
        callback,
        api_base_url,
        redis,
        mode,
        style,
        variant_id=variant_id,
    )


# Composition Safety Layer — Phase 3 advanced override callback.
#
# Two-step opt-in so a stray double-tap can't bypass the policy: the
# first click shows an explicit "this can produce anatomically wrong
# bodies" warning + a confirmation button; the second click flips
# ``COMPOSITION_OVERRIDE_KEY`` to ``1`` in Redis and re-enters
# ``_submit_analysis`` with ``skip_composition_safety=True``.
# ``_submit_analysis`` reads the flag and forwards it as a form field
# on the /analyze call (or via task_context for the edge proxy path).
COMPOSITION_OVERRIDE_KEY = "ratemeai:composition_override:{}"
_COMPOSITION_OVERRIDE_TTL = 600


@router.callback_query(F.data.startswith("override_csl:"))
async def on_override_csl(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """First click on the CSL override button — show the confirmation prompt."""
    if not bool(getattr(settings, "composition_safety_advanced_override", False)):
        await callback.answer(
            "Эта функция временно отключена.",
            show_alert=True,
        )
        return

    parts = callback.data.split(":")
    mode = parts[1] if len(parts) > 1 else ""
    style = parts[2] if len(parts) > 2 else ""
    if not mode or not style:
        await callback.answer()
        return

    await callback.answer()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\u2705 Понял, всё равно сгенерировать",
                    callback_data=f"override_csl_go:{mode}:{style}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="\u21a9 Назад",
                    callback_data="reupload_photo",
                )
            ],
        ]
    )
    await callback.message.answer(
        "\u26a0\ufe0f *Расширенные настройки*\n\n"
        "Генерация тела с крупного портрета может привести к "
        "нереалистичным пропорциям и анатомическим ошибкам — "
        "лицо может «прилипнуть» к чужим плечам.\n\n"
        "Если уверены, что хотите попробовать — нажмите ниже.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("override_csl_go:"))
async def on_override_csl_go(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Second click — set the override flag and submit the analysis."""
    if not bool(getattr(settings, "composition_safety_advanced_override", False)):
        await callback.answer(
            "Эта функция временно отключена.",
            show_alert=True,
        )
        return

    parts = callback.data.split(":")
    mode = parts[1] if len(parts) > 1 else ""
    style = parts[2] if len(parts) > 2 else ""
    if not mode or not style:
        await callback.answer()
        return

    user_id = callback.from_user.id
    try:
        await redis.set(
            COMPOSITION_OVERRIDE_KEY.format(user_id),
            "1",
            ex=_COMPOSITION_OVERRIDE_TTL,
        )
    except Exception:
        logger.exception("CSL override: failed to write flag for user %s", user_id)

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _submit_analysis(callback, api_base_url, redis, mode, style)


@router.callback_query(F.data == "reupload_photo")
async def on_reupload_photo(callback: CallbackQuery, redis: Redis):
    """User chose to reupload photo — clear cached photo + pre-analysis."""
    user_id = callback.from_user.id
    await redis.delete(
        PHOTO_KEY.format(user_id),
        PRE_ANALYSIS_REF_KEY.format(user_id),
        FACE_AREA_RATIO_KEY.format(user_id),
        RISK_ACCEPTED_KEY.format(user_id),
        COMPOSITION_CLASS_KEY.format(user_id),
        COMPOSITION_OVERRIDE_KEY.format(user_id),
    )
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "\U0001f4f7 Отправь новое фото — лучше, чтобы были видны плечи и корпус."
    )


@router.callback_query(F.data == "accept_risky_result")
async def on_accept_risky_result(callback: CallbackQuery):
    """User accepted a low-similarity result — just dismiss the prompt."""
    await callback.answer("Хорошо, оставили как есть")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def _maybe_warn_style_reference_mismatch(
    callback: CallbackQuery,
    redis: Redis,
    mode: str,
    style: str,
) -> bool:
    """Show a warning keyboard if the chosen style requires visible body but
    the reference is a tight head-crop. Returns True when the user was
    prompted (caller must stop; continuation happens via `confirm_risk:`).

    Never re-shows the warning if the user already accepted the risk
    for the same ``(mode, style)`` on the current photo — that path
    lives behind the Redis set at ``RISK_ACCEPTED_KEY``. Uploading a
    new photo drops the set (see :func:`on_reupload_photo`).
    """
    if not mode or not style:
        return False

    user_id = callback.from_user.id

    try:
        already_accepted = await redis.sismember(
            RISK_ACCEPTED_KEY.format(user_id),
            f"{mode}:{style}",
        )
    except Exception:
        already_accepted = False
    if already_accepted:
        return False

    raw = await redis.get(FACE_AREA_RATIO_KEY.format(user_id))
    try:
        ratio = float(raw.decode() if isinstance(raw, bytes) else raw) if raw else 0.0
    except (TypeError, ValueError):
        ratio = 0.0

    # Composition Safety Layer — fold the cached composition_class into
    # the compatibility check. A FACE_CLOSEUP × needs_full_body pairing
    # now returns a ``block``-severity issue (STYLE_FORBIDDEN_FOR_COMPOSITION)
    # which we surface without a "продолжить с риском" escape — the user
    # must reupload (Phase 3 will add an explicit advanced-override
    # entry behind a feature flag).
    composition_class = await _read_composition_class(redis, user_id)
    issue = check_style_reference_compat(
        ratio, mode, style, composition_class=composition_class
    )
    if issue is None:
        return False

    await callback.answer()
    keyboard_rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="\U0001f4f7 Загрузить другое фото",
                callback_data="reupload_photo",
            )
        ],
    ]
    # Only soft warnings get a "продолжить с риском" affordance. Hard
    # blocks (CSL: ``style_forbidden_for_composition``) refuse to let
    # the user bypass the policy from the bot UI — that path will move
    # to the advanced-override keyboard once Phase 3 ships behind
    # ``settings.composition_safety_advanced_override``.
    is_block = issue.severity == "block"
    if not is_block:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text="\u26a0\ufe0f Продолжить с риском",
                    callback_data=f"confirm_risk:{mode}:{style}",
                )
            ]
        )
    if is_block and bool(
        getattr(settings, "composition_safety_advanced_override", False)
    ):
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text="\u26a0\ufe0f Расширенные настройки",
                    callback_data=f"override_csl:{mode}:{style}",
                )
            ]
        )
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    text = (
        f"\u26a0\ufe0f *{issue.message}*\n\n"
        f"{issue.suggestion}\n\n"
        "Для таких стилей нужно фото, где видно плечи и корпус — "
        "иначе модель сама дорисует тело и сходство может снизиться."
    )
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=keyboard)
    return True


@router.callback_query(F.data.startswith("mode:"))
async def on_mode_selected(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Legacy: direct mode selection (for /rating command flow)."""
    mode = callback.data.split(":", 1)[1]
    await _submit_analysis(callback, api_base_url, redis, mode, "")


@router.callback_query(F.data.startswith("restyle:"))
async def on_restyle(callback: CallbackQuery, redis: Redis):
    """Show style keyboard for current mode."""
    mode = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    file_id = await redis.get(PHOTO_KEY.format(user_id))
    if not file_id:
        await callback.answer(
            "Фото больше не доступно. Отправь новое!", show_alert=True
        )
        return

    # P1.1: debounce rapid double-taps that otherwise spam edit_reply_markup.
    nav_lock = _UI_NAV_LOCK.format(user_id)
    if not await redis.set(nav_lock, "1", ex=_UI_NAV_LOCK_TTL, nx=True):
        await callback.answer()
        return

    await callback.answer()
    mode_headers = {
        "dating": "\U0001f495 Выбери образ:",
        "cv": "\U0001f4bc Выбери образ:",
        "social": "\U0001f4f8 Выбери образ:",
    }
    header = mode_headers.get(mode)
    if header:
        await callback.message.answer(header, reply_markup=style_keyboard(mode))
    else:
        await callback.message.answer(
            "Выбери направление:", reply_markup=scenario_keyboard()
        )


@router.callback_query(F.data.startswith("styles_page:"))
async def on_styles_page(callback: CallbackQuery, redis: Redis):
    """Paginate through style options."""
    parts = callback.data.split(":")
    mode = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    user_id = callback.from_user.id

    nav_lock = _UI_NAV_LOCK.format(user_id)
    if not await redis.set(nav_lock, "1", ex=_UI_NAV_LOCK_TTL, nx=True):
        await callback.answer()
        return

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(
            reply_markup=style_keyboard(mode, page)
        )
    except Exception:
        await callback.message.answer(
            "Выбери стиль:", reply_markup=style_keyboard(mode, page)
        )


@router.callback_query(F.data == "retry")
async def on_retry(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Retry last generation using stored context."""
    user_id = callback.from_user.id
    file_id = await redis.get(PHOTO_KEY.format(user_id))
    if not file_id:
        await callback.answer(
            "Фото больше не доступно. Отправь новое!", show_alert=True
        )
        return
    last = await redis.get(LAST_GEN_KEY.format(user_id))
    if last and ":" in last:
        mode, style = last.split(":", 1)
    else:
        await callback.answer()
        await callback.message.answer(
            "Выбери направление:", reply_markup=scenario_keyboard()
        )
        return
    await _submit_analysis(callback, api_base_url, redis, mode, style)


async def _get_api_headers(
    redis: Redis, user_id: int, api_url: str, user=None
) -> dict[str, str]:
    """Return auth headers for the Railway API the bot calls.

    Since 1.62.0 the bot runs only on Railway, so there is no
    cross-region session juggling — we always reuse the standard
    bot auth headers from :func:`get_bot_auth_headers`.
    """
    return await get_bot_auth_headers(redis, user_id)


async def _refresh_api_headers(
    redis: Redis, user_id: int, api_url: str, user=None
) -> dict[str, str]:
    """Force-refresh auth headers (delete cached session, obtain new one)."""
    from src.bot.middleware import _BOT_SESSION_KEY

    await redis.delete(_BOT_SESSION_KEY.format(user_id))
    return await get_bot_auth_headers(redis, user_id)


async def _call_pre_analyze(
    bot, api_base_url: str, user_id: int, file_id: str, mode: str, redis: Redis
) -> dict | None:
    """Download the user's photo and call POST /api/v1/pre-analyze. Returns response dict or None on failure."""
    try:
        if isinstance(file_id, bytes):
            file_id = file_id.decode()
        file_obj = await bot.get_file(file_id)
        file_bytes = io.BytesIO()
        await bot.download_file(file_obj.file_path, file_bytes)
        file_bytes.seek(0)
        image_data = file_bytes.read()

        headers = await _get_api_headers(redis, user_id, api_base_url)
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{api_base_url}/api/v1/pre-analyze",
                files={"image": ("photo.jpg", image_data, "image/jpeg")},
                data={"mode": mode},
                headers=headers,
            )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 401:
            headers = await _refresh_api_headers(redis, user_id, api_base_url)
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{api_base_url}/api/v1/pre-analyze",
                    files={"image": ("photo.jpg", image_data, "image/jpeg")},
                    data={"mode": mode},
                    headers=headers,
                )
            if resp.status_code == 200:
                return resp.json()
        logger.warning("pre-analyze returned %s: %s", resp.status_code, resp.text[:200])
    except Exception:
        logger.exception("pre-analyze call failed for user %s", user_id)
    return None


def _format_pre_analysis_message(
    header: str, kind: str, user_id: int, data: dict
) -> str:
    """Format the pre-analysis scores + suggestions into a Telegram message."""
    first_impression = sanitize_llm_text(data.get("first_impression", ""), max_len=600)
    score = data.get("score", 0)
    ps = data.get("perception_scores", {})

    lines = [header]
    if first_impression:
        lines.append(first_impression)
    lines.append("")
    lines.append(f"\U0001f4ca *Твой скор: {score:.2f} / 10*")
    lines.append("")

    warmth = ps.get("warmth", 0)
    presence = ps.get("presence", 0)
    appeal = ps.get("appeal", 0)
    lines.append("*Профиль восприятия:*")
    lines.append(
        f"\u2600\ufe0f Теплота: {warmth:.2f} \u2022 "
        f"\u26a1 Уверенность: {presence:.2f} \u2022 "
        f"\u2728 Привлекательность: {appeal:.2f}"
    )

    opportunities = data.get("enhancement_opportunities", [])
    if opportunities:
        lines.append("")
        lines.append("\U0001f4a1 *Рекомендации:*")
        for opp in opportunities[:3]:
            clean_opp = sanitize_llm_text(opp, max_len=200)
            if clean_opp:
                lines.append(f"\u2022 {clean_opp}")

    preview = build_enhancement_preview(kind, user_id, depth=1, count=3)
    if preview.suggestions:
        lines.append("")
        lines.append("\U0001f680 *Как усилить:*")
        for s in preview.suggestions[:3]:
            clean_line = sanitize_llm_text(s.line, max_len=200)
            if clean_line:
                lines.append(f"\u2022 {clean_line}")

    lines.append("")
    lines.append("*Выбери стиль:*")
    return "\n".join(lines)


async def _submit_analysis(
    callback: CallbackQuery,
    api_base_url: str,
    redis: Redis,
    mode: str,
    style: str,
    *,
    variant_id: str = "",
):
    user_id = callback.from_user.id
    bot = callback.bot
    analyze_api = api_base_url

    file_id = await redis.get(PHOTO_KEY.format(user_id))
    if not file_id:
        await callback.answer("Сначала отправь фото!", show_alert=True)
        return

    lock_key = _PROCESSING_LOCK.format(user_id)
    acquired = await redis.set(lock_key, "1", ex=_LOCK_TTL, nx=True)
    if not acquired:
        await callback.answer(
            "\u23f3 Предыдущий запрос ещё обрабатывается...", show_alert=True
        )
        return

    await callback.answer()

    depth = await _get_depth(redis, user_id, mode)
    if depth > 1:
        status_text = (
            f"\u23f3 Усиливаю образ (уровень {depth})\u2026 Это может занять до минуты."
        )
    else:
        status_text = "\u23f3 Улучшаю твой образ\u2026 Это может занять до минуты."
    status_msg = await callback.message.answer(status_text)

    await redis.set(LAST_GEN_KEY.format(user_id), f"{mode}:{style}", ex=86400)
    if style:
        used_key = USED_STYLES_KEY.format(user_id, mode)
        await redis.sadd(used_key, style)
        await redis.expire(used_key, 86400)
    await _increment_depth(redis, user_id, mode)

    try:
        file = await bot.get_file(file_id)
        file_bytes = io.BytesIO()
        await bot.download_file(file.file_path, file_bytes)
        file_bytes.seek(0)
        image_data = file_bytes.read()

        from src.orchestrator.enhancement_matrix import level_for_depth

        # ``enhancement_level`` only changes the image prompt directly for
        # ``emoji`` (via ``ENHANCEMENT_LEVEL_MODIFIERS`` in
        # ``src/prompts/image_gen.py``). For photo modes it travels into
        # the LLM analysis builder and perturbs ``base_description``
        # unpredictably on each repeat — that is one of the regressions
        # that started showing up after the A/B cutover, since the
        # downstream pipeline no longer absorbs prompt drift the way
        # PuLID + CodeFormer did. Web pins it to ``1`` for photo
        # generations; mirror that here and keep the depth-based ladder
        # only for emoji where it actually affects the prompt template.
        if mode == "emoji":
            enh_level = level_for_depth(depth).level
        else:
            enh_level = 1

        # Telegram has no "ракурс" picker, so without these two fields the
        # executor falls back to ``framing='half_body'`` (see
        # ``src/orchestrator/executor.py``) which clashes with the tight
        # Telegram preview reference. We pick framing from the StyleSpec
        # exactly the same way the web modal does and forward it both as
        # the top-level form field (kept for analytics + edge fan-out)
        # and inside ``input_hints`` (where ``executor.single_pass``
        # reads it via ``modal_framing``).
        framing = await _framing_for_style(mode, style, redis=redis, user_id=user_id)
        input_hints_payload = {"framing": framing}

        # Image model + quality: omit ``image_model`` so ``/analyze`` applies
        # the same ``apply_ab_test_context_fields`` defaults as anonymous web
        # clients (`settings.ab_default_model`, server-locked ``medium`` tier).
        # Tag the task for analytics; generation policy is channel-agnostic
        # (`allow_cross_model_image_fallback` on settings).
        import json as _json

        form_data = {
            "mode": mode,
            "enhancement_level": str(enh_level),
            "source": "telegram_bot",
            "framing": framing,
            "input_hints": _json.dumps(input_hints_payload, separators=(",", ":")),
        }
        if style:
            form_data["style"] = style
        if variant_id:
            form_data["variant_id"] = variant_id

        pre_id = await redis.get(PRE_ANALYSIS_REF_KEY.format(user_id))
        if pre_id:
            if isinstance(pre_id, bytes):
                pre_id = pre_id.decode()
            form_data["pre_analysis_id"] = pre_id

        # Composition Safety Layer override — forward the one-shot flag
        # left by ``on_override_csl_go``. The API ignores it unless the
        # deployment opted in via ``composition_safety_advanced_override``;
        # we always send it as a string so FastAPI's bool parser accepts
        # both "true"/"false" and 1/0 consistently.
        try:
            override_flag = await redis.get(
                COMPOSITION_OVERRIDE_KEY.format(user_id)
            )
        except Exception:
            override_flag = None
        if override_flag:
            form_data["skip_composition_safety"] = "true"
            try:
                await redis.delete(COMPOSITION_OVERRIDE_KEY.format(user_id))
            except Exception:
                pass

        auth_headers = await _get_api_headers(
            redis, user_id, analyze_api, callback.from_user
        )
        # v1.24.2: 120 s aligned with ``fal_request_timeout`` (see
        # src/config.py). The old 30 s budget was below the wall-clock
        # envelope of a real A/B generation (FAL queue wait + Nano
        # Banana 2 / GPT Image 2 inference at ``medium``/``high`` + our
        # post-pipeline), so the bot's POST was being cut off on
        # healthy runs and the status bubble froze with no result.
        _ANALYZE_TIMEOUT = 120.0
        async with httpx.AsyncClient(timeout=_ANALYZE_TIMEOUT) as client:
            resp = await client.post(
                f"{analyze_api}/api/v1/analyze",
                files={"image": ("photo.jpg", image_data, "image/jpeg")},
                data=form_data,
                headers=auth_headers,
            )

        if resp.status_code == 401:
            auth_headers = await _refresh_api_headers(
                redis, user_id, analyze_api, callback.from_user
            )
            file_bytes_retry = io.BytesIO(image_data)
            async with httpx.AsyncClient(timeout=_ANALYZE_TIMEOUT) as client:
                resp = await client.post(
                    f"{analyze_api}/api/v1/analyze",
                    files={
                        "image": ("photo.jpg", file_bytes_retry.read(), "image/jpeg")
                    },
                    data=form_data,
                    headers=auth_headers,
                )

        def _safe_json(r: httpx.Response) -> dict:
            """Parse JSON from response, returning an empty dict if body is non-JSON
            (например, HTML-страница 502/504 от edge-прокси во время рестарта).
            """
            ct = (r.headers.get("content-type") or "").lower()
            if "application/json" not in ct:
                logger.warning(
                    "Non-JSON response from %s: status=%s content-type=%s body[:500]=%r",
                    r.request.url if r.request else "?",
                    r.status_code,
                    ct,
                    r.text[:500],
                )
                return {}
            try:
                return r.json()
            except ValueError:
                logger.warning(
                    "Failed to parse JSON from %s: status=%s body[:500]=%r",
                    r.request.url if r.request else "?",
                    r.status_code,
                    r.text[:500],
                )
                return {}

        # У бота стоит default parse_mode=Markdown. Любой детейл от бэкенда,
        # содержащий `_`, `*`, `[`, `]`, `` ` `` и т.п., превращает текст в
        # невалидный Markdown и Telegram отвечает
        # «can't parse entities: Can't find end of the entity …» — мы падаем
        # в generic except и пользователь видит «Произошла ошибка».
        # Поэтому все статусные сообщения шлём с parse_mode=None.
        _NO_CREDITS_DETAILS = {"no_credits", "credits_exhausted", "quota_exceeded"}

        def _human_402(detail: str) -> str:
            if not detail or detail.strip().lower() in _NO_CREDITS_DETAILS:
                return "Недостаточно кредитов. Пополни баланс и попробуй снова."
            return detail

        if resp.status_code == 202:
            task_data = _safe_json(resp)
            task_id = task_data.get("task_id") if task_data else None
            if not task_id:
                await redis.delete(lock_key)
                await status_msg.edit_text(
                    "\u274c Сервер не вернул идентификатор задачи. Попробуй ещё раз.",
                    reply_markup=error_keyboard(),
                    parse_mode=None,
                )
                return

            if not hasattr(bot, "_pending_tasks"):
                bot._pending_tasks = {}
            bot._pending_tasks[user_id] = {
                "task_id": task_id,
                "chat_id": callback.message.chat.id,
                "status_msg_id": status_msg.message_id,
            }

            import asyncio

            asyncio.create_task(
                _poll_task(
                    bot,
                    analyze_api,
                    user_id,
                    task_id,
                    callback.message.chat.id,
                    status_msg.message_id,
                    redis,
                )
            )

        elif resp.status_code == 429:
            await redis.delete(lock_key)
            await status_msg.edit_text(
                "\u26a0\ufe0f Слишком много запросов. Попробуй через минуту.",
                reply_markup=error_keyboard(),
                parse_mode=None,
            )
        elif resp.status_code == 402:
            await redis.delete(lock_key)
            raw_detail = _safe_json(resp).get("detail") or ""
            await status_msg.edit_text(
                f"\u274c {_human_402(raw_detail)}",
                reply_markup=error_keyboard(),
                parse_mode=None,
            )
        else:
            await redis.delete(lock_key)
            detail = _safe_json(resp).get("detail") or f"HTTP {resp.status_code}"
            logger.warning(
                "Analyze failed for user %s: status=%s detail=%s",
                user_id,
                resp.status_code,
                detail,
            )
            await status_msg.edit_text(
                f"\u274c Ошибка: {detail}",
                reply_markup=error_keyboard(),
                parse_mode=None,
            )

    except httpx.TimeoutException:
        await redis.delete(lock_key)
        logger.warning("Analyze timeout for user %s", user_id, exc_info=True)
        await status_msg.edit_text(
            "\u274c Сервис долго отвечает. Попробуй ещё раз через минуту.",
            reply_markup=error_keyboard(),
            parse_mode=None,
        )
    except httpx.HTTPError as e:
        await redis.delete(lock_key)
        logger.warning(
            "Analyze network error for user %s: %s", user_id, e, exc_info=True
        )
        await status_msg.edit_text(
            "\u274c Проблема с подключением к сервису. Попробуй ещё раз.",
            reply_markup=error_keyboard(),
            parse_mode=None,
        )
    except Exception:
        await redis.delete(lock_key)
        logger.exception("Failed to submit analysis for user %s", user_id)
        await status_msg.edit_text(
            "\u274c Произошла ошибка. Попробуй позже.",
            reply_markup=error_keyboard(),
            parse_mode=None,
        )


# 1.62.0 — RUB/USD pack-callbacks were removed from the bot.  All
# Telegram-side purchases now go through Telegram Stars (XTR) — see
# ``src/bot/handlers/stars.py``.  The web client keeps ЮKassa (RUB)
# and Xsolla (USD) flows for browser users.


@router.callback_query(F.data == "balance")
async def on_balance(callback: CallbackQuery, api_base_url: str, redis: Redis):
    """Show user's current credit balance (from edge server where payments are processed)."""
    await callback.answer()
    user_id = callback.from_user.id
    payment_api = api_base_url

    try:
        headers = await _get_api_headers(
            redis, user_id, payment_api, callback.from_user
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{payment_api}/api/v1/payments/balance",
                headers=headers,
            )

        if resp.status_code == 401:
            headers = await _refresh_api_headers(
                redis, user_id, payment_api, callback.from_user
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{payment_api}/api/v1/payments/balance",
                    headers=headers,
                )

        if resp.status_code == 200:
            data = resp.json()
            credits = data.get("image_credits", 0)
            text = f"\U0001f4b0 *Твой баланс*\n\nДоступно образов: *{credits}*\n\n"
            if credits == 0:
                text += "Открой новые образы и стили!"
                from src.bot.keyboards import upgrade_keyboard

                await callback.message.answer(
                    text, parse_mode="Markdown", reply_markup=upgrade_keyboard()
                )
            else:
                text += "Отправь фото для улучшения образа!"
                await callback.message.answer(
                    text, parse_mode="Markdown", reply_markup=back_keyboard()
                )
        else:
            await callback.message.answer(
                "\u274c Не удалось получить баланс.", reply_markup=error_keyboard()
            )
    except Exception:
        logger.exception("Failed to fetch balance for user %s", user_id)
        await callback.message.answer(
            "\u274c Ошибка. Попробуй позже.", reply_markup=error_keyboard()
        )


@router.callback_query(F.data == "topup")
async def on_topup(callback: CallbackQuery):
    """Show available credit packs for purchase."""
    await callback.answer()
    from src.bot.keyboards import upgrade_keyboard

    await callback.message.answer(
        "\U0001f6d2 *Пополнить баланс*\n\nВыбери подходящий пакет образов:",
        parse_mode="Markdown",
        reply_markup=upgrade_keyboard(),
    )


@router.callback_query(F.data == "new_photo")
async def on_new_photo(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "\U0001f4f8 Отправь мне новое фото!", reply_markup=back_keyboard()
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


# 1.62.0 — _resolve_user_id / _ensure_edge_session / _ensure_primary_session
# / _force_refresh_* / _EDGE_SESSION_KEY / _PRIMARY_SESSION_KEY helpers were
# removed.  They existed only to bridge bot → RU edge and bot → primary
# Xsolla flows.  The single bot now lives on Railway and uses the standard
# bot session token from :func:`get_bot_auth_headers` (see ``_get_api_headers``).


# ------------------------------------------------------------------
# Depth tracking
# ------------------------------------------------------------------


async def _get_depth(redis: Redis, user_id: int, mode: str) -> int:
    key = DEPTH_KEY.format(user_id, mode)
    val = await redis.get(key)
    return int(val) if val else 1


async def _increment_depth(redis: Redis, user_id: int, mode: str) -> int:
    key = DEPTH_KEY.format(user_id, mode)
    new_val = await redis.incr(key)
    await redis.expire(key, 86400)
    return new_val


# ------------------------------------------------------------------
# Progress streaming
# ------------------------------------------------------------------


async def _update_progress(bot, chat_id: int, status_msg_id: int, data_str: str):
    """Update the status message with step progress."""
    try:
        parts = data_str.split(":")
        step_raw = parts[0] if parts else ""
        current = int(parts[1]) if len(parts) > 1 else 0
        total = int(parts[2]) if len(parts) > 2 else 0

        step_name = (
            step_raw.split("_", 2)[-1] if step_raw.startswith("step_") else step_raw
        )
        label = _STEP_LABELS.get(step_name, f"Шаг {current}...")
        bar = "\u2593" * current + "\u2591" * (total - current)
        text = f"\u23f3 {label}\n[{bar}] {current}/{total}"

        await bot.edit_message_text(text, chat_id=chat_id, message_id=status_msg_id)
    except Exception:
        pass


_STEP_LABELS: dict[str, str] = {
    "background_edit": "Работаю над окружением\u2026",
    "lighting_adjust": "Улучшаю освещение\u2026",
    "clothing_edit": "Подбираю стиль одежды\u2026",
    "expression_hint": "Работаю с выражением\u2026",
    "skin_correction": "Сохраняю идентичность\u2026",
    "style_overall": "Финализация образа\u2026",
    "preprocess": "Анализ черт лица\u2026",
    "analyze": "Подбираю улучшения\u2026",
    "identity": "Сохраняю идентичность\u2026",
}


# ------------------------------------------------------------------
# Task polling
# ------------------------------------------------------------------


async def _poll_task(
    bot,
    api_base_url: str,
    user_id: int,
    task_id: str,
    chat_id: int,
    status_msg_id: int,
    redis: Redis,
):
    """Wait for task via Redis Pub/Sub, with HTTP polling fallback."""
    import asyncio
    from src.bot.handlers.results import deliver_result

    lock_key = _PROCESSING_LOCK.format(user_id)

    done_channel = f"ratemeai:task_done:{task_id}"
    progress_channel = f"ratemeai:progress:{task_id}"
    notified = False

    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(done_channel, progress_channel)
        try:
            for _ in range(_PUBSUB_ITERATIONS):
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if msg and msg.get("type") == "message":
                    ch = msg.get("channel", "")
                    if isinstance(ch, bytes):
                        ch = ch.decode()
                    if ch == done_channel:
                        notified = True
                        break
                    if ch == progress_channel:
                        data_str = msg.get("data", "")
                        if isinstance(data_str, bytes):
                            data_str = data_str.decode()
                        await _update_progress(bot, chat_id, status_msg_id, data_str)
        finally:
            await pubsub.unsubscribe(done_channel, progress_channel)
            await pubsub.close()
    except Exception:
        logger.warning("Pub/Sub failed for task %s, falling back to polling", task_id)

    _poll_auth_refreshed = False

    async def _fetch_task_status():
        nonlocal _poll_auth_refreshed
        auth_headers = await _get_api_headers(redis, user_id, api_base_url)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{api_base_url}/api/v1/tasks/{task_id}",
                headers=auth_headers,
            )
            if resp.status_code == 401 and not _poll_auth_refreshed:
                _poll_auth_refreshed = True
                auth_headers = await _refresh_api_headers(redis, user_id, api_base_url)
                resp = await client.get(
                    f"{api_base_url}/api/v1/tasks/{task_id}",
                    headers=auth_headers,
                )
            if resp.status_code != 200:
                return None
            return resp.json()

    max_polls = _POLL_MAX_IF_NOTIFIED if notified else _POLL_MAX_IF_NOT_NOTIFIED
    sleep_interval = _POLL_SLEEP_NOTIFIED if notified else _POLL_SLEEP_FALLBACK

    last_status: str | None = None
    for attempt in range(max_polls):
        if not notified:
            await asyncio.sleep(sleep_interval)
        try:
            data = await _fetch_task_status()
            if data is None:
                if notified:
                    await asyncio.sleep(_POLL_SLEEP_NOTIFIED)
                continue

            status = data.get("status")
            if status is not None:
                last_status = status

            if status == "completed":
                await redis.delete(lock_key)
                await deliver_result(
                    bot,
                    chat_id,
                    status_msg_id,
                    data,
                    user_id,
                    redis,
                    api_base_url=api_base_url,
                )
                return
            if status == "failed":
                await redis.delete(lock_key)
                err_msg = data.get("error_message") or ""
                logger.warning(
                    "Task %s failed (user=%s) error_message=%s",
                    task_id,
                    user_id,
                    err_msg,
                )
                await bot.edit_message_text(
                    _user_message_for_failed(err_msg),
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    reply_markup=error_keyboard(),
                )
                return

        except Exception:
            logger.exception("Poll error for task %s", task_id)

        if notified:
            await asyncio.sleep(_POLL_SLEEP_NOTIFIED)

    # Grace window: task may commit to DB right after last poll (race with worker).
    for _ in range(3):
        await asyncio.sleep(2.0)
        try:
            data = await _fetch_task_status()
            if data and data.get("status") is not None:
                last_status = data.get("status")
            if data and data.get("status") == "completed":
                await redis.delete(lock_key)
                await deliver_result(
                    bot,
                    chat_id,
                    status_msg_id,
                    data,
                    user_id,
                    redis,
                    api_base_url=api_base_url,
                )
                return
            if data and data.get("status") == "failed":
                await redis.delete(lock_key)
                err_msg = data.get("error_message") or ""
                logger.warning(
                    "Task %s failed during grace window (user=%s) error_message=%s",
                    task_id,
                    user_id,
                    err_msg,
                )
                await bot.edit_message_text(
                    _user_message_for_failed(err_msg),
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    reply_markup=error_keyboard(),
                )
                return
        except Exception:
            logger.exception("Grace poll error for task %s", task_id)

    logger.warning(
        "Task poll timeout task_id=%s user_id=%s last_status=%s redis_notified=%s",
        task_id,
        user_id,
        last_status,
        notified,
    )
    await redis.delete(lock_key)
    await bot.edit_message_text(
        "\u23f0 Обработка занимает слишком долго. Попробуй позже или проверь /balance — "
        "результат мог прийти с задержкой.",
        chat_id=chat_id,
        message_id=status_msg_id,
        reply_markup=error_keyboard(),
    )

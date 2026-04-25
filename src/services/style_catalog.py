"""Shared style catalog — single source of truth for bot keyboards + web API.

Historically this module shipped a hardcoded ``STYLE_CATALOG`` dict-literal
(~850 lines) that drove every Telegram-bot keyboard. The web API and the
admin panel already loaded styles from ``data/styles.json`` via
:func:`src.services.style_loader.load_styles_from_json`, so the bot's
hardcoded copy turned into a parallel source of truth — admin edits were
invisible to the bot until the next deploy.

To unify the two catalogs we expose ``STYLE_CATALOG`` as a thin
:class:`_BotCatalogProxy` that builds the historical
``dict[mode, list[(key, label, hook, meta)]]`` shape on demand from the
JSON file. The proxy:

* keeps the same external API (``.get(mode, [])``, ``.items()``,
  ``[mode]``, ``in``) so existing callers — ``src/bot/keyboards.py``,
  ``src/bot/handlers/mode_select.py``, ``src/services/enhancement_advisor.py``
  — continue to work without changes,
* caches the assembled ``dict`` until :func:`_invalidate` is called from
  :func:`src.services.style_store.invalidate_caches` (which the admin
  ``POST /styles`` and ``POST /styles/reload`` endpoints already trigger),
* skips scenario-only entries (``scenario`` field set or legacy
  ``is_scenario_only`` flag) so the bot keyboards stay scoped to the
  three primary modes.

The standalone ``get_catalog_json*`` / ``get_scenario_styles_json*`` /
``get_style_options*`` helpers are unchanged — they already read from
``data/styles.json`` and serve the web API directly.
"""

from __future__ import annotations

from typing import Iterable

_BotCatalogEntry = tuple[str, str, str, dict]


def _is_scenario_only(entry: dict) -> bool:
    """Whether the style is bound to a specific scenario page.

    A style is excluded from the main mode catalog when either:
    - the legacy boolean ``is_scenario_only`` is set, OR
    - the new ``scenario`` field has a non-empty string value.

    The new field is preferred — it tells the scenario endpoint which
    bucket the style belongs to. The boolean stays around for the
    handful of entries that still rely on it.
    """
    if entry.get("scenario"):
        return True
    return bool(entry.get("is_scenario_only", False))


class _BotCatalogProxy:
    """dict-like view over ``data/styles.json`` for bot keyboards.

    Returns tuples in the same shape the bot consumed historically:
    ``(key, label, hook, meta)`` — so :mod:`src.bot.keyboards`,
    :mod:`src.bot.handlers.mode_select`, and
    :mod:`src.services.enhancement_advisor` keep working without an API
    change.

    The proxy memoises the assembled mapping on first access and is
    invalidated explicitly by :func:`src.services.style_store.invalidate_caches`
    via :meth:`_invalidate`. It does NOT try to detect external file
    edits on its own — every legitimate write path already routes
    through ``style_store`` which calls ``invalidate_caches``.
    """

    def __init__(self) -> None:
        self._cache: dict[str, list[_BotCatalogEntry]] | None = None

    def _build(self) -> dict[str, list[_BotCatalogEntry]]:
        from src.services.style_loader import load_styles_from_json

        out: dict[str, list[_BotCatalogEntry]] = {}
        for s in load_styles_from_json():
            if _is_scenario_only(s):
                continue
            mode = s.get("mode")
            if not mode:
                continue
            out.setdefault(mode, []).append(
                (
                    s["id"],
                    s.get("display_label", s["id"]),
                    s.get("hook_text", ""),
                    s.get("meta", {}) or {},
                )
            )
        return out

    def _ensure(self) -> dict[str, list[_BotCatalogEntry]]:
        if self._cache is None:
            self._cache = self._build()
        return self._cache

    def _invalidate(self) -> None:
        """Drop the memoised mapping; next access rebuilds from disk."""
        self._cache = None

    # ---- dict-like surface ------------------------------------------------

    def get(
        self, mode: str, default: list[_BotCatalogEntry] | None = None
    ) -> list[_BotCatalogEntry]:
        return self._ensure().get(mode, default if default is not None else [])

    def __getitem__(self, mode: str) -> list[_BotCatalogEntry]:
        return self._ensure()[mode]

    def __contains__(self, mode: object) -> bool:
        return mode in self._ensure()

    def __iter__(self) -> Iterable[str]:
        return iter(self._ensure())

    def __len__(self) -> int:
        return len(self._ensure())

    def items(self):
        return self._ensure().items()

    def keys(self):
        return self._ensure().keys()

    def values(self):
        return self._ensure().values()


STYLE_CATALOG: _BotCatalogProxy = _BotCatalogProxy()


def get_catalog_json(mode: str) -> list[dict]:
    """Return catalog for a mode as JSON-friendly list of dicts."""
    from src.services.style_loader import load_styles_from_json

    styles = load_styles_from_json()
    items = []

    for s in styles:
        if s.get("mode") == mode and not _is_scenario_only(s):
            items.append(
                {
                    "key": s["id"],
                    "label": s.get("display_label", s["id"]),
                    "hook": s.get("hook_text", ""),
                    "meta": s.get("meta", {}),
                    "unlock_after_generations": s.get("unlock_after_generations", 0),
                }
            )

    return items


def get_scenario_styles_json(scenario: str) -> list[dict]:
    """Return styles tagged with ``scenario == <scenario>`` (v1 shape).

    Powers ``GET /api/v1/catalog/scenario-styles?scenario=...`` so the
    web app can fetch e.g. document-format styles for ``/dokumenty``
    without polluting the main ``cv`` catalog.
    """
    from src.services.style_loader import load_styles_from_json

    items: list[dict] = []
    for s in load_styles_from_json():
        if s.get("scenario") != scenario:
            continue
        items.append(
            {
                "key": s["id"],
                "label": s.get("display_label", s["id"]),
                "hook": s.get("hook_text", ""),
                "meta": s.get("meta", {}),
                "unlock_after_generations": s.get("unlock_after_generations", 0),
                "mode": s.get("mode"),
            }
        )
    return items


def get_available_modes() -> list[str]:
    from src.services.style_loader import load_styles_from_json

    styles = load_styles_from_json()
    modes = set(s.get("mode") for s in styles if s.get("mode"))
    return list(modes)


def get_style_options(style_id: str) -> dict | None:
    """Return allowed variations for a specific style."""
    from src.services.style_loader import load_styles_from_json

    styles = load_styles_from_json()
    for s in styles:
        if s["id"] == style_id:
            return s.get("allowed_variations", {})
    return None


# --------------------------------------------------------------------------
# style-schema-v2 catalog helpers (PR4)
#
# These helpers expose the slot-based view of a style so API clients can
# render the new «Другой вариант» modal with explicit channels. They are
# additive: absence of v2 data simply returns ``None`` and callers fall
# back to the v1 payload returned by ``get_style_options``.
# --------------------------------------------------------------------------


def _v2_slots_from_raw(raw: dict) -> dict | None:
    """Build a JSON-friendly v2 slot payload from a raw styles.json entry.

    Returns ``None`` when the entry is not yet v2-tagged so the caller can
    gracefully fall back to the v1 shape.
    """
    if int(raw.get("schema_version") or 0) != 2:
        return None

    from src.services.style_loader_v2 import _to_v2

    spec = _to_v2(raw)
    if spec is None:
        return None

    context_slots = {
        k: list(v) for k, v in spec.context_slots.items() if v
    }

    return {
        "schema_version": 2,
        "trigger": spec.trigger,
        "context_slots": context_slots,
        "weather": {
            "enabled": spec.weather.enabled,
            "allowed": list(spec.weather.allowed),
            "default_na": spec.weather.default_na,
        },
        "clothing": {
            "default": spec.clothing.default,
            "allowed": list(spec.clothing.allowed),
            "gender_neutral": spec.clothing.gender_neutral,
        },
        "background": {
            "base": spec.background.base,
            "lock": spec.background.lock.value,
            "overrides_allowed": list(spec.background.overrides_allowed),
        },
    }


def get_style_options_v2(style_id: str) -> dict | None:
    """Return v2 slot payload for a style or ``None`` if not yet migrated.

    Reads from ``data/styles.json`` directly (not the registry) so it
    works regardless of the ``style_schema_v2_enabled`` feature flag:
    the flag gates *runtime prompt generation*, while this function is
    a pure view over the data file.
    """
    from src.services.style_loader import load_styles_from_json

    for entry in load_styles_from_json():
        if entry.get("id") != style_id:
            continue
        return _v2_slots_from_raw(entry)
    return None


def get_catalog_json_v2(mode: str) -> list[dict]:
    """Return the catalog for a mode enriched with ``schema_version`` flag.

    Clients that send ``?schema=v2`` get the same list as
    :func:`get_catalog_json` plus a ``schema_version`` field per entry
    (``1`` or ``2``) so the UI can decide whether to render legacy
    ``allowed_variations`` or the new slot-based controls for that style.
    """
    from src.services.style_loader import load_styles_from_json

    styles = load_styles_from_json()
    items: list[dict] = []
    for s in styles:
        if s.get("mode") != mode or _is_scenario_only(s):
            continue
        items.append(
            {
                "key": s["id"],
                "label": s.get("display_label", s["id"]),
                "hook": s.get("hook_text", ""),
                "meta": s.get("meta", {}),
                "unlock_after_generations": s.get("unlock_after_generations", 0),
                "schema_version": int(s.get("schema_version") or 1),
            }
        )
    return items


def get_scenario_styles_json_v2(scenario: str) -> list[dict]:
    """Return styles tagged with ``scenario == <scenario>`` enriched with v2 flag."""
    from src.services.style_loader import load_styles_from_json

    items: list[dict] = []
    for s in load_styles_from_json():
        if s.get("scenario") != scenario:
            continue
        items.append(
            {
                "key": s["id"],
                "label": s.get("display_label", s["id"]),
                "hook": s.get("hook_text", ""),
                "meta": s.get("meta", {}),
                "unlock_after_generations": s.get("unlock_after_generations", 0),
                "mode": s.get("mode"),
                "schema_version": int(s.get("schema_version") or 1),
            }
        )
    return items

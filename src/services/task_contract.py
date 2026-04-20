from __future__ import annotations

from typing import Any

SCENARIO_TYPE_CORE_ENTRY = "core-entry"
SCENARIO_TYPE_STANDALONE = "standalone"

ENTRY_MODE_APP = "app"
ENTRY_MODE_LANDING = "landing"

_KNOWN_SCENARIO_TYPES = {
    SCENARIO_TYPE_CORE_ENTRY,
    SCENARIO_TYPE_STANDALONE,
}
_KNOWN_ENTRY_MODES = {
    ENTRY_MODE_APP,
    ENTRY_MODE_LANDING,
}


def normalize_market_id(raw: str | None, fallback: str = "global") -> str:
    value = (raw or "").strip().lower()
    if value:
        return value
    fb = (fallback or "").strip().lower()
    return fb or "global"


def normalize_scenario_type(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    if value in _KNOWN_SCENARIO_TYPES:
        return value
    return None


def normalize_entry_mode(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    if value in _KNOWN_ENTRY_MODES:
        return value
    return None


def build_policy_flags(
    existing: dict[str, Any] | None = None,
    *,
    cache_allowed: bool = True,
    delete_after_process: bool = False,
    retention_policy: str = "standard",
    data_class: str = "user_photo",
    single_provider_call: bool = False,
    consent_data_processing: bool = False,
    consent_ai_transfer: bool = False,
) -> dict[str, Any]:
    flags = dict(existing or {})
    flags["cache_allowed"] = bool(flags.get("cache_allowed", cache_allowed))
    flags["delete_after_process"] = bool(
        flags.get("delete_after_process", delete_after_process)
    )
    flags["retention_policy"] = str(
        flags.get("retention_policy", retention_policy)
    ).strip() or retention_policy
    flags["data_class"] = str(flags.get("data_class", data_class)).strip() or data_class
    flags["single_provider_call"] = bool(
        flags.get("single_provider_call", single_provider_call)
    )
    flags["consent_data_processing"] = bool(
        flags.get("consent_data_processing", consent_data_processing)
    )
    flags["consent_ai_transfer"] = bool(
        flags.get("consent_ai_transfer", consent_ai_transfer)
    )
    return flags


def build_task_context(
    existing: dict[str, Any] | None = None,
    *,
    market_id: str,
    service_role: str,
    compute_mode: str,
    scenario_slug: str = "",
    scenario_type: str | None = None,
    entry_mode: str | None = None,
    trace_id: str = "",
    policy_flags: dict[str, Any] | None = None,
    artifact_refs: dict[str, str] | None = None,
    remote_origin: str | None = None,
) -> dict[str, Any]:
    ctx = dict(existing or {})
    ctx["market_id"] = normalize_market_id(market_id)
    ctx["service_role"] = (service_role or "api").strip().lower() or "api"
    ctx["compute_mode"] = (compute_mode or "local").strip().lower() or "local"

    slug = (scenario_slug or "").strip()
    if slug:
        ctx["scenario_slug"] = slug

    normalized_type = normalize_scenario_type(scenario_type)
    if normalized_type:
        ctx["scenario_type"] = normalized_type

    normalized_entry_mode = normalize_entry_mode(entry_mode)
    if normalized_entry_mode:
        ctx["entry_mode"] = normalized_entry_mode

    if trace_id:
        ctx["trace_id"] = trace_id

    merged_policy = build_policy_flags(
        ctx.get("policy_flags") if isinstance(ctx.get("policy_flags"), dict) else None,
    )
    if policy_flags:
        merged_policy.update(policy_flags)
        merged_policy = build_policy_flags(merged_policy)
    ctx["policy_flags"] = merged_policy

    merged_artifacts = dict(ctx.get("artifact_refs") or {})
    if artifact_refs:
        merged_artifacts.update(
            {
                str(key): str(value)
                for key, value in artifact_refs.items()
                if value
            }
        )
    if merged_artifacts:
        ctx["artifact_refs"] = merged_artifacts

    if remote_origin:
        ctx["remote_origin"] = remote_origin

    return ctx


def get_market_id(context: dict[str, Any] | None, fallback: str = "global") -> str:
    if not isinstance(context, dict):
        return normalize_market_id(None, fallback=fallback)
    return normalize_market_id(context.get("market_id"), fallback=fallback)


def get_service_role(context: dict[str, Any] | None, fallback: str = "api") -> str:
    if not isinstance(context, dict):
        return fallback
    value = str(context.get("service_role", fallback)).strip().lower()
    return value or fallback


def get_compute_mode(context: dict[str, Any] | None, fallback: str = "local") -> str:
    if not isinstance(context, dict):
        return fallback
    value = str(context.get("compute_mode", fallback)).strip().lower()
    return value or fallback


def get_scenario_slug(context: dict[str, Any] | None) -> str | None:
    if not isinstance(context, dict):
        return None
    value = str(context.get("scenario_slug", "")).strip()
    return value or None


def get_scenario_type(context: dict[str, Any] | None) -> str | None:
    if not isinstance(context, dict):
        return None
    return normalize_scenario_type(context.get("scenario_type"))


def get_policy_flags(context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, dict):
        return build_policy_flags()
    raw = context.get("policy_flags")
    if isinstance(raw, dict):
        return build_policy_flags(raw)
    return build_policy_flags()


def is_cache_allowed(context: dict[str, Any] | None, default: bool = True) -> bool:
    flags = get_policy_flags(context)
    if "cache_allowed" not in flags:
        return default
    return bool(flags["cache_allowed"])


def should_delete_after_process(
    context: dict[str, Any] | None,
    default: bool = False,
) -> bool:
    flags = get_policy_flags(context)
    if "delete_after_process" not in flags:
        return default
    return bool(flags["delete_after_process"])


def should_force_single_provider_call(
    context: dict[str, Any] | None,
    default: bool = False,
) -> bool:
    flags = get_policy_flags(context)
    if "single_provider_call" not in flags:
        return default
    return bool(flags["single_provider_call"])


def get_trace_id(context: dict[str, Any] | None) -> str | None:
    if not isinstance(context, dict):
        return None
    value = str(context.get("trace_id", "")).strip()
    return value or None

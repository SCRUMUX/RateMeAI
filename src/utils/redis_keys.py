"""Shared Redis key helpers (API + worker + bot must stay in sync)."""


def _market_scope(market_id: str | None) -> str:
    value = (market_id or "").strip().lower()
    return value or "global"


def _scoped(prefix: str, identifier: str, market_id: str | None = None) -> str:
    if market_id is None:
        return f"ratemeai:{prefix}:{identifier}"
    return f"ratemeai:{prefix}:{_market_scope(market_id)}:{identifier}"


def task_input_cache_key(task_id: str, market_id: str | None = None) -> str:
    return _scoped("task_input", task_id, market_id)


def legacy_task_input_cache_key(task_id: str) -> str:
    return f"ratemeai:task_input:{task_id}"


def task_input_cache_keys(task_id: str, market_id: str | None = None) -> list[str]:
    key = task_input_cache_key(task_id, market_id)
    legacy = legacy_task_input_cache_key(task_id)
    return [key] if key == legacy else [key, legacy]


def gen_image_cache_key(task_id: str, market_id: str | None = None) -> str:
    return _scoped("gen_image", task_id, market_id)


def legacy_gen_image_cache_key(task_id: str) -> str:
    return f"ratemeai:gen_image:{task_id}"


def gen_image_cache_keys(task_id: str, market_id: str | None = None) -> list[str]:
    key = gen_image_cache_key(task_id, market_id)
    legacy = legacy_gen_image_cache_key(task_id)
    return [key] if key == legacy else [key, legacy]


def preanalysis_cache_key(pre_analysis_id: str, market_id: str | None = None) -> str:
    return _scoped("preanalysis", pre_analysis_id, market_id)


def legacy_preanalysis_cache_key(pre_analysis_id: str) -> str:
    return f"ratemeai:preanalysis:{pre_analysis_id}"


def preanalysis_cache_keys(
    pre_analysis_id: str,
    market_id: str | None = None,
) -> list[str]:
    key = preanalysis_cache_key(pre_analysis_id, market_id)
    legacy = legacy_preanalysis_cache_key(pre_analysis_id)
    return [key] if key == legacy else [key, legacy]


WORKER_HEARTBEAT_KEY = "ratemeai:worker:heartbeat"
WORKER_HEARTBEAT_TTL = 120


def consent_cache_key(user_id: str) -> str:
    """Redis cache of current consent state for a user (JSON list of kinds)."""
    return f"ratemeai:consent:{user_id}"


CONSENT_CACHE_TTL = 3600

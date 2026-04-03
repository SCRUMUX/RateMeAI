"""Shared Redis key helpers (API + worker must stay in sync)."""


def task_input_cache_key(task_id: str) -> str:
    return f"ratemeai:task_input:{task_id}"

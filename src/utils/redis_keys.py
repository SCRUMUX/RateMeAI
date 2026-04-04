"""Shared Redis key helpers (API + worker + bot must stay in sync)."""


def task_input_cache_key(task_id: str) -> str:
    return f"ratemeai:task_input:{task_id}"


def gen_image_cache_key(task_id: str) -> str:
    return f"ratemeai:gen_image:{task_id}"

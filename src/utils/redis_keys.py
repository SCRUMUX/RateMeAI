"""Shared Redis key helpers (API + worker + bot must stay in sync)."""


def task_input_cache_key(task_id: str) -> str:
    return f"ratemeai:task_input:{task_id}"


def gen_image_cache_key(task_id: str) -> str:
    return f"ratemeai:gen_image:{task_id}"


def embedding_cache_key(task_id: str) -> str:
    return f"ratemeai:embedding:{task_id}"


def preanalysis_cache_key(pre_analysis_id: str) -> str:
    return f"ratemeai:preanalysis:{pre_analysis_id}"


WORKER_HEARTBEAT_KEY = "ratemeai:worker:heartbeat"
WORKER_HEARTBEAT_TTL = 120

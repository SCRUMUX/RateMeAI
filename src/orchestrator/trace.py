"""Pipeline trace helpers.

Single source of truth for recording per-stage timestamps and wrapping
step exceptions into :class:`PipelineStageError` so the worker can
surface the exact stage (``preprocess`` / ``analyze`` / ``generate_image``
/ ``execute_plan`` / ``post_gen_rescore`` / ``finalize``) in
``task.error_message`` without requiring full tracebacks.
"""
from __future__ import annotations

import time
from contextlib import contextmanager


class PipelineStageError(Exception):
    """Wraps a pipeline step exception with stage name for observability.

    Nested :func:`trace_step` blocks do not re-wrap — the innermost stage
    wins so the worker always sees the original failure site.
    """

    def __init__(
        self,
        stage: str,
        original: BaseException,
        duration_ms: float | None = None,
    ):
        self.stage = stage
        self.original = original
        self.duration_ms = duration_ms
        super().__init__(f"[stage={stage}] {type(original).__name__}: {original}")


@contextmanager
def trace_step(trace: dict, step_name: str):
    """Context manager that records start/end timestamps and duration for a pipeline step.

    On exception, writes ``error`` to the trace entry and re-raises the
    exception wrapped in :class:`PipelineStageError` (unless already
    wrapped by an inner step — in that case we propagate as-is so the
    innermost stage is preserved).
    """
    entry: dict = {"started_at": time.time()}
    try:
        yield entry
    except PipelineStageError:
        entry["ended_at"] = time.time()
        entry["duration_ms"] = round((entry["ended_at"] - entry["started_at"]) * 1000, 1)
        trace["steps"][step_name] = entry
        raise
    except BaseException as exc:
        entry["ended_at"] = time.time()
        entry["duration_ms"] = round((entry["ended_at"] - entry["started_at"]) * 1000, 1)
        entry["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        trace["steps"][step_name] = entry
        if isinstance(exc, Exception):
            raise PipelineStageError(step_name, exc, entry["duration_ms"]) from exc
        raise
    else:
        entry["ended_at"] = time.time()
        entry["duration_ms"] = round((entry["ended_at"] - entry["started_at"]) * 1000, 1)
        trace["steps"][step_name] = entry


__all__ = ["PipelineStageError", "trace_step"]

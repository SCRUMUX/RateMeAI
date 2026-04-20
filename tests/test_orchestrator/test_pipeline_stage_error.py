"""Verify pipeline stage tracking: exceptions from ``_trace_step`` are wrapped
in :class:`PipelineStageError` so the worker can render a structured
``task.error_message`` like ``[stage=analyze] ReadTimeout: ...`` (A1 fix).
"""
from __future__ import annotations

import pytest

from src.orchestrator.pipeline import PipelineStageError, _trace_step


def test_trace_step_wraps_exception_with_stage():
    trace = {"steps": {}}
    with pytest.raises(PipelineStageError) as ei:
        with _trace_step(trace, "preprocess"):
            raise ValueError("bad image")

    exc = ei.value
    assert exc.stage == "preprocess"
    assert isinstance(exc.original, ValueError)
    assert "[stage=preprocess]" in str(exc)
    assert "ValueError" in str(exc)
    assert "bad image" in str(exc)

    entry = trace["steps"]["preprocess"]
    assert "duration_ms" in entry
    assert "ValueError" in entry["error"]


def test_trace_step_does_not_double_wrap_nested_stage():
    # Outer ``execute_plan`` should see the innermost stage ``analyze`` rather
    # than re-wrapping it as ``[stage=execute_plan] PipelineStageError: ...``.
    trace = {"steps": {}}
    with pytest.raises(PipelineStageError) as ei:
        with _trace_step(trace, "execute_plan"):
            with _trace_step(trace, "analyze"):
                raise RuntimeError("LLM exploded")

    exc = ei.value
    assert exc.stage == "analyze"
    assert isinstance(exc.original, RuntimeError)
    assert "[stage=analyze]" in str(exc)


def test_trace_step_records_duration_on_success():
    trace = {"steps": {}}
    with _trace_step(trace, "finalize"):
        pass
    entry = trace["steps"]["finalize"]
    assert "started_at" in entry
    assert "ended_at" in entry
    assert "duration_ms" in entry
    assert "error" not in entry


def test_format_task_error_unwraps_stage():
    from src.workers.tasks import _format_task_error

    original = RuntimeError("LLM 503")
    stage_err = PipelineStageError("analyze", original, duration_ms=42.0)
    msg = _format_task_error(stage_err)
    assert msg.startswith("[stage=analyze]")
    assert "RuntimeError" in msg
    assert "LLM 503" in msg
    assert len(msg) <= 500


def test_format_task_error_falls_back_to_worker_stage():
    from src.workers.tasks import _format_task_error

    msg = _format_task_error(OSError("disk gone"))
    assert msg.startswith("[stage=worker]")
    assert "OSError" in msg
    assert "disk gone" in msg


def test_is_transient_sees_through_pipeline_stage_error():
    from src.workers.tasks import _is_transient

    # A ReadTimeout inside PipelineStageError should still classify as transient
    # so the worker's retry loop can retry the whole pipeline.
    wrapped = PipelineStageError("analyze", TimeoutError("read timed out"))
    assert _is_transient(wrapped)

    # A terminal error buried in PipelineStageError stays non-transient.
    wrapped2 = PipelineStageError("preprocess", ValueError("bad jpeg"))
    assert not _is_transient(wrapped2)

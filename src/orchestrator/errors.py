"""Error formatting helpers used across pipeline, executor and worker.

Single source of truth for unwrapping nested exceptions and emitting
human-readable diagnostics that the worker writes into
``task.error_message`` and the frontend uses to route into specific UI
messages (e.g. PROVIDER_AUTH_MESSAGE for ``http=401``).
"""

from __future__ import annotations

from src.orchestrator.trace import PipelineStageError


def unwrap_exception(exc: BaseException) -> BaseException:
    """Peel tenacity.RetryError / PipelineStageError down to the real cause.

    Without this, worker writes ``RetryError[<Future at 0x… raised
    HTTPStatusError>]`` into ``Task.error_message`` — which tells us
    nothing (no HTTP status, no body, no URL).
    """
    seen: set[int] = set()
    cur: BaseException = exc
    for _ in range(8):
        if id(cur) in seen:
            break
        seen.add(id(cur))
        if isinstance(cur, PipelineStageError):
            cur = cur.original
            continue
        try:
            from tenacity import RetryError as _RetryError

            if isinstance(cur, _RetryError):
                last = getattr(cur, "last_attempt", None)
                if last is not None:
                    nested = last.exception()
                    if nested is not None:
                        cur = nested
                        continue
        except Exception:
            pass
        cause = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
        if cause is not None and cause is not cur:
            cur = cause
            continue
        break
    return cur


def http_status_of(exc: BaseException) -> int | None:
    """Extract HTTP status code from httpx.HTTPStatusError-like exceptions."""
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    if isinstance(code, int):
        return code
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    return None


def format_task_error(exc: Exception) -> str:
    """Build a structured ``error_message`` like ``[stage=analyze] ReadTimeout: ...``.

    Truncated to 500 chars (DB column limit). The stage helps ops
    pinpoint *where* in the pipeline a task died without reading full
    tracebacks. For HTTP-layer failures we also embed ``http=<code>``
    and host — the single most important bit when debugging LLM /
    provider outages.
    """
    if isinstance(exc, PipelineStageError):
        stage = exc.stage
    else:
        stage = "worker"

    original = unwrap_exception(exc)
    exc_type = type(original).__name__

    extras: list[str] = []
    status = http_status_of(original)
    if status is not None:
        extras.append(f"http={status}")
    response = getattr(original, "response", None)
    if response is not None:
        try:
            body = getattr(response, "text", "") or ""
            if body:
                snippet = body.strip().replace("\n", " ")
                if len(snippet) > 140:
                    snippet = snippet[:137] + "..."
                extras.append(f"body={snippet!r}")
        except Exception:
            pass
    request = getattr(original, "request", None)
    url = getattr(request, "url", None) if request is not None else None
    if url is not None:
        try:
            host = getattr(url, "host", None) or str(url).split("/")[2]
            if host:
                extras.append(f"host={host}")
        except Exception:
            pass

    # v1.64: the Reve-specific error-code branch was removed alongside
    # the Reve provider. FAL adapter exceptions inherit from
    # ``httpx.HTTPStatusError`` and are surfaced via the generic
    # response/request branches above.

    extras_suffix = (" " + " ".join(extras)) if extras else ""
    text = f"[stage={stage}] {exc_type}: {str(original)[:260]}{extras_suffix}"
    return text[:500]


def format_image_gen_error(exc: BaseException) -> str:
    """Compact, UI-safe description of an image-generation failure.

    When ``single_pass`` catches an exception we set
    ``image_gen_error="generation_failed"`` and the worker marks the
    task as ``completed`` with ``no_image_reason="generation_error"``.
    The web UI then picks a hard-coded "Попробуйте другой стиль"
    string and the real provider cause is lost. Store a short
    diagnostic here so the frontend can surface it instead.

    v1.64: the Reve-specific code/request-id formatter was removed.
    FAL adapters raise ``httpx.HTTPStatusError`` whose default
    string already carries status + URL.
    """
    exc_type = type(exc).__name__
    msg = str(exc) or exc_type
    text = f"{exc_type}: {msg[:260]}"
    return text[:320]


__all__ = [
    "unwrap_exception",
    "http_status_of",
    "format_task_error",
    "format_image_gen_error",
]

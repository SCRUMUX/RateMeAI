"""Hard block for cross-border AI transfers without explicit user consent.

Usage pattern:

1. The pipeline entry point (``AnalysisPipeline.execute``) binds the current
   task's ``policy_flags`` to the ``_current_task_context`` ``ContextVar``.
2. Providers that make outbound calls to external AI services (OpenRouter,
   Reve, Replicate) invoke ``assert_external_transfer_allowed`` before each
   request.
3. If ``consent_ai_transfer`` is missing, the provider raises
   ``AITransferForbiddenError`` which the pipeline converts to an
   analysis-only fallback with ``no_image_reason="consent_missing_ai_transfer"``.

This makes the guard minimally invasive — no public signatures change.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from src.services.task_contract import get_policy_flags

logger = logging.getLogger(__name__)


class AITransferForbiddenError(PermissionError):
    """Raised when an outbound AI call would violate the consent contract."""

    def __init__(self, provider: str, reason: str = "consent_missing_ai_transfer"):
        super().__init__(f"{provider}: {reason}")
        self.provider = provider
        self.reason = reason


_current_task_context: ContextVar[dict | None] = ContextVar(
    "privacy_task_context", default=None
)


@contextmanager
def task_context_scope(context: dict | None):
    """Bind the given task context for the duration of the ``with`` block."""
    token = _current_task_context.set(context)
    try:
        yield
    finally:
        _current_task_context.reset(token)


def get_current_task_context() -> dict | None:
    return _current_task_context.get()


def is_external_transfer_allowed(context: dict | None = None) -> bool:
    ctx = context if context is not None else _current_task_context.get()
    if ctx is None:
        return False
    flags = get_policy_flags(ctx)
    return bool(flags.get("consent_ai_transfer"))


def assert_external_transfer_allowed(
    provider: str,
    context: dict | None = None,
) -> None:
    """Raise :class:`AITransferForbiddenError` if consent is missing.

    Safe no-op when called outside a pipeline request (no bound context) — in
    that situation we fall back to "allow" to avoid breaking dev/tests and
    standalone tooling. Production pipelines always set a context.
    """
    ctx = context if context is not None else _current_task_context.get()
    if ctx is None:
        return
    if not is_external_transfer_allowed(ctx):
        logger.warning(
            "ai_transfer.blocked", extra={"provider": provider}
        )
        raise AITransferForbiddenError(provider)

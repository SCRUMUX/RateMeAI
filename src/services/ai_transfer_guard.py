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

from src.config import settings
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

    Fail-closed policy:

    - In **production** (``settings.is_production``): if no pipeline
      context is bound (meaning the caller forgot to wrap the
      cross-border-sending code in ``task_context_scope``), we treat
      that as a *hard failure* and raise ``AITransferForbiddenError``.
      This closes the previous "fail-open backdoor" where a developer
      could accidentally bypass the consent check by calling a provider
      from outside a pipeline scope (flagged as Critical C3 in the
      v1.10 privacy audit).
    - In **dev / tests**: we keep the safe no-op behaviour for missing
      context so standalone tooling (notebooks, migration scripts,
      unit-tests that don't care about consent) can still exercise the
      providers directly.
    """
    ctx = context if context is not None else _current_task_context.get()
    if ctx is None:
        if settings.is_production:
            logger.error(
                "ai_transfer.no_context",
                extra={"provider": provider},
            )
            raise AITransferForbiddenError(provider, reason="no_pipeline_context")
        return
    if not is_external_transfer_allowed(ctx):
        logger.warning(
            "ai_transfer.blocked", extra={"provider": provider}
        )
        raise AITransferForbiddenError(provider)

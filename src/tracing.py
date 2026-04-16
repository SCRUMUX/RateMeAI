"""OpenTelemetry setup for distributed tracing across the analysis pipeline.

Traces propagate through: API -> ARQ Worker -> Pipeline -> LLM/ImageGen providers.

To enable, set OTEL_EXPORTER_OTLP_ENDPOINT in the environment (e.g. to a Jaeger
or Grafana Tempo collector). When the endpoint is not set, tracing is disabled and
all span operations are no-ops.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

logger = logging.getLogger(__name__)

_tracer = None
_initialized = False


def _try_init() -> None:
    global _tracer, _initialized
    if _initialized:
        return
    _initialized = True

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        logger.debug("OTEL_EXPORTER_OTLP_ENDPOINT not set — tracing disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": "ratemeai"})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("ratemeai")
        logger.info("OpenTelemetry tracing initialized (endpoint=%s)", endpoint)
    except ImportError:
        logger.warning(
            "opentelemetry packages not installed — tracing disabled. "
            "Install with: pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-exporter-otlp-proto-grpc"
        )
    except Exception:
        logger.exception("Failed to initialize OpenTelemetry tracing")


def get_tracer():
    """Return the OTEL tracer, or None if tracing is not available."""
    _try_init()
    return _tracer


@contextmanager
def span(name: str, attributes: dict | None = None) -> Iterator[None]:
    """Synchronous span context manager. No-op if tracing is disabled."""
    tracer = get_tracer()
    if tracer is None:
        yield
        return
    with tracer.start_as_current_span(name, attributes=attributes or {}):
        yield


@asynccontextmanager
async def async_span(name: str, attributes: dict | None = None) -> AsyncIterator[None]:
    """Async span context manager. No-op if tracing is disabled."""
    tracer = get_tracer()
    if tracer is None:
        yield
        return
    with tracer.start_as_current_span(name, attributes=attributes or {}):
        yield


def add_span_attribute(key: str, value) -> None:
    """Add an attribute to the current span, if tracing is active."""
    try:
        from opentelemetry import trace
        current = trace.get_current_span()
        if current and current.is_recording():
            current.set_attribute(key, value)
    except ImportError:
        pass
    except Exception:
        pass

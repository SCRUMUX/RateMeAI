import time
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        response.headers["X-Request-Id"] = correlation_id

        logger.info(
            "%s %s -> %s (%.3fs) [%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            correlation_id[:12],
        )
        return response

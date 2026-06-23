import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.metrics import REQUEST_COUNT, REQUEST_LATENCY, ERROR_COUNT

logger = structlog.get_logger()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            duration = time.perf_counter() - start_time
            await logger.aerror(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration=round(duration, 4),
                error=str(exc),
            )
            raise

        duration = time.perf_counter() - start_time
        status_code = response.status_code

        # Skip metrics endpoint from instrumentation
        if request.url.path != "/metrics":
            endpoint = request.url.path
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=endpoint,
                status_code=status_code,
            ).inc()
            REQUEST_LATENCY.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(duration)

            if status_code >= 400:
                ERROR_COUNT.labels(
                    method=request.method,
                    endpoint=endpoint,
                    status_code=status_code,
                ).inc()

            await logger.ainfo(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration=round(duration, 4),
            )

        response.headers["X-Request-ID"] = request_id
        return response

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from template_fastcrud_api.core.contracts import (
    EventOutcome,
    HttpCompletion,
    HttpExecution,
    HttpRequestResult,
    LogContext,
)
from template_fastcrud_api.core.logging import request_outcome, work_context
from template_fastcrud_api.core.metrics import HttpMetrics

logger = logging.getLogger(__name__)

EXCLUDED_PATHS = frozenset(
    {
        "/metrics",
        "/health/live",
        "/health/ready",
        "/docs",
        "/docs/oauth2-redirect",
        "/openapi.json",
        "/redoc",
    }
)


def resolve_completion(
    *,
    finished: float | None,
    send_failed: bool,
    disconnected: bool,
    execution: HttpExecution,
) -> HttpCompletion:
    """전송 완료 사실을 후속 오류·취소보다 우선합니다."""
    if finished is not None:
        return HttpCompletion.COMPLETE
    if send_failed:
        return HttpCompletion.SEND_FAILED
    if execution is HttpExecution.CANCELLED:
        return HttpCompletion.CANCELLED
    if disconnected:
        return HttpCompletion.DISCONNECTED
    return HttpCompletion.INCOMPLETE


class HttpObservation:
    """완성된 ASGI 앱 바깥에서 전송·실행 결과만 관측합니다."""

    def __init__(
        self,
        app: ASGIApp,
        metrics: HttpMetrics,
        *,
        timer: Callable[[], float] = perf_counter,
        log_context: LogContext | None = None,
    ) -> None:
        self.app = app
        self.metrics = metrics
        self.timer = timer
        self.log_context = log_context

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        excluded = scope["path"] in EXCLUDED_PATHS
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        context = (
            replace(self.log_context, work_id=request_id) if self.log_context else None
        )
        token = work_context.set(context)

        started = self.timer()
        finished: float | None = None
        status: int | None = None
        send_failed = False
        disconnected = False
        execution = HttpExecution.RETURNED
        error: Exception | None = None

        async def observed_send(message: Message) -> None:
            nonlocal finished, status, send_failed
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ] + [(b"x-request-id", request_id.encode("ascii"))]
            try:
                await send(message)
            except OSError:
                send_failed = True
                raise
            if message["type"] == "http.response.start":
                code = message["status"]
                status = code if 100 <= code <= 599 else None
            elif message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                finished = self.timer()

        async def observed_receive() -> Message:
            nonlocal disconnected
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnected = True
            return message

        try:
            await self.app(scope, observed_receive, observed_send)
        except asyncio.CancelledError:
            execution = HttpExecution.CANCELLED
            raise
        except Exception as caught:
            execution = HttpExecution.ERROR
            error = caught
            raise
        finally:
            try:
                elapsed = (finished if finished is not None else self.timer()) - started
                result = HttpRequestResult(
                    method=scope["method"],
                    route=getattr(scope.get("route"), "path", "unmatched"),
                    status=status,
                    completion=resolve_completion(
                        finished=finished,
                        send_failed=send_failed,
                        disconnected=disconnected,
                        execution=execution,
                    ),
                    execution=execution,
                    duration_seconds=max(0.0, elapsed),
                )
                if context is not None and error is not None:
                    logger.error(
                        "http.failed",
                        exc_info=(type(error), error, error.__traceback__),
                        extra={"event_outcome": EventOutcome.FAILURE},
                    )
                if not excluded:
                    self.metrics.record(result)
                    if context is not None:
                        logger.info(
                            "http.completed",
                            extra={
                                "http_result": result,
                                "event_outcome": request_outcome(result),
                            },
                        )
            except Exception:
                self.metrics.failed = True
            finally:
                work_context.reset(token)

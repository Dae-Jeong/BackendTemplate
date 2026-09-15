import json
import logging
import sys
from collections import deque
from contextvars import ContextVar
from datetime import UTC, datetime
from http import HTTPMethod
from pathlib import PurePath
from types import CodeType, TracebackType

from template_fastcrud_api.core.contracts import (
    EventOutcome,
    HttpCompletion,
    HttpExecution,
    HttpRequestResult,
    LogContext,
)

work_context: ContextVar[LogContext | None] = ContextVar("work_context", default=None)
MAX_LOG_BYTES = 16 * 1024
MAX_FRAMES = 20
EVENTS = frozenset({"http.completed", "http.failed", "greeting.completed"})
SERVER_EVENTS = {
    "Uvicorn running on %s://%s:%d (Press CTRL+C to quit)": "server.listening",
    "Uvicorn running on socket %s (Press CTRL+C to quit)": "server.listening",
    "Started server process [%d]": "server.started",
    "Finished server process [%d]": "server.stopped",
    "Waiting for application startup.": "application.starting",
    "Application startup complete.": "application.ready",
    "Shutting down": "server.stopping",
    "Waiting for application shutdown.": "application.stopping",
    "Application shutdown complete.": "application.stopped",
}


def error_frames(traceback: TracebackType | None) -> list[dict[str, str | int]]:
    frames: deque[dict[str, str | int]] = deque(maxlen=MAX_FRAMES)
    while traceback is not None:
        code = traceback.tb_frame.f_code
        frames.append(
            {
                "file": PurePath(code.co_filename).name[:128],
                "function": code.co_name[:128],
                "line": traceback.tb_lineno,
            }
        )
        traceback = traceback.tb_next
    return list(frames)


class JsonFormatter(logging.Formatter):
    def __init__(self, context: LogContext) -> None:
        super().__init__()
        self.context = context

    def format(self, record: logging.LogRecord) -> str:
        context = work_context.get() or self.context
        event = record.msg if type(record.msg) is str and record.msg in EVENTS else None
        if event is None:
            event = (
                SERVER_EVENTS.get(record.msg, "server.event")
                if type(record.msg) is str
                else "server.event"
            )
        app: dict[str, object] = {
            "environment": context.environment[:64],
            "log_schema_version": 1,
        }
        event_fields: dict[str, object] = {"action": event}
        payload: dict[str, object] = {
            "@timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "log": {"level": record.levelname.lower(), "logger": record.name[:128]},
            "service": {
                "name": context.service_name[:128],
                "version": context.service_version[:128],
            },
            "app": app,
            "message": event,
            "event": event_fields,
        }
        if context.work_id is not None:
            app["work"] = {"id": context.work_id[:128], "kind": "http"}
        outcome = getattr(record, "event_outcome", None)
        if isinstance(outcome, EventOutcome):
            event_fields["outcome"] = outcome.value
        result = getattr(record, "http_result", None)
        if isinstance(result, HttpRequestResult):
            event_fields["duration"] = round(result.duration_seconds * 1_000_000_000)
            payload["http"] = {
                "request": {
                    "method": result.method if result.method in HTTPMethod else "OTHER"
                },
                "response": {"status_code": result.status},
                "route": result.route[:512],
                "completion": result.completion.value,
                "execution": result.execution.value,
            }
        if record.exc_info is not None and record.exc_info[0] is not None:
            payload["error"] = {"type": record.exc_info[0].__name__[:128]}
            app["error"] = {"frames": error_frames(record.exc_info[2])}
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(line.encode("utf-8")) + 1 > MAX_LOG_BYTES:
            app.pop("error", None)
            app["truncated"] = True
            line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return line


class JsonHandler(logging.StreamHandler):
    """표준 handler의 출력 오류에서 원문 record·traceback 노출을 막습니다."""

    def handleError(self, record: logging.LogRecord) -> None:
        try:
            sys.stderr.write(
                '{"message":"logging.output_failed","log":{"level":"error"}}\n'
            )
            sys.stderr.flush()
        except Exception:
            # stdout·stderr 동시 장애에서는 보고를 보장할 수 없습니다.
            pass


class EventFilter(logging.Filter):
    def __init__(self, http_boundary: CodeType) -> None:
        super().__init__()
        self.http_boundary = http_boundary

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("template_fastcrud_api"):
            return type(record.msg) is str and record.msg in EVENTS
        if not record.name.startswith("uvicorn"):
            return False
        # wrapper가 처리한 HTTP 예외만 중복 제외합니다. 다른 서버 오류는 남깁니다.
        if record.msg == "Exception in ASGI application\n" and record.exc_info:
            traceback = record.exc_info[2]
            while traceback is not None:
                if traceback.tb_frame.f_code is self.http_boundary:
                    return False
                traceback = traceback.tb_next
        return True


def configure_logging(
    context: LogContext, level: str, *, http_boundary: CodeType
) -> None:
    """실행 진입점에서만 호출하며 타 도구 handler는 삭제하지 않습니다."""
    for name in ("template_fastcrud_api", "uvicorn"):
        logger = logging.getLogger(name)
        handler = next((h for h in logger.handlers if isinstance(h, JsonHandler)), None)
        if handler is None:
            handler = JsonHandler(sys.stdout)
            handler.addFilter(EventFilter(http_boundary))
            logger.addHandler(handler)
        handler.setFormatter(JsonFormatter(context))
        logger.setLevel(level.upper())
        logger.propagate = False


def request_outcome(result: HttpRequestResult) -> EventOutcome:
    if (
        result.execution is not HttpExecution.RETURNED
        or result.completion is not HttpCompletion.COMPLETE
    ):
        return EventOutcome.FAILURE
    if result.status is None:
        return EventOutcome.UNKNOWN
    return EventOutcome.FAILURE if result.status >= 400 else EventOutcome.SUCCESS

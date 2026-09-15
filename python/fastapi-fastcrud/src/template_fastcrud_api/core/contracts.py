from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

type Clock = Callable[[], datetime]


class HttpCompletion(StrEnum):
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    SEND_FAILED = "send_failed"
    DISCONNECTED = "disconnected"
    INCOMPLETE = "incomplete"


class HttpExecution(StrEnum):
    RETURNED = "returned"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class HttpRequestResult:
    method: str
    route: str
    status: int | None
    completion: HttpCompletion
    execution: HttpExecution
    duration_seconds: float


class EventOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LogContext:
    service_name: str
    service_version: str
    environment: str
    work_id: str | None = None

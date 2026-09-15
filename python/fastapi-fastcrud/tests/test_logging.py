import asyncio
import io
import json
import logging
import sys
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.contracts import LogContext
from template_fastcrud_api.core.logging import (
    MAX_LOG_BYTES,
    JsonFormatter,
    JsonHandler,
    configure_logging,
    work_context,
)
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.http.observation import HttpObservation


@pytest.fixture
def output(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    stream = io.StringIO()
    saved = {}
    for name in ("template_fastcrud_api", "uvicorn"):
        logger = logging.getLogger(name)
        saved[name] = (logger.level, logger.propagate, tuple(logger.handlers))
    monkeypatch.setattr(sys, "stdout", stream)
    configure_logging(
        LogContext("test", "1", "test"),
        "info",
        http_boundary=HttpObservation.__call__.__code__,
    )
    yield stream
    for name, (level, propagate, handlers) in saved.items():
        logger = logging.getLogger(name)
        for handler in tuple(logger.handlers):
            if handler not in handlers:
                logger.removeHandler(handler)
                handler.close()
        logger.setLevel(level)
        logger.propagate = propagate


def test_request_summary_error_and_private_data(output: io.StringIO) -> None:
    app = create_app(Settings(app_name="서비스"))

    @app.get("/test/error")
    def fail() -> None:
        raise ValueError("private-exception")

    with TestClient(
        HttpObservation(
            app,
            app.state.metrics,
            log_context=app.state.log_context,
        ),
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/v1/greetings?name=private-name",
            headers={"x-request-id": "private-id", "Authorization": "private-token"},
        )
        rejected = client.get("/v1/greetings?name=%20")
        failure = client.get("/test/error")
        client.get("/docs")
        client.get("/metrics")
    lines = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(lines) == 4
    summaries = [line for line in lines if line["event"]["action"] == "http.completed"]
    assert [line["http"]["response"]["status_code"] for line in summaries] == [
        200,
        422,
        500,
    ]
    assert [line["app"]["work"]["id"] for line in summaries] == [
        response.headers["x-request-id"],
        rejected.headers["x-request-id"],
        failure.headers["x-request-id"],
    ]
    assert len({line["app"]["work"]["id"] for line in summaries}) == 3
    assert all(type(line["event"]["duration"]) is int for line in summaries)
    assert all(line["service"]["name"] == "서비스" for line in lines)
    detail = next(line for line in lines if line["event"]["action"] == "http.failed")
    assert detail["error"]["type"] == "ValueError"
    assert detail["app"]["work"]["id"] == failure.headers["x-request-id"]
    assert 0 < len(detail["app"]["error"]["frames"]) <= 20
    assert "private-" not in output.getvalue()
    assert work_context.get() is None


def test_logging_setup_twice_preserves_foreign_handler(output: io.StringIO) -> None:
    logger = logging.getLogger("template_fastcrud_api")
    foreign = logging.NullHandler()
    logger.addHandler(foreign)
    try:
        configure_logging(
            LogContext("test", "1", "test"),
            "info",
            http_boundary=HttpObservation.__call__.__code__,
        )
        logger.info("greeting.completed")
        assert foreign in logger.handlers
        assert len([h for h in logger.handlers if isinstance(h, JsonHandler)]) == 1
        assert len(output.getvalue().splitlines()) == 1
    finally:
        logger.removeHandler(foreign)


def test_allowlist_does_not_format_untrusted_message_or_extras(
    output: io.StringIO,
) -> None:
    logger = logging.getLogger("template_fastcrud_api.test")
    # pytest는 자체 capture handler를 추가합니다. 이 시험은 소유 출력 경계를 검사합니다.
    handler = next(
        h
        for h in logging.getLogger("template_fastcrud_api").handlers
        if isinstance(h, JsonHandler)
    )
    secret = Mock()
    secret.__str__ = Mock(side_effect=AssertionError("must not format"))
    handler.handle(
        logger.makeRecord(logger.name, logging.INFO, __file__, 1, secret, (), None)
    )
    handler.handle(
        logger.makeRecord(
            logger.name,
            logging.INFO,
            __file__,
            1,
            "greeting.completed",
            (secret,),
            None,
            extra={
                "token": "private-token",
                "event_outcome": "private-outcome",
                "http_result": {"status": "private-status"},
                "app": "private-collision",
            },
        )
    )
    lines = output.getvalue().splitlines()
    assert len(lines) == 1
    assert "private-" not in lines[0]
    assert json.loads(lines[0])["app"]["log_schema_version"] == 1
    secret.__str__.assert_not_called()


def test_concurrent_context_and_cancellation_restore_parent(
    output: io.StringIO,
) -> None:
    from starlette.types import Message, Receive, Scope, Send

    async def scenario() -> None:
        ready = asyncio.Event()

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            logging.getLogger("template_fastcrud_api.test").info("greeting.completed")
            if scope["method"] == "POST":
                ready.set()
                await asyncio.Future()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def receive() -> Message:
            return {"type": "http.request", "body": b""}

        async def send(message: Message) -> None:
            pass

        def scope(method: str) -> Scope:
            return {"type": "http", "path": "/test", "method": method}

        first = create_app(Settings(app_name="first"))
        second = create_app(Settings(app_name="second"))
        observer = HttpObservation(
            app, first.state.metrics, log_context=first.state.log_context
        )
        other = HttpObservation(
            app, second.state.metrics, log_context=second.state.log_context
        )
        parent = LogContext("parent", "1", "test", "parent-id")
        token = work_context.set(parent)
        try:
            task = asyncio.create_task(observer(scope("POST"), receive, send))
            await asyncio.wait_for(ready.wait(), timeout=2)
            await other(scope("GET"), receive, send)
            assert work_context.get() is parent
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert work_context.get() is parent
        finally:
            work_context.reset(token)

    asyncio.run(scenario())
    lines = [json.loads(line) for line in output.getvalue().splitlines()]
    for name in ("first", "second"):
        records = [line for line in lines if line["service"]["name"] == name]
        assert len(records) == 2
        assert len({line["app"]["work"]["id"] for line in records}) == 1
    cancelled = lines[-1]
    assert cancelled["http"]["execution"] == "cancelled"
    assert cancelled["event"]["outcome"] == "failure"
    assert work_context.get() is None


def test_output_failure_preserves_http_and_reports_safe_fallback(
    output: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    errors = io.StringIO()
    monkeypatch.setattr(sys, "stderr", errors)
    handler = next(
        h
        for h in logging.getLogger("template_fastcrud_api").handlers
        if isinstance(h, JsonHandler)
    )
    monkeypatch.setattr(
        handler, "stream", Mock(write=Mock(side_effect=OSError("private-sink-error")))
    )
    app = create_app(Settings())

    @app.get("/test/error")
    def fail() -> None:
        raise ValueError("private-original")

    with TestClient(
        HttpObservation(app, app.state.metrics, log_context=app.state.log_context)
    ) as client:
        assert client.get("/").status_code == 200
        with pytest.raises(ValueError, match="private-original"):
            client.get("/test/error")
    assert len(errors.getvalue().splitlines()) == 3
    assert "private-" not in errors.getvalue()
    assert all(
        json.loads(line)["message"] == "logging.output_failed"
        for line in errors.getvalue().splitlines()
    )
    assert work_context.get() is None


def test_utf8_line_size_and_truncation_remain_valid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "template_fastcrud_api.core.logging.error_frames",
        lambda tb: [
            {"file": "파일" * 64, "function": "함수" * 64, "line": 1} for _ in range(20)
        ],
    )
    formatter = JsonFormatter(LogContext("서비스\n" * 128, "1", "test"))
    record = logging.LogRecord(
        "template_fastcrud_api.test",
        logging.ERROR,
        __file__,
        1,
        "http.failed",
        (),
        (ValueError, ValueError("private-error"), None),
    )
    line = formatter.format(record)
    assert len(line.encode("utf-8")) + 1 <= MAX_LOG_BYTES
    assert "\n" not in line
    assert json.loads(line)["app"]["truncated"] is True
    assert "private-error" not in line


def test_formatter_failure_has_safe_fallback(
    output: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    errors = io.StringIO()
    monkeypatch.setattr(sys, "stderr", errors)
    monkeypatch.setattr(
        JsonFormatter, "format", Mock(side_effect=ValueError("private-format-error"))
    )
    logging.getLogger("template_fastcrud_api.test").info("greeting.completed")
    assert json.loads(errors.getvalue())["message"] == "logging.output_failed"
    assert "private-" not in errors.getvalue()


@pytest.mark.parametrize("mode", ["body_error", "send_failed", "background_error"])
def test_response_failure_logs_preserve_transmission(
    output: io.StringIO,
    mode: str,
) -> None:
    from starlette.types import Message, Receive, Scope, Send

    sent: list[Message] = []
    original = (
        OSError("private-send") if mode == "send_failed" else ValueError("private-body")
    )

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        if mode == "body_error":
            raise original
        await send({"type": "http.response.body", "body": b"ok"})
        if mode == "background_error":
            raise original

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        if mode == "send_failed" and message["type"] == "http.response.body":
            raise original
        sent.append(message)

    state = create_app(Settings()).state
    times = iter([1.0, 1.125])
    observer = HttpObservation(
        app, state.metrics, log_context=state.log_context, timer=lambda: next(times)
    )
    with pytest.raises(type(original)) as caught:
        asyncio.run(
            observer({"type": "http", "path": "/test", "method": "GET"}, receive, send)
        )
    assert caught.value is original
    assert len([m for m in sent if m["type"] == "http.response.start"]) == 1
    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(records) == 2
    summary = records[-1]
    assert summary["http"]["response"]["status_code"] == 200
    assert summary["http"]["execution"] == "error"
    assert (
        summary["http"]["completion"]
        == {
            "body_error": "incomplete",
            "send_failed": "send_failed",
            "background_error": "complete",
        }[mode]
    )
    assert summary["event"]["duration"] == 125_000_000
    assert "private-" not in output.getvalue()

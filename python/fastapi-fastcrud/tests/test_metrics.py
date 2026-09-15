import asyncio
from typing import cast
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.metrics import HttpMetrics, create_metrics
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.http.observation import HttpObservation


def labels(
    *,
    route: str = "unmatched",
    status: str = "200",
    completion: str = "complete",
    execution: str = "returned",
    method: str = "GET",
) -> dict[str, str]:
    return dict(
        route=route,
        status=status,
        completion=completion,
        execution=execution,
        method=method,
    )


def sample(metrics: HttpMetrics, name: str, expected: dict[str, str]) -> float | None:
    return metrics.registry.get_sample_value(name, expected)


def test_http_metrics_counts_exclusions_and_app_isolation() -> None:
    app = create_app(Settings())
    metrics = cast(HttpMetrics, app.state.metrics)

    @app.get("/test/error")
    def error() -> None:
        raise ValueError("synthetic-private-error")

    with TestClient(
        HttpObservation(app, metrics), raise_server_exceptions=False
    ) as client:
        assert client.get("/v1/greetings?name=private-name").status_code == 200
        assert client.get("/v1/greetings?name=%20").status_code == 422
        assert client.get("/private-path-1").status_code == 404
        assert client.get("/private-path-2").status_code == 404
        assert client.get("/test/error").status_code == 500
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/redoc").status_code == 200
        assert client.get("/docs/oauth2-redirect").status_code == 200
        first = client.get("/metrics")
        second = client.get("/metrics")
    assert first.status_code == 200
    assert first.headers["content-type"].startswith("text/plain")
    assert first.content == second.content
    assert "private-name" not in first.text
    assert "private-path" not in first.text
    assert "synthetic-private-error" not in first.text
    expected = [
        (labels(route="/v1/greetings"), 1),
        (labels(route="/v1/greetings", status="422"), 1),
        (labels(status="404"), 2),
        (labels(route="/test/error", status="500", execution="error"), 1),
    ]
    for dimensions, count in expected:
        assert sample(metrics, "http_requests_total", dimensions) == count
        assert (
            sample(metrics, "http_request_duration_seconds_count", dimensions) == count
        )
    assert (
        len(
            [
                s
                for family in metrics.registry.collect()
                for s in family.samples
                if s.name == "http_requests_total"
            ]
        )
        == 4
    )
    other = create_app(Settings())
    with TestClient(HttpObservation(other, other.state.metrics)) as client:
        assert 'route="/v1/greetings"' not in client.get("/metrics").text


def scope(method: str = "GET") -> Scope:
    return {"type": "http", "method": method, "path": "/test", "headers": []}


def test_dynamic_route_uses_template_and_preserves_method_rejection() -> None:
    app = create_app(Settings())

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    metrics = cast(HttpMetrics, app.state.metrics)
    with TestClient(HttpObservation(app, metrics)) as client:
        assert client.get("/items/private-one").status_code == 200
        assert client.get("/items/private-two").status_code == 200
        assert client.post("/items/private-three").status_code == 405
        exposition = client.get("/metrics").text
    assert "private-" not in exposition
    assert sample(metrics, "http_requests_total", labels(route="/items/{item_id}")) == 2
    assert (
        sample(
            metrics,
            "http_requests_total",
            labels(route="/items/{item_id}", method="POST", status="405"),
        )
        == 1
    )


async def receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


async def send(message: Message) -> None:
    return None


@pytest.mark.parametrize(
    ("mode", "status", "completion", "execution"),
    [
        ("complete", "200", "complete", "returned"),
        ("body_error", "200", "incomplete", "error"),
        ("send_failed", "200", "send_failed", "error"),
        ("cancelled", "none", "cancelled", "cancelled"),
        ("disconnected", "none", "disconnected", "returned"),
        ("incomplete", "none", "incomplete", "returned"),
        ("background_error", "200", "complete", "error"),
    ],
)
def test_asgi_outcomes(mode: str, status: str, completion: str, execution: str) -> None:
    metrics = create_metrics()
    sent: list[Message] = []
    times = iter([10.0, 10.25])

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if mode == "cancelled":
            raise asyncio.CancelledError
        if mode == "disconnected":
            assert await receive() == {"type": "http.disconnect"}
            return
        if mode == "incomplete":
            return
        await send({"type": "http.response.start", "status": 200, "headers": []})
        if mode == "body_error":
            raise ValueError("body error")
        await send({"type": "http.response.body", "body": b"ok"})
        if mode == "background_error":
            raise ValueError("background error")

    async def receive_disconnect() -> Message:
        return {"type": "http.disconnect"}

    async def send_or_fail(message: Message) -> None:
        if mode == "send_failed" and message["type"] == "http.response.body":
            raise OSError("send failed")
        sent.append(message)

    observer = HttpObservation(app, metrics, timer=lambda: next(times))
    if execution == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(observer(scope(), receive, send_or_fail))
    elif execution == "error":
        with pytest.raises((ValueError, OSError)):
            asyncio.run(observer(scope(), receive, send_or_fail))
    else:
        asyncio.run(observer(scope(), receive_disconnect, send_or_fail))
    dimensions = labels(status=status, completion=completion, execution=execution)
    assert sample(metrics, "http_requests_total", dimensions) == 1
    assert sample(metrics, "http_request_duration_seconds_sum", dimensions) == 0.25
    assert len([m for m in sent if m["type"] == "http.response.start"]) <= 1


def test_concurrent_cancellation_does_not_change_other_request() -> None:
    async def scenario() -> None:
        metrics = create_metrics()
        started = asyncio.Event()

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["method"] == "POST":
                started.set()
                await asyncio.Future()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        observer = HttpObservation(app, metrics)
        cancelled = asyncio.create_task(observer(scope("POST"), receive, send))
        await asyncio.wait_for(started.wait(), timeout=2)
        await observer(scope("arbitrary-client-method"), receive, send)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert sample(metrics, "http_requests_total", labels(method="OTHER")) == 1
        assert (
            sample(
                metrics,
                "http_requests_total",
                labels(
                    method="POST",
                    status="none",
                    completion="cancelled",
                    execution="cancelled",
                ),
            )
            == 1
        )

    asyncio.run(scenario())


@pytest.mark.parametrize("failing_app", [False, True])
def test_metric_failure_preserves_response_or_original_exception(
    failing_app: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(Settings())
    metrics = cast(HttpMetrics, app.state.metrics)
    original = ValueError("original")
    monkeypatch.setattr(
        metrics.requests, "labels", Mock(side_effect=RuntimeError("metrics failure"))
    )

    @app.get("/test/error")
    def fail() -> None:
        raise original

    with TestClient(HttpObservation(app, metrics)) as client:
        if failing_app:
            with pytest.raises(ValueError) as caught:
                client.get("/test/error")
            assert caught.value is original
        else:
            assert client.get("/").status_code == 200
        assert client.get("/metrics").status_code == 503
    assert metrics.failed is True


def test_exposition_failure_is_not_reported_as_empty_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "template_fastcrud_api.routers.metrics.generate_latest",
        Mock(side_effect=RuntimeError("broken exporter")),
    )
    app = create_app(Settings())
    with TestClient(HttpObservation(app, app.state.metrics)) as client:
        assert client.get("/metrics").status_code == 503
        assert client.get("/").status_code == 200

import asyncio
from contextlib import AsyncExitStack

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.settings import Settings


def test_health_and_cleanup_order() -> None:
    events: list[str] = []

    async def cleanup(app: FastAPI, name: str) -> None:
        assert app.state.ready is False
        events.append(name)

    async def prepare(app: FastAPI, stack: AsyncExitStack) -> None:
        assert app.state.ready is False
        events.append("prepare")
        stack.push_async_callback(cleanup, app, "close-a")
        stack.push_async_callback(cleanup, app, "close-b")

    app = create_app(Settings(), prepare=prepare)
    assert events == []
    # lifespan 시작 없이 ASGI를 직접 호출하여 준비 전 상태를 확인합니다.
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503
    with client:
        assert client.get("/health/ready").json() == {"status": "ready"}
    assert app.state.ready is False
    assert events == ["prepare", "close-b", "close-a"]


def test_partial_startup_failure_preserves_original_and_attempts_all_cleanup() -> None:
    events: list[str] = []
    original = RuntimeError("startup failed")

    async def close_a() -> None:
        events.append("a")

    async def close_b() -> None:
        events.append("b")
        raise ValueError("cleanup failed")

    async def prepare(app: FastAPI, stack: AsyncExitStack) -> None:
        stack.push_async_callback(close_a)
        stack.push_async_callback(close_b)
        raise original

    app = create_app(Settings(), prepare=prepare)
    with pytest.raises(RuntimeError) as caught, TestClient(app):
        pytest.fail("startup must fail")
    assert caught.value is original
    assert isinstance(caught.value.__cause__, ValueError)
    assert events == ["b", "a"]
    assert app.state.ready is False


def test_shutdown_cleanup_failure_keeps_not_ready() -> None:
    async def close() -> None:
        raise ValueError("cleanup failed")

    async def prepare(app: FastAPI, stack: AsyncExitStack) -> None:
        stack.push_async_callback(close)

    app = create_app(Settings(), prepare=prepare)
    with pytest.raises(ValueError, match="cleanup failed"), TestClient(app):
        assert app.state.ready is True
    assert app.state.ready is False


@pytest.mark.parametrize("cancel_during_startup", [True, False])
def test_cancellation_cleans_resources(cancel_during_startup: bool) -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        events: list[str] = []

        async def close() -> None:
            events.append("closed")

        async def prepare(app: FastAPI, stack: AsyncExitStack) -> None:
            stack.push_async_callback(close)
            if cancel_during_startup:
                entered.set()
                await asyncio.Future()

        app = create_app(Settings(), prepare=prepare)

        async def run_lifespan() -> None:
            async with app.router.lifespan_context(app):
                entered.set()
                await asyncio.Future()

        task = asyncio.create_task(run_lifespan())
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert events == ["closed"]
        assert app.state.ready is False

    asyncio.run(scenario())


def test_app_readiness_is_independent() -> None:
    first = create_app(Settings())
    second = create_app(Settings())
    with TestClient(first):
        assert first.state.ready is True
        assert second.state.ready is False
        with TestClient(second):
            assert second.state.ready is True
        assert first.state.ready is True
        assert second.state.ready is False
    assert first.state.ready is False

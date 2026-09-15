import json
import os
import selectors
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import insert, text
from sqlalchemy.engine import make_url
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.models.reservations import ProductModel, ReservationModel
from template_fastcrud_api.repositories.reservations import product_crud


def database_state(url: str) -> tuple[int, int, int]:
    with closing(sqlite3.connect(str(make_url(url).database))) as connection:
        return (
            connection.execute(
                "SELECT available FROM products WHERE id='demo'"
            ).fetchone()[0],
            connection.execute("SELECT count(*) FROM reservations").fetchone()[0],
            connection.execute("SELECT count(*) FROM idempotency_keys").fetchone()[0],
        )


def test_seed_cli_preserves_existing_stock(database_url: str) -> None:
    def seed(stock: int):
        process = subprocess.run(
            [sys.executable, "-m", "template_fastcrud_api.seed", "--stock", str(stock)],
            env={**os.environ, "DB_PRIMARY_URL": database_url},
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert process.returncode == 0, process.stderr
        return json.loads(process.stdout)

    assert seed(2) == {"product_id": "demo", "available": 2}
    with TestClient(create_app(Settings(db_primary_url=database_url))) as api:
        assert (
            api.post(
                "/v1/reservations",
                json={"product_id": "demo"},
                headers={"Idempotency-Key": "first"},
            ).status_code
            == 201
        )
    assert seed(100) == {"product_id": "demo", "available": 1}
    assert database_state(database_url) == (1, 1, 1)


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    app = create_app(Settings(db_primary_url=database_url))

    async def seed():
        async with app.state.primary_engine.begin() as connection:
            await connection.execute(
                insert(ProductModel),
                [{"id": "demo", "available": 1}, {"id": "other", "available": 1}],
            )

    with TestClient(
        app, raise_server_exceptions=False, headers={"Idempotency-Key": "test-key"}
    ) as test_client:
        assert test_client.portal is not None
        test_client.portal.call(seed)
        yield test_client


def test_sequential_reservation_and_sold_out(
    client: TestClient, database_url: str
) -> None:
    first = client.post("/v1/reservations", json={"product_id": "demo"})
    assert first.status_code == 201
    assert first.json()["data"]["product_id"] == "demo"
    second = client.post(
        "/v1/reservations",
        json={"product_id": "demo"},
        headers={"Idempotency-Key": "second-key"},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "SOLD_OUT"
    assert database_state(database_url) == (0, 1, 1)


def test_validation_and_missing_product(client: TestClient) -> None:
    for body in (
        {},
        {"product_id": ""},
        {"product_id": "demo", "quantity": 2},
        {"product_id": 3},
    ):
        assert client.post("/v1/reservations", json=body).status_code == 422
    response = client.post("/v1/reservations", json={"product_id": "missing"})
    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"
    schema = client.get("/openapi.json").json()
    responses = schema["paths"]["/v1/reservations"]["post"]["responses"]
    for code in (404, 409, 422, 500, 503):
        assert "application/problem+json" in responses[str(code)]["content"]


def test_save_failure_rolls_back_stock(
    client: TestClient, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import template_fastcrud_api.services.reservations as service

    original = service.save_reservation

    async def fail(session, reservation):
        await original(session, reservation)
        raise RuntimeError("synthetic-private-error")

    monkeypatch.setattr(service, "save_reservation", fail)
    response = client.post("/v1/reservations", json={"product_id": "demo"})
    assert response.status_code == 500
    assert "synthetic-private-error" not in response.text
    assert database_state(database_url) == (1, 0, 0)
    metrics = client.get("/metrics").text
    assert 'db_transactions_total{outcome="failed",role="primary"} 1.0' in metrics


def test_commit_failure_rolls_back_and_same_key_can_retry(
    client: TestClient, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import template_fastcrud_api.services.reservations as service

    original = service.save_idempotency

    async def invalid_deferred_fk(session, key, reservation):
        await original(session, key, reservation)
        # Actual SQLite constraint failure at COMMIT, after all business writes.
        await session.execute(text("PRAGMA defer_foreign_keys=ON"))
        await session.execute(
            insert(ReservationModel).values(
                id="invalid-fk",
                product_id="missing",
                created_at=reservation.created_at.isoformat(),
            )
        )

    monkeypatch.setattr(service, "save_idempotency", invalid_deferred_fk)
    failed = client.post("/v1/reservations", json={"product_id": "demo"})
    assert failed.status_code == 500
    assert database_state(database_url) == (1, 0, 0)
    metrics = client.get("/metrics").text
    assert 'db_transactions_total{outcome="failed",role="primary"} 1.0' in metrics
    assert 'db_transactions_total{outcome="committed",role="primary"} 0.0' in metrics
    monkeypatch.setattr(service, "save_idempotency", original)
    retried = client.post("/v1/reservations", json={"product_id": "demo"})
    assert retried.status_code == 201
    assert retried.headers["Idempotency-Replayed"] == "false"
    assert database_state(database_url) == (0, 1, 1)


@pytest.mark.parametrize("requests", [2, 12])
def test_concurrent_requests_across_apps(
    client: TestClient, database_url: str, requests: int
) -> None:
    other_app = create_app(Settings(db_primary_url=database_url))
    barrier = Barrier(requests)
    with (
        TestClient(other_app) as other,
        ThreadPoolExecutor(max_workers=requests) as executor,
    ):

        def call(index: int):
            barrier.wait(timeout=5)
            return (client if index % 2 else other).post(
                "/v1/reservations",
                json={"product_id": "demo"},
                headers={"Idempotency-Key": f"race-{index}"},
            )

        results = list(executor.map(call, range(requests)))
    assert [r.status_code for r in results].count(201) == 1
    assert [r.status_code for r in results].count(409) == requests - 1
    assert all(r.status_code == 201 or r.json()["code"] == "SOLD_OUT" for r in results)
    assert database_state(database_url) == (0, 1, 1)


def test_lock_timeout_is_retryable_not_sold_out(
    client: TestClient, database_url: str
) -> None:
    app = create_app(
        Settings(db_primary_url=database_url, db_sqlite_busy_timeout_seconds=0.02)
    )
    with (
        TestClient(app, headers={"Idempotency-Key": "retry-key"}) as api,
        closing(sqlite3.connect(str(make_url(database_url).database))) as locked,
    ):
        locked.execute("BEGIN IMMEDIATE")
        try:
            response = api.post("/v1/reservations", json={"product_id": "demo"})
            assert response.status_code == 503
            assert response.json()["code"] == "DATABASE_BUSY"
            assert response.headers["Retry-After"] == "1"
            assert database_state(database_url) == (1, 0, 0)
        finally:
            locked.rollback()
        assert (
            api.post("/v1/reservations", json={"product_id": "demo"}).status_code == 201
        )


def test_pool_timeout_is_retryable(client: TestClient, database_url: str) -> None:
    app = create_app(
        Settings(
            db_primary_url=database_url, db_pool_size=1, db_pool_timeout_seconds=0.02
        )
    )

    async def occupy():
        return await app.state.primary_engine.connect()

    with TestClient(app, headers={"Idempotency-Key": "retry-key"}) as api:
        assert api.portal is not None
        connection = api.portal.call(occupy)
        try:
            response = api.post("/v1/reservations", json={"product_id": "demo"})
            assert response.status_code == 503
            assert response.json()["code"] == "DATABASE_POOL_TIMEOUT"
            assert database_state(database_url) == (1, 0, 0)
        finally:
            api.portal.call(connection.close)
        assert (
            api.post("/v1/reservations", json={"product_id": "demo"}).status_code == 201
        )


def test_replay_and_conflicting_input(client: TestClient, database_url: str) -> None:
    first = client.post("/v1/reservations", json={"product_id": "demo"})
    replay = client.post("/v1/reservations", json={"product_id": "demo"})
    assert first.status_code == replay.status_code == 201
    assert first.content == replay.content
    assert first.headers["Idempotency-Replayed"] == "false"
    assert replay.headers["Idempotency-Replayed"] == "true"
    conflict = client.post("/v1/reservations", json={"product_id": "other"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert database_state(database_url) == (0, 1, 1)


def test_deleted_product_still_replays_committed_key_but_rejects_new_key(
    client: TestClient, database_url: str
) -> None:
    first = client.post("/v1/reservations", json={"product_id": "demo"})
    assert first.status_code == 201

    async def delete_product() -> None:
        app = cast(FastAPI, client.app)
        async with app.state.primary_session_factory() as session:
            async with session.begin():
                await product_crud.delete(db=session, commit=False, id="demo")

    assert client.portal is not None
    client.portal.call(delete_product)
    replay = client.post("/v1/reservations", json={"product_id": "demo"})
    assert replay.status_code == 201
    assert replay.content == first.content
    assert replay.headers["Idempotency-Replayed"] == "true"

    missing = client.post(
        "/v1/reservations",
        json={"product_id": "demo"},
        headers={"Idempotency-Key": "after-delete"},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "PRODUCT_NOT_FOUND"
    assert database_state(database_url) == (0, 1, 1)


def test_idempotency_save_failure_and_retry(
    client: TestClient, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import template_fastcrud_api.services.reservations as service

    original = service.save_idempotency

    async def fail(session, key, reservation):
        await original(session, key, reservation)
        raise RuntimeError("after key save")

    monkeypatch.setattr(service, "save_idempotency", fail)
    assert (
        client.post("/v1/reservations", json={"product_id": "demo"}).status_code == 500
    )
    assert database_state(database_url) == (1, 0, 0)
    monkeypatch.setattr(service, "save_idempotency", original)
    assert (
        client.post("/v1/reservations", json={"product_id": "demo"}).status_code == 201
    )
    assert database_state(database_url) == (0, 1, 1)


def test_idempotency_header_validation(client: TestClient, database_url: str) -> None:
    for key in ("", "a" * 129, "invalid spaces"):
        assert (
            client.post(
                "/v1/reservations",
                json={"product_id": "demo"},
                headers={"Idempotency-Key": key},
            ).status_code
            == 422
        )
    del client.headers["Idempotency-Key"]
    assert (
        client.post("/v1/reservations", json={"product_id": "demo"}).status_code == 422
    )
    assert database_state(database_url) == (1, 0, 0)


def test_same_key_concurrent_replay(client: TestClient, database_url: str) -> None:
    barrier = Barrier(12)
    with (
        TestClient(create_app(Settings(db_primary_url=database_url))) as other,
        ThreadPoolExecutor(max_workers=12) as executor,
    ):

        def call(index):
            barrier.wait(timeout=5)
            return (client if index % 2 else other).post(
                "/v1/reservations",
                json={"product_id": "demo"},
                headers={"Idempotency-Key": "shared"},
            )

        responses = list(executor.map(call, range(12)))
    assert all(r.status_code == 201 for r in responses)
    assert len({r.content for r in responses}) == 1
    assert [r.headers["Idempotency-Replayed"] for r in responses].count("false") == 1
    assert database_state(database_url) == (0, 1, 1)


def test_same_key_different_input_race(client: TestClient, database_url: str) -> None:
    barrier = Barrier(2)

    def call(product):
        barrier.wait(timeout=5)
        return client.post(
            "/v1/reservations",
            json={"product_id": product},
            headers={"Idempotency-Key": "shared"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(call, ["demo", "other"]))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert (
        next(r for r in responses if r.status_code == 409).json()["code"]
        == "IDEMPOTENCY_CONFLICT"
    )
    with closing(sqlite3.connect(str(make_url(database_url).database))) as connection:
        assert (
            connection.execute("SELECT sum(available) FROM products").fetchone()[0] == 1
        )
    assert database_state(database_url)[1:] == (1, 1)


class DropSuccessResponse:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.body = b""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        successful = False

        async def drop(message: Message) -> None:
            nonlocal successful
            if message["type"] == "http.response.start":
                successful = message["status"] == 201
            if successful and message["type"] == "http.response.body":
                self.body = message["body"]
                raise ConnectionResetError("test response loss after commit")
            await send(message)

        await self.app(scope, receive, drop)


def test_response_loss_then_restart_replays(
    client: TestClient, database_url: str
) -> None:
    broken = DropSuccessResponse(create_app(Settings(db_primary_url=database_url)))
    with TestClient(broken) as failing:
        with pytest.raises(ConnectionResetError):
            failing.post(
                "/v1/reservations",
                json={"product_id": "demo"},
                headers={"Idempotency-Key": "lost"},
            )
    assert database_state(database_url) == (0, 1, 1)
    with TestClient(create_app(Settings(db_primary_url=database_url))) as restarted:
        replay = restarted.post(
            "/v1/reservations",
            json={"product_id": "demo"},
            headers={"Idempotency-Key": "lost"},
        )
        assert replay.status_code == 201
        assert replay.content == broken.body
        assert replay.headers["Idempotency-Replayed"] == "true"
    assert database_state(database_url) == (0, 1, 1)


@pytest.mark.parametrize("mode", ["before_commit", "after_commit"])
def test_process_crash_and_retry(
    client: TestClient, database_url: str, mode: str
) -> None:
    worker = Path(__file__).with_name("process_worker.py")
    process = subprocess.run(
        [sys.executable, str(worker), database_url, "crash", mode],
        input="go\n",
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert process.returncode == (23 if mode == "before_commit" else 24), process.stderr
    assert database_state(database_url) == (
        (1, 0, 0) if mode == "before_commit" else (0, 1, 1)
    )
    response = client.post(
        "/v1/reservations",
        json={"product_id": "demo"},
        headers={"Idempotency-Key": "crash"},
    )
    assert response.status_code == 201
    assert response.headers["Idempotency-Replayed"] == (
        "false" if mode == "before_commit" else "true"
    )
    assert database_state(database_url) == (0, 1, 1)


@pytest.mark.parametrize("same_key", [False, True])
def test_independent_processes(
    client: TestClient, database_url: str, same_key: bool
) -> None:
    worker = Path(__file__).with_name("process_worker.py")
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                str(worker),
                database_url,
                "shared" if same_key else f"key-{i}",
                "normal",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(2)
    ]
    try:
        with selectors.DefaultSelector() as selector:
            for process in processes:
                assert process.stdout is not None
                selector.register(process.stdout, selectors.EVENT_READ, process.stdout)
            while selector.get_map():
                ready = selector.select(timeout=10)
                assert ready, "workers did not become ready"
                for stream, _ in ready:
                    assert stream.data.readline().strip() == "ready"
                    selector.unregister(stream.fileobj)
        for process in processes:
            assert process.stdin is not None
            process.stdin.write("go\n")
            process.stdin.flush()
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stderr
            results.append(json.loads(stdout.splitlines()[-1]))
        assert sum(r["status"] == "ok" for r in results) == (2 if same_key else 1)
        if same_key:
            assert results[0]["reservation"] == results[1]["reservation"]
            assert sorted(r["replayed"] for r in results) == [False, True]
        assert database_state(database_url) == (0, 1, 1)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate()

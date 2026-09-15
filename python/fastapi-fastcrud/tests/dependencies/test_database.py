import asyncio
import sys
from pathlib import Path
from time import monotonic

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.contracts.database import TransactionOutcome
from template_fastcrud_api.core.database import (
    acquire_primary_connection,
    primary_session,
)
from template_fastcrud_api.core.database_metrics import DatabaseMetrics
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.dependencies.database import (
    DatabaseMetricsDep,
    PrimarySessionDep,
)


async def write_sample(
    session: AsyncSession,
    metrics: DatabaseMetrics,
    *,
    fail: bool = False,
    bad_fk: bool = False,
) -> None:
    """Test-only business: explicit transaction, no automatic commit dependency."""
    started = monotonic()
    outcome = TransactionOutcome.FAILED
    body_error: BaseException | None = None
    try:
        async with session.begin():
            try:
                await acquire_primary_connection(session, metrics)
                await session.execute(text("INSERT INTO parent VALUES (1)"))
                await session.execute(
                    text("INSERT INTO child VALUES (:id)"), {"id": 9 if bad_fk else 1}
                )
                if fail:
                    raise ValueError("business failed")
            except BaseException as error:
                body_error = error
                raise
        outcome = TransactionOutcome.COMMITTED
    except BaseException as error:
        if error is body_error:
            outcome = TransactionOutcome.ROLLED_BACK
        raise
    finally:
        metrics.record_transaction(outcome, monotonic() - started)


async def schema(app: FastAPI) -> None:
    async with app.state.primary_engine.begin() as conn:
        await conn.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        await conn.execute(
            text(
                "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)"
            )
        )


def sample(app: FastAPI, name: str, **labels: str) -> float | None:
    return app.state.metrics.registry.get_sample_value(
        name, {"role": "primary", **labels}
    )


@pytest.mark.parametrize(
    "mode", ["success", "body_failure", "commit_failure", "rollback_failure"]
)
def test_atomic_business_and_finalized_metrics(tmp_path: Path, mode: str) -> None:
    async def scenario():
        app = create_app(
            Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/atomic.db")
        )
        async with app.router.lifespan_context(app):
            await schema(app)
            engine = app.state.primary_engine

            def broken_rollback(connection):
                raise RuntimeError("rollback failed")

            if mode == "rollback_failure":
                event.listen(engine.sync_engine, "rollback", broken_rollback)
            try:
                async with primary_session(
                    app.state.primary_session_factory, app.state.database_metrics
                ) as session:
                    call = write_sample(
                        session,
                        app.state.database_metrics,
                        fail=mode in ("body_failure", "rollback_failure"),
                        bad_fk=mode == "commit_failure",
                    )
                    if mode == "success":
                        await call
                    else:
                        error_type = {
                            "body_failure": ValueError,
                            "commit_failure": IntegrityError,
                            "rollback_failure": RuntimeError,
                        }[mode]
                        with pytest.raises(error_type):
                            await call
            finally:
                if mode == "rollback_failure":
                    event.remove(engine.sync_engine, "rollback", broken_rollback)
            async with engine.connect() as conn:
                assert await conn.scalar(text("SELECT count(*) FROM parent")) == (
                    1 if mode == "success" else 0
                )
                assert await conn.scalar(text("SELECT count(*) FROM child")) == (
                    1 if mode == "success" else 0
                )
            outcome = {"success": "committed", "body_failure": "rolled_back"}.get(
                mode, "failed"
            )
            assert sample(app, "db_transactions_total", outcome=outcome) == 1
            if mode != "success":
                assert sample(app, "db_transactions_total", outcome="committed") == 0
            assert sample(app, "db_sessions_active") == 0
            assert sample(app, "db_pool_connections_in_use") == 0

    asyncio.run(scenario())


def test_pool_timeout_cancellation_and_recovery(tmp_path: Path) -> None:
    async def scenario():
        app = create_app(
            Settings(
                db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/pool.db",
                db_pool_size=1,
                db_pool_timeout_seconds=0.03,
            )
        )
        async with app.router.lifespan_context(app):
            factory, metrics = (
                app.state.primary_session_factory,
                app.state.database_metrics,
            )
            async with primary_session(factory, metrics) as first:
                assert not first.in_transaction()
                assert sample(app, "db_sessions_active") == 1
                assert sample(app, "db_pool_connections_in_use") == 0
                async with first.begin():
                    await acquire_primary_connection(first, metrics)
                    async with primary_session(factory, metrics) as second:
                        assert first is not second
                        with pytest.raises(TimeoutError):
                            async with second.begin():
                                await acquire_primary_connection(second, metrics)
            assert sample(app, "db_pool_timeouts_total") == 1
            entered = asyncio.Event()

            async def hold():
                async with (
                    primary_session(factory, metrics) as session,
                    session.begin(),
                ):
                    await acquire_primary_connection(session, metrics)
                    entered.set()
                    await asyncio.Future()

            task = asyncio.create_task(hold())
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert sample(app, "db_sessions_active") == 0
            assert sample(app, "db_pool_connections_in_use") == 0
            async with primary_session(factory, metrics) as session, session.begin():
                await acquire_primary_connection(session, metrics)
                assert await session.scalar(text("SELECT 1")) == 1
            assert (
                sample(app, "db_connection_acquire_seconds_count", outcome="timeout")
                == 1
            )

    asyncio.run(scenario())


def test_dependency_cleanup_and_commit_failure_response(tmp_path: Path) -> None:
    app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/http.db"))
    sessions = []

    @app.post("/test/write")
    async def write(session: PrimarySessionDep, metrics: DatabaseMetricsDep):
        assert not session.in_transaction()
        sessions.append(session)
        await write_sample(session, metrics, bad_fk=True)
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.portal is not None
        client.portal.call(schema, app)
        assert client.post("/test/write").status_code == 500
        assert client.post("/test/write").status_code == 500
        assert sessions[0] is not sessions[1]
        assert sample(app, "db_sessions_active") == 0
        assert sample(app, "db_pool_connections_in_use") == 0
        assert sample(app, "db_transactions_total", outcome="failed") == 2


def test_sqlite_lock_is_not_pool_timeout(tmp_path: Path) -> None:
    async def scenario():
        app = create_app(
            Settings(
                db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/lock.db",
                db_sqlite_busy_timeout_seconds=0.02,
            )
        )
        async with app.router.lifespan_context(app):
            await schema(app)
            factory, metrics = (
                app.state.primary_session_factory,
                app.state.database_metrics,
            )
            async with primary_session(factory, metrics) as first, first.begin():
                await first.execute(text("INSERT INTO parent VALUES (3)"))
                async with primary_session(factory, metrics) as second:
                    with pytest.raises(OperationalError, match="locked"):
                        await write_sample(second, metrics)
            assert sample(app, "db_pool_timeouts_total") == 0
            assert sample(app, "db_pool_connections_in_use") == 0

    asyncio.run(scenario())


def test_business_cancellation_records_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        app = create_app(
            Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/cancel.db")
        )
        entered = asyncio.Event()

        async def pause(session, metrics):
            await original(session, metrics)
            await session.execute(text("INSERT INTO parent VALUES (7)"))
            entered.set()
            await asyncio.Future()

        monkeypatch.setattr(sys.modules[__name__], "acquire_primary_connection", pause)
        async with app.router.lifespan_context(app):
            await schema(app)

            async def run():
                async with primary_session(
                    app.state.primary_session_factory, app.state.database_metrics
                ) as session:
                    await write_sample(session, app.state.database_metrics)

            task = asyncio.create_task(run())
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert sample(app, "db_transactions_total", outcome="rolled_back") == 1
            assert sample(app, "db_sessions_active") == 0
            assert sample(app, "db_pool_connections_in_use") == 0
            async with app.state.primary_engine.connect() as connection:
                assert await connection.scalar(text("SELECT count(*) FROM parent")) == 0

    original = acquire_primary_connection
    asyncio.run(scenario())

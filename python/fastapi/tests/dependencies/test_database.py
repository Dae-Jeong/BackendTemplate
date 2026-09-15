import asyncio
from inspect import signature
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from template_api.bootstrap.app import create_app
from template_api.core.database import primary_session
from template_api.core.database_metrics import DatabaseMetrics
from template_api.core.settings import Settings
from template_api.core.transactions import transactional
from template_api.dependencies.database import DatabaseMetricsDep, PrimarySessionDep
from template_api.exceptions.database import (
    ConcurrentTransactionUse,
    DatabaseBusy,
    DatabasePoolTimeout,
    TransactionOwnershipError,
    TransactionRollbackOnly,
)


@transactional
async def write_sample(
    *,
    session: AsyncSession,
    metrics: DatabaseMetrics,
    value: int,
    error: BaseException | None = None,
) -> int:
    await session.execute(text("INSERT INTO samples VALUES (:value)"), {"value": value})
    if error is not None:
        raise error
    return value


@transactional
async def nested_success(
    *, session: AsyncSession, metrics: DatabaseMetrics, value: int
) -> int:
    await write_sample(session=session, metrics=metrics, value=value)
    return await write_sample(session=session, metrics=metrics, value=value + 1)


@transactional
async def catches_nested_failure(
    *, session: AsyncSession, metrics: DatabaseMetrics
) -> None:
    await write_sample(session=session, metrics=metrics, value=1)
    failure = ValueError("inner failed")
    try:
        await write_sample(session=session, metrics=metrics, value=2, error=failure)
    except ValueError as error:
        assert error is failure
    await write_sample(session=session, metrics=metrics, value=3)


async def create_schema(app) -> None:
    async with app.state.primary_engine.begin() as connection:
        await connection.execute(
            text("CREATE TABLE samples (value INTEGER PRIMARY KEY)")
        )
        await connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        await connection.execute(
            text(
                "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id) "
                "DEFERRABLE INITIALLY DEFERRED)"
            )
        )


def sample(app, name: str, outcome: str) -> float | None:
    return app.state.metrics.registry.get_sample_value(
        name, {"role": "primary", "outcome": outcome}
    )


def gauge(app, name: str) -> float | None:
    return app.state.metrics.registry.get_sample_value(name, {"role": "primary"})


async def sample_count(app) -> int:
    async with app.state.primary_engine.connect() as connection:
        return await connection.scalar(text("SELECT count(*) FROM samples")) or 0


def test_decorator_preserves_signature_and_requires_explicit_contract() -> None:
    assert tuple(signature(write_sample).parameters) == (
        "session",
        "metrics",
        "value",
        "error",
    )
    with pytest.raises(TypeError, match="keyword-only session"):

        @transactional
        async def invalid(session: AsyncSession, *, metrics: DatabaseMetrics) -> None:
            pass


def test_nested_success_commits_and_records_once(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"))
        async with app.router.lifespan_context(app):
            await create_schema(app)
            async with primary_session(
                app.state.primary_session_factory, app.state.database_metrics
            ) as session:
                assert (
                    await nested_success(
                        session=session, metrics=app.state.database_metrics, value=1
                    )
                    == 2
                )
                assert not session.in_transaction()
            assert await sample_count(app) == 2
            assert sample(app, "db_transactions_total", "committed") == 1
            assert sample(app, "db_transactions_total", "failed") == 0

    asyncio.run(scenario())


def test_caught_nested_failure_marks_outer_rollback_only(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"))
        async with app.router.lifespan_context(app):
            await create_schema(app)
            async with primary_session(
                app.state.primary_session_factory, app.state.database_metrics
            ) as session:
                with pytest.raises(TransactionRollbackOnly) as caught:
                    await catches_nested_failure(
                        session=session, metrics=app.state.database_metrics
                    )
                assert isinstance(caught.value.__cause__, ValueError)
            assert await sample_count(app) == 0
            assert sample(app, "db_transactions_total", "failed") == 1

    asyncio.run(scenario())


def test_uncaught_failure_rolls_back_and_preserves_identity(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"))
        failure = LookupError("business failed")
        async with app.router.lifespan_context(app):
            await create_schema(app)
            async with primary_session(
                app.state.primary_session_factory, app.state.database_metrics
            ) as session:
                with pytest.raises(LookupError) as caught:
                    await write_sample(
                        session=session,
                        metrics=app.state.database_metrics,
                        value=1,
                        error=failure,
                    )
                assert caught.value is failure
            assert await sample_count(app) == 0
            assert sample(app, "db_transactions_total", "failed") == 1

    asyncio.run(scenario())


def test_autobegin_conflict_leaves_caller_transaction_untouched(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"))
        async with app.router.lifespan_context(app):
            await create_schema(app)
            async with primary_session(
                app.state.primary_session_factory, app.state.database_metrics
            ) as session:
                await session.execute(text("INSERT INTO samples VALUES (9)"))
                transaction = session.get_transaction()
                with pytest.raises(TransactionOwnershipError):
                    await write_sample(
                        session=session, metrics=app.state.database_metrics, value=10
                    )
                assert session.get_transaction() is transaction
                assert await session.scalar(text("SELECT count(*) FROM samples")) == 1
                await session.rollback()
            assert await sample_count(app) == 0
            assert sample(app, "db_transactions_total", "failed") == 0

    asyncio.run(scenario())


def test_sequential_reuse_of_session(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"))
        async with app.router.lifespan_context(app):
            await create_schema(app)
            async with primary_session(
                app.state.primary_session_factory, app.state.database_metrics
            ) as session:
                for value in (1, 2):
                    assert (
                        await write_sample(
                            session=session,
                            metrics=app.state.database_metrics,
                            value=value,
                        )
                        == value
                    )
            assert await sample_count(app) == 2
            assert sample(app, "db_transactions_total", "committed") == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["commit", "rollback"])
def test_finalization_failure_is_failed(tmp_path: Path, mode: str) -> None:
    async def scenario() -> None:
        app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"))
        async with app.router.lifespan_context(app):
            await create_schema(app)
            engine = app.state.primary_engine

            def broken_rollback(connection) -> None:
                raise RuntimeError("rollback failed")

            if mode == "rollback":
                event.listen(engine.sync_engine, "rollback", broken_rollback)
            try:
                async with primary_session(
                    app.state.primary_session_factory, app.state.database_metrics
                ) as session:
                    if mode == "commit":

                        @transactional
                        async def invalid_fk(
                            *, session: AsyncSession, metrics: DatabaseMetrics
                        ) -> None:
                            await session.execute(text("INSERT INTO parent VALUES (1)"))
                            await session.execute(text("INSERT INTO child VALUES (9)"))

                        with pytest.raises(IntegrityError):
                            await invalid_fk(
                                session=session, metrics=app.state.database_metrics
                            )
                    else:
                        with pytest.raises(RuntimeError, match="rollback failed"):
                            await write_sample(
                                session=session,
                                metrics=app.state.database_metrics,
                                value=1,
                                error=ValueError("business failed"),
                            )
            finally:
                if mode == "rollback":
                    event.remove(engine.sync_engine, "rollback", broken_rollback)
            async with engine.connect() as connection:
                assert await connection.scalar(text("SELECT count(*) FROM parent")) == 0
                assert await connection.scalar(text("SELECT count(*) FROM child")) == 0
            assert sample(app, "db_transactions_total", "failed") == 1
            assert sample(app, "db_transactions_total", "committed") == 0

    asyncio.run(scenario())


def test_cancellation_allows_sequential_reuse(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"))
        entered = asyncio.Event()

        @transactional
        async def pause(*, session: AsyncSession, metrics: DatabaseMetrics) -> None:
            await session.execute(text("INSERT INTO samples VALUES (1)"))
            entered.set()
            await asyncio.Future()

        async with app.router.lifespan_context(app):
            await create_schema(app)
            async with primary_session(
                app.state.primary_session_factory, app.state.database_metrics
            ) as session:
                task = asyncio.create_task(
                    pause(session=session, metrics=app.state.database_metrics)
                )
                await asyncio.wait_for(entered.wait(), 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert not session.in_transaction()
                assert (
                    await write_sample(
                        session=session, metrics=app.state.database_metrics, value=2
                    )
                    == 2
                )
            assert await sample_count(app) == 1
            assert sample(app, "db_transactions_total", "failed") == 1
            assert sample(app, "db_transactions_total", "committed") == 1
            assert gauge(app, "db_sessions_active") == 0
            assert gauge(app, "db_pool_connections_in_use") == 0

    asyncio.run(scenario())


def test_concurrent_task_reuse_does_not_corrupt_owner(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"))
        entered = asyncio.Event()
        release = asyncio.Event()

        @transactional
        async def owner(*, session: AsyncSession, metrics: DatabaseMetrics) -> None:
            await session.execute(text("INSERT INTO samples VALUES (1)"))
            entered.set()
            await release.wait()

        async with app.router.lifespan_context(app):
            await create_schema(app)
            async with primary_session(
                app.state.primary_session_factory, app.state.database_metrics
            ) as session:
                task = asyncio.create_task(
                    owner(session=session, metrics=app.state.database_metrics)
                )
                await asyncio.wait_for(entered.wait(), 2)
                with pytest.raises(ConcurrentTransactionUse):
                    await write_sample(
                        session=session, metrics=app.state.database_metrics, value=2
                    )
                release.set()
                await task
            assert await sample_count(app) == 1
            assert sample(app, "db_transactions_total", "committed") == 1
            assert sample(app, "db_transactions_total", "failed") == 0

    asyncio.run(scenario())


def test_pool_timeout_and_sqlite_busy_are_translated(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(
            Settings(
                db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db",
                db_pool_size=1,
                db_pool_timeout_seconds=0.02,
                db_sqlite_busy_timeout_seconds=0.02,
            )
        )
        async with app.router.lifespan_context(app):
            await create_schema(app)
            factory = app.state.primary_session_factory
            metrics = app.state.database_metrics
            async with primary_session(factory, metrics) as first:
                await first.execute(text("SELECT 1"))
                async with primary_session(factory, metrics) as second:
                    with pytest.raises(DatabasePoolTimeout) as timeout:
                        await write_sample(session=second, metrics=metrics, value=1)
                    assert isinstance(timeout.value.__cause__, TimeoutError)
                await first.rollback()
            assert sample(app, "db_transactions_total", "failed") == 1
            assert gauge(app, "db_sessions_active") == 0
            assert gauge(app, "db_pool_connections_in_use") == 0

        busy_app = create_app(
            Settings(
                db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/busy.db",
                db_pool_size=2,
                db_sqlite_busy_timeout_seconds=0.02,
            )
        )
        async with busy_app.router.lifespan_context(busy_app):
            await create_schema(busy_app)
            factory = busy_app.state.primary_session_factory
            metrics = busy_app.state.database_metrics
            async with primary_session(factory, metrics) as first:
                await first.execute(text("INSERT INTO samples VALUES (1)"))
                async with primary_session(factory, metrics) as second:
                    with pytest.raises(DatabaseBusy) as busy:
                        await write_sample(session=second, metrics=metrics, value=2)
                    assert isinstance(busy.value.__cause__, OperationalError)
                await first.rollback()
            assert sample(busy_app, "db_transactions_total", "failed") == 1

    asyncio.run(scenario())


def test_metrics_failure_does_not_replace_result(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"))
        async with app.router.lifespan_context(app):
            await create_schema(app)
            metrics = app.state.database_metrics

            def fail(outcome, seconds) -> None:
                raise RuntimeError("metrics failed")

            metrics.record_transaction = fail
            async with primary_session(
                app.state.primary_session_factory, metrics
            ) as session:
                assert (
                    await write_sample(session=session, metrics=metrics, value=1) == 1
                )
                failure = LookupError("business failed")
                with pytest.raises(LookupError) as caught:
                    await write_sample(
                        session=session,
                        metrics=metrics,
                        value=2,
                        error=failure,
                    )
                assert caught.value is failure
            assert await sample_count(app) == 1

    asyncio.run(scenario())


def test_manual_commit_is_detected(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"))

        @transactional
        async def commits(*, session: AsyncSession, metrics: DatabaseMetrics) -> None:
            await session.execute(text("INSERT INTO samples VALUES (1)"))
            await session.commit()

        async with app.router.lifespan_context(app):
            await create_schema(app)
            async with primary_session(
                app.state.primary_session_factory, app.state.database_metrics
            ) as session:
                with pytest.raises(TransactionOwnershipError):
                    await commits(session=session, metrics=app.state.database_metrics)
            assert sample(app, "db_transactions_total", "failed") == 1
            assert await sample_count(app) == 1

    asyncio.run(scenario())


def test_dependency_cleanup_and_commit_failure_response(tmp_path: Path) -> None:
    app = create_app(Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/http"))
    sessions: list[AsyncSession] = []

    @transactional
    async def invalid_fk(*, session: AsyncSession, metrics: DatabaseMetrics) -> None:
        await session.execute(text("INSERT INTO parent VALUES (1)"))
        await session.execute(text("INSERT INTO child VALUES (9)"))

    @app.post("/test/write")
    async def write(session: PrimarySessionDep, metrics: DatabaseMetricsDep) -> dict:
        assert not session.in_transaction()
        sessions.append(session)
        await invalid_fk(session=session, metrics=metrics)
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.portal is not None
        client.portal.call(create_schema, app)
        assert client.post("/test/write").status_code == 500
        assert client.post("/test/write").status_code == 500
        assert sessions[0] is not sessions[1]
        assert gauge(app, "db_sessions_active") == 0
        assert gauge(app, "db_pool_connections_in_use") == 0
        assert sample(app, "db_transactions_total", "failed") == 2

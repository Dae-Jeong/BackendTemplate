import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, TimeoutError

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.database import create_primary_engine
from template_fastcrud_api.core.database_metrics import create_database_metrics
from template_fastcrud_api.core.metrics import create_metrics
from template_fastcrud_api.core.settings import Settings


def test_pool_lifecycle_and_sqlite_transactions(tmp_path: Path) -> None:
    async def scenario() -> None:
        owner = create_metrics()
        metrics = create_database_metrics(owner, 1)
        engine = create_primary_engine(
            Settings(
                db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/pool.db",
                db_pool_size=1,
                db_pool_timeout_seconds=0.02,
            ),
            metrics,
        )

        def value(name: str) -> float | None:
            return owner.registry.get_sample_value(name, {"role": "primary"})

        try:
            async with engine.connect() as connection:
                assert value("db_pool_connections_in_use") == 1
                assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
                with pytest.raises(TimeoutError):
                    async with engine.connect():
                        pytest.fail("pool must be exhausted")
                await connection.execute(text("CREATE TABLE sample (id INTEGER)"))
                await connection.rollback()
                assert (
                    await connection.scalar(
                        text("SELECT count(*) FROM sqlite_master WHERE name='sample'")
                    )
                    == 0
                )
                await connection.invalidate()
            assert value("db_pool_connections_in_use") == 0
            async with engine.connect() as connection:
                assert await connection.scalar(text("SELECT 1")) == 1
            assert value("db_pool_connections_in_use") == 0
            assert value("db_pool_connection_hold_seconds_count") == 2
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_database_startup_restart_and_app_isolation(tmp_path: Path) -> None:
    settings = Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/app.db")
    first, second = create_app(settings), create_app(settings)
    for _ in range(2):
        with TestClient(first) as client:
            assert client.get("/health/ready").status_code == 200
            assert (
                'db_pool_connections_in_use{role="primary"} 0.0'
                in client.get("/metrics").text
            )
            assert not hasattr(second.state, "primary_engine")
        assert not hasattr(first.state, "primary_session_factory")
    with TestClient(create_app(Settings())) as client:
        assert "db_pool_" not in client.get("/metrics").text


def test_startup_failure_disposes_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import template_fastcrud_api.bootstrap.lifespan as lifecycle

    disposed = []
    original = lifecycle.create_primary_engine

    def create(settings, metrics):
        engine = original(settings, metrics)
        dispose = engine.dispose

        async def close(close=True):
            disposed.append(True)
            await dispose(close=close)

        # Patch class method because AsyncEngine instances have slots.
        async def replacement(self, close=True):
            await close_engine(close)

        close_engine = close
        monkeypatch.setattr(type(engine), "dispose", replacement)
        return engine

    monkeypatch.setattr(lifecycle, "create_primary_engine", create)
    app = create_app(
        Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/missing/db")
    )
    with pytest.raises(OperationalError), TestClient(app):
        pytest.fail("must fail startup")
    assert disposed == [True]
    assert app.state.ready is False


def test_metrics_failure_does_not_break_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario():
        owner = create_metrics()
        metrics = create_database_metrics(owner, 1)

        def fail(*args, **kwargs):
            raise ValueError("metrics failure")

        monkeypatch.setattr(metrics.connections, "inc", fail)
        engine = create_primary_engine(
            Settings(db_primary_url=f"sqlite+aiosqlite:///{tmp_path}/db"), metrics
        )
        try:
            async with engine.connect() as connection:
                assert await connection.scalar(text("SELECT 1")) == 1
            assert owner.failed
        finally:
            await engine.dispose()

    asyncio.run(scenario())

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any, cast

from sqlalchemy import Connection, event
from sqlalchemy.exc import TimeoutError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import ConnectionPoolEntry

from template_fastcrud_api.contracts.database import AcquisitionOutcome
from template_fastcrud_api.core.database_metrics import DatabaseMetrics
from template_fastcrud_api.core.settings import Settings


def create_primary_engine(settings: Settings, metrics: DatabaseMetrics) -> AsyncEngine:
    engine = create_async_engine(
        settings.db_primary_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        connect_args={"timeout": settings.db_sqlite_busy_timeout_seconds},
        hide_parameters=True,
    )

    # aiosqlite adapter supports these synchronous event hooks.
    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(connection: Any, record: ConnectionPoolEntry) -> None:
        connection.isolation_level = None
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def begin(connection: Connection) -> None:
        connection.exec_driver_sql(
            "BEGIN IMMEDIATE"
            if connection.get_execution_options().get("sqlite_write")
            else "BEGIN"
        )

    @event.listens_for(engine.sync_engine, "checkout")
    def checkout(connection: Any, record: ConnectionPoolEntry, proxy: Any) -> None:
        cast(dict[str, Any], record.record_info)["checkout_started"] = monotonic()
        metrics.record(metrics.connections.inc)

    @event.listens_for(engine.sync_engine, "checkin")
    @event.listens_for(engine.sync_engine, "detach")
    def returned(connection: Any, record: ConnectionPoolEntry) -> None:
        started = cast(dict[str, Any], record.record_info).pop("checkout_started", None)
        if started is not None:
            metrics.record(metrics.connections.dec)
            metrics.record(lambda: metrics.hold.observe(monotonic() - started))

    return engine


@asynccontextmanager
async def primary_session(
    factory: async_sessionmaker[AsyncSession], metrics: DatabaseMetrics
) -> AsyncIterator[AsyncSession]:
    metrics.record(metrics.sessions.inc)
    try:
        async with factory() as session:
            yield session
    finally:
        metrics.record(metrics.sessions.dec)


async def acquire_primary_connection(
    session: AsyncSession, metrics: DatabaseMetrics, *, write: bool = False
) -> AsyncConnection:
    """Call once inside the outer business transaction, before its first SQL."""
    if not session.in_transaction():
        raise RuntimeError(
            "Start the business transaction before acquiring a connection"
        )
    started = monotonic()
    outcome = AcquisitionOutcome.FAILED
    try:
        connection = await session.connection(execution_options={"sqlite_write": write})
        outcome = AcquisitionOutcome.ACQUIRED
        return connection
    except TimeoutError:
        outcome = AcquisitionOutcome.TIMEOUT
        raise
    finally:
        metrics.record_acquisition(outcome, monotonic() - started)

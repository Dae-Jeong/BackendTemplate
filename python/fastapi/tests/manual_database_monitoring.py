"""Temporary file DB workload for local monitoring; no business/test HTTP routes.

Run from python/fastapi: uv run python tests/manual_database_monitoring.py
Stop with Ctrl-C. The database is removed after shutdown.
"""

import argparse
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from dependencies.test_database import create_schema, write_sample
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError

from template_api.bootstrap.app import create_app
from template_api.core.database import acquire_primary_connection, primary_session
from template_api.core.settings import Settings


async def workload(app: FastAPI) -> None:
    factory, metrics = app.state.primary_session_factory, app.state.database_metrics
    while True:
        print("phase=idle", flush=True)
        await asyncio.sleep(20)
        async with primary_session(factory, metrics) as session:
            await write_sample(session=session, metrics=metrics, value=1)
        async with app.state.primary_engine.begin() as connection:
            await connection.execute(text("DELETE FROM child"))
            await connection.execute(text("DELETE FROM parent"))
        async with primary_session(factory, metrics) as session:
            try:
                await write_sample(
                    session=session,
                    metrics=metrics,
                    value=1,
                    error=ValueError("monitoring failure"),
                )
            except ValueError:
                pass
        async with primary_session(factory, metrics) as session, session.begin():
            await acquire_primary_connection(session, metrics)
            print("phase=held connections=1 sessions=1", flush=True)
            await asyncio.sleep(20)
            async with primary_session(factory, metrics) as waiting, waiting.begin():
                try:
                    await acquire_primary_connection(waiting, metrics)
                except TimeoutError:
                    print("phase=timeout", flush=True)
            await asyncio.sleep(20)
        print("phase=recovered connections=0 sessions=0", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--without-db", action="store_true")
    args = parser.parse_args()
    if args.without_db:
        uvicorn.run(
            create_app(Settings(db_primary_url="")),
            host="0.0.0.0",
            port=18082,
            access_log=False,
        )
        return
    with TemporaryDirectory(prefix="backend-db-monitor-") as directory:
        app = create_app(
            Settings(
                db_primary_url=f"sqlite+aiosqlite:///{Path(directory) / 'monitor.db'}",
                db_pool_size=1,
                db_pool_timeout_seconds=0.2,
            )
        )
        original = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(application: FastAPI) -> AsyncIterator[None]:
            async with original(application):
                await create_schema(application)
                task = asyncio.create_task(workload(application))
                try:
                    yield
                finally:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        app.router.lifespan_context = lifespan
        uvicorn.run(app, host="0.0.0.0", port=18082, access_log=False)


if __name__ == "__main__":
    main()

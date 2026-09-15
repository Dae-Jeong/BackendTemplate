from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from template_fastcrud_api.core.database import primary_session
from template_fastcrud_api.core.database_metrics import DatabaseMetrics


def get_database_metrics(request: Request) -> DatabaseMetrics:
    return cast(DatabaseMetrics, request.app.state.database_metrics)


async def get_primary_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = cast(
        async_sessionmaker[AsyncSession], request.app.state.primary_session_factory
    )
    async with primary_session(factory, get_database_metrics(request)) as session:
        yield session


PrimarySessionDep = Annotated[
    AsyncSession, Depends(get_primary_session, scope="function")
]
DatabaseMetricsDep = Annotated[DatabaseMetrics, Depends(get_database_metrics)]

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from template_fastcrud_api.bootstrap.contracts import Lifespan, PrepareResources
from template_fastcrud_api.core.database import create_primary_engine
from template_fastcrud_api.core.settings import Settings


async def prepare_resources(
    app: FastAPI, stack: AsyncExitStack, *, settings: Settings
) -> None:
    if not settings.db_primary_url:
        return
    engine = create_primary_engine(settings, app.state.database_metrics)
    stack.push_async_callback(engine.dispose)
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    app.state.primary_engine = engine
    app.state.primary_session_factory = async_sessionmaker(
        engine, expire_on_commit=False
    )
    stack.callback(delattr, app.state, "primary_engine")
    stack.callback(delattr, app.state, "primary_session_factory")


def create_lifespan(prepare: PrepareResources) -> Lifespan:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.ready = False
        stack = AsyncExitStack()
        try:
            await prepare(app, stack)
            app.state.ready = True
            yield
        except BaseException as error:
            # 취소와 초기화 실패도 자원을 정리한 뒤 원래 실패로 전파합니다.
            app.state.ready = False
            try:
                await stack.aclose()
            except BaseException as cleanup_error:
                raise error from cleanup_error
            raise
        else:
            app.state.ready = False
            await stack.aclose()

    return lifespan

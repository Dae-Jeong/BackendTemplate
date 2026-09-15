"""Alembic async template using the application's SQLite configuration."""

import asyncio

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection

from template_fastcrud_api.core.database import create_primary_engine
from template_fastcrud_api.core.database_metrics import create_database_metrics
from template_fastcrud_api.core.metrics import create_metrics
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.models import Base

config = context.config
target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    sqlite_connection = connection.dialect.name == "sqlite"
    if sqlite_connection:
        connection.connection.dbapi_connection.execute("PRAGMA foreign_keys=OFF")
    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transactional_ddl=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        if sqlite_connection:
            violations = connection.execute(text("PRAGMA foreign_key_check")).all()
            if violations:
                raise RuntimeError(
                    f"Migration left foreign key violations: {violations}"
                )
            connection.commit()
    finally:
        if sqlite_connection:
            connection.connection.dbapi_connection.execute("PRAGMA foreign_keys=ON")


async def run_async_migrations() -> None:
    settings = Settings()
    if not settings.db_primary_url:
        raise ValueError("Set DB_PRIMARY_URL before running migrations")
    engine = create_primary_engine(
        settings,
        create_database_metrics(
            create_metrics(), settings.db_pool_size + settings.db_pool_max_overflow
        ),
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url="sqlite+aiosqlite:///offline.db",
        target_metadata=target_metadata,
        literal_binds=True,
        transactional_ddl=True,
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    do_run_migrations(config.attributes["connection"])
else:
    asyncio.run(run_async_migrations())

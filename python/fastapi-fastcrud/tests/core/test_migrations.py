import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from template_fastcrud_api.core.database import create_primary_engine
from template_fastcrud_api.core.database_metrics import create_database_metrics
from template_fastcrud_api.core.metrics import create_metrics
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.models.reservations import (
    IdempotencyKeyModel,
    ProductModel,
    ReservationModel,
)


def run_migration(database_url: str, *args: str) -> None:
    config = Path(__file__).resolve().parents[2] / "alembic.ini"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(config), *args],
        env={**os.environ, "DB_PRIMARY_URL": database_url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_migration_repeat_drift_and_database_constraints(database_url: str) -> None:
    for args in [("upgrade", "head"), ("check",)]:
        run_migration(database_url, *args)

    async def scenario():
        engine = create_primary_engine(
            Settings(db_primary_url=database_url),
            create_database_metrics(create_metrics(), 4),
        )
        try:
            async with engine.begin() as conn:
                await conn.execute(insert(ProductModel).values(id="demo", available=1))
                await conn.execute(
                    insert(ReservationModel).values(
                        id="r",
                        product_id="demo",
                        created_at="2026-09-08T00:00:00+00:00",
                    )
                )
                await conn.execute(
                    insert(IdempotencyKeyModel).values(
                        key="key",
                        product_id="demo",
                        reservation_id="r",
                        response={"reservation_id": "r"},
                    )
                )
            invalid = [
                insert(ProductModel).values(id="bad", available=-1),
                insert(ReservationModel).values(
                    id="invalid", product_id="missing", created_at="now"
                ),
                insert(IdempotencyKeyModel).values(
                    key="key", product_id="demo", reservation_id="r", response={}
                ),
            ]
            for statement in invalid:
                with pytest.raises(IntegrityError):
                    async with engine.begin() as conn:
                        await conn.execute(statement)
            async with engine.connect() as conn:
                assert await conn.scalar(text("SELECT count(*) FROM reservations")) == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())

    for args in [("downgrade", "base"), ("upgrade", "head"), ("check",)]:
        run_migration(database_url, *args)


def test_populated_previous_revision_upgrade_preserves_state(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/previous.db"
    database_path = str(make_url(database_url).database)
    run_migration(database_url, "upgrade", "7372e3cacca4")
    response = {
        "reservation_id": "legacy-reservation",
        "product_id": "legacy-product",
        "created_at": "2026-09-08T00:00:00+00:00",
    }
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO products (id, available) VALUES (?, ?)",
            ("legacy-product", 7),
        )
        connection.execute(
            "INSERT INTO reservations (id, product_id, created_at) VALUES (?, ?, ?)",
            ("legacy-reservation", "legacy-product", response["created_at"]),
        )
        connection.execute(
            "INSERT INTO idempotency_keys "
            "(key, product_id, reservation_id, response) VALUES (?, ?, ?, ?)",
            (
                "legacy-key",
                "legacy-product",
                "legacy-reservation",
                json.dumps(response),
            ),
        )
        connection.commit()

    before_upgrade = datetime.now(UTC)
    run_migration(database_url, "upgrade", "head")
    after_upgrade = datetime.now(UTC)

    async def assert_upgraded_state() -> None:
        engine = create_primary_engine(
            Settings(db_primary_url=database_url),
            create_database_metrics(create_metrics(), 4),
        )
        try:
            async with engine.connect() as connection:
                row = (
                    await connection.execute(
                        select(
                            ProductModel.available,
                            ProductModel.created_at,
                            ProductModel.updated_at,
                            ProductModel.is_deleted,
                            ProductModel.deleted_at,
                        ).where(ProductModel.id == "legacy-product")
                    )
                ).one()
                assert row.available == 7
                assert row.created_at == row.updated_at
                assert before_upgrade <= row.created_at <= after_upgrade
                assert row.created_at.tzinfo is UTC
                assert row.is_deleted is False
                assert row.deleted_at is None
                assert not (
                    await connection.execute(text("PRAGMA foreign_key_check"))
                ).all()
        finally:
            await engine.dispose()

    asyncio.run(assert_upgraded_state())
    with closing(sqlite3.connect(database_path)) as connection:
        stored_response = connection.execute(
            "SELECT response FROM idempotency_keys WHERE key='legacy-key'"
        ).fetchone()[0]
        assert json.loads(stored_response) == response
        assert (
            connection.execute(
                "SELECT created_at FROM reservations WHERE id='legacy-reservation'"
            ).fetchone()[0]
            == response["created_at"]
        )

    run_migration(database_url, "downgrade", "7372e3cacca4")
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT id, available FROM products").fetchall() == [
            ("legacy-product", 7)
        ]
        assert connection.execute(
            "SELECT key, response FROM idempotency_keys"
        ).fetchall() == [("legacy-key", json.dumps(response))]
        product_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(products)")
        }
        assert product_columns == {"id", "available"}
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()

    run_migration(database_url, "upgrade", "head")
    run_migration(database_url, "check")


def test_foreign_key_check_failure_rolls_back_entire_migration(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/invalid-legacy.db"
    database_path = str(make_url(database_url).database)
    run_migration(database_url, "upgrade", "7372e3cacca4")
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO reservations (id, product_id, created_at) VALUES (?, ?, ?)",
            ("orphan", "missing", "2026-09-08T00:00:00+00:00"),
        )
        connection.commit()

    config = Path(__file__).resolve().parents[2] / "alembic.ini"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(config), "upgrade", "head"],
        env={**os.environ, "DB_PRIMARY_URL": database_url},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Migration left foreign key violations" in result.stderr

    with closing(sqlite3.connect(database_path)) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        assert revision == ("7372e3cacca4",)
        product_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(products)")
        }
        assert product_columns == {"id", "available"}
        assert connection.execute(
            "SELECT id, product_id, created_at FROM reservations"
        ).fetchall() == [("orphan", "missing", "2026-09-08T00:00:00+00:00")]
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name='_alembic_tmp_products'"
        ).fetchall()


def test_migration_rejects_connection_with_existing_transaction(
    database_url: str,
) -> None:
    database_path = str(make_url(database_url).database)
    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(config_path))
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            with pytest.raises(
                RuntimeError,
                match="Alembic migrations require a connection without a transaction",
            ):
                command.check(config)
    finally:
        engine.dispose()

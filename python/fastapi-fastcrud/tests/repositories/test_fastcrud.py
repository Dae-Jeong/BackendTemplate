import asyncio
from datetime import UTC, datetime
from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from template_fastcrud_api.contracts.reservations import Product, Reservation
from template_fastcrud_api.core.database import create_primary_engine
from template_fastcrud_api.core.database_metrics import create_database_metrics
from template_fastcrud_api.core.metrics import create_metrics
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.exceptions.reservations import ProductNotFound
from template_fastcrud_api.models.reservations import ProductModel, ReservationModel
from template_fastcrud_api.repositories.reservations import (
    create_product,
    decrease_stock,
    get_product,
    product_crud,
    save_reservation,
    seed_product,
)


def test_fastcrud_create_flushes_refreshes_and_outer_transaction_rolls_back(
    database_url: str,
) -> None:
    async def scenario() -> None:
        settings = Settings(db_primary_url=database_url)
        engine = create_primary_engine(
            settings,
            create_database_metrics(
                create_metrics(),
                settings.db_pool_size + settings.db_pool_max_overflow,
            ),
        )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                with pytest.raises(RuntimeError, match="force rollback"):
                    async with session.begin():
                        with (
                            patch.object(
                                session, "flush", wraps=session.flush
                            ) as flush,
                            patch.object(
                                session, "refresh", wraps=session.refresh
                            ) as refresh,
                        ):
                            product = await create_product(session, "fastcrud", 2)
                        flush.assert_awaited_once()
                        refresh.assert_awaited_once()
                        assert product == Product("fastcrud", 2)
                        assert not isinstance(product, ProductModel)
                        assert (
                            await session.scalar(
                                select(func.count())
                                .select_from(ProductModel)
                                .where(ProductModel.id == "fastcrud")
                            )
                            == 1
                        )
                        saved = await save_reservation(
                            session,
                            Reservation(
                                reservation_id="reservation",
                                product_id="fastcrud",
                                created_at=datetime(2026, 9, 15, tzinfo=UTC),
                            ),
                        )
                        assert saved is None
                        assert (
                            await session.scalar(
                                select(func.count()).select_from(ReservationModel)
                            )
                            == 1
                        )
                        raise RuntimeError("force rollback")

            async with factory() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(ProductModel))
                    == 0
                )
                assert (
                    await session.scalar(
                        select(func.count()).select_from(ReservationModel)
                    )
                    == 0
                )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_product_timestamps_cover_defaults_orm_core_fastcrud_and_rollback(
    database_url: str,
) -> None:
    async def scenario() -> None:
        settings = Settings(db_primary_url=database_url)
        engine = create_primary_engine(
            settings,
            create_database_metrics(
                create_metrics(),
                settings.db_pool_size + settings.db_pool_max_overflow,
            ),
        )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        created_at = datetime(2020, 1, 1, tzinfo=UTC)
        old_updated_at = datetime(2021, 1, 1, tzinfo=UTC)
        try:
            async with factory() as session:
                async with session.begin():
                    await create_product(session, "defaulted", 1)
                defaulted = await session.get(ProductModel, "defaulted")
                assert defaulted is not None
                assert defaulted.created_at.tzinfo is UTC
                assert defaulted.updated_at.tzinfo is UTC
                await session.rollback()

                async with session.begin():
                    audited = ProductModel(
                        id="audited",
                        available=5,
                        created_at=created_at,
                        updated_at=old_updated_at,
                    )
                    session.add(audited)
                async with session.begin():
                    audited.available = 4
                assert audited.created_at == created_at
                assert audited.updated_at > old_updated_at
                assert audited.updated_at.tzinfo is UTC
                await session.rollback()

                async with session.begin():
                    await session.execute(
                        update(ProductModel)
                        .where(ProductModel.id == "audited")
                        .values(updated_at=old_updated_at)
                    )
                async with session.begin():
                    await decrease_stock(session, "audited")
                await session.refresh(audited)
                assert audited.available == 3
                assert audited.created_at == created_at
                assert audited.updated_at > old_updated_at
                assert audited.updated_at.tzinfo is UTC
                await session.rollback()

                async with session.begin():
                    await session.execute(
                        update(ProductModel)
                        .where(ProductModel.id == "audited")
                        .values(updated_at=old_updated_at)
                    )
                async with session.begin():
                    await product_crud.update(
                        db=session,
                        object={"available": 2},
                        commit=False,
                        id="audited",
                    )
                await session.refresh(audited)
                assert audited.available == 2
                assert audited.created_at == created_at
                assert audited.updated_at > old_updated_at
                assert audited.updated_at.tzinfo is UTC
                await session.rollback()

                async with session.begin():
                    await session.execute(
                        update(ProductModel)
                        .where(ProductModel.id == "audited")
                        .values(updated_at=old_updated_at)
                    )
                await session.refresh(audited)
                await session.rollback()
                with pytest.raises(RuntimeError, match="force rollback"):
                    async with session.begin():
                        await decrease_stock(session, "audited")
                        changed = (
                            await session.execute(
                                select(ProductModel).where(ProductModel.id == "audited")
                            )
                        ).scalar_one()
                        assert changed.available == 1
                        assert changed.updated_at > old_updated_at
                        raise RuntimeError("force rollback")
                await session.refresh(audited)
                assert audited.available == 2
                assert audited.created_at == created_at
                assert audited.updated_at == old_updated_at
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_product_soft_delete_is_opt_in_filtered_and_rollback_safe(
    database_url: str,
) -> None:
    async def scenario() -> None:
        settings = Settings(db_primary_url=database_url)
        engine = create_primary_engine(
            settings,
            create_database_metrics(
                create_metrics(),
                settings.db_pool_size + settings.db_pool_max_overflow,
            ),
        )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        old_updated_at = datetime(2021, 1, 1, tzinfo=UTC)
        try:
            async with factory() as session:
                async with session.begin():
                    product = ProductModel(
                        id="deleted",
                        available=3,
                        created_at=datetime(2020, 1, 1, tzinfo=UTC),
                        updated_at=old_updated_at,
                    )
                    session.add(product)

                with pytest.raises(RuntimeError, match="force rollback"):
                    async with session.begin():
                        await product_crud.delete(
                            db=session, db_row=cast(Row, product), commit=False
                        )
                        await session.flush()
                        assert product.is_deleted is True
                        assert product.deleted_at is not None
                        assert product.deleted_at.tzinfo is UTC
                        assert product.updated_at > old_updated_at
                        raise RuntimeError("force rollback")
                await session.refresh(product)
                assert product.is_deleted is False
                assert product.deleted_at is None
                assert product.updated_at == old_updated_at
                await session.rollback()

                async with session.begin():
                    await product_crud.delete(db=session, commit=False, id="deleted")
                await session.refresh(product)
                assert product.is_deleted is True
                assert product.deleted_at is not None
                assert product.deleted_at.tzinfo is UTC
                assert product.updated_at > old_updated_at
                assert product.updated_at.tzinfo is UTC
                assert product.available == 3

                with pytest.raises(ProductNotFound):
                    await get_product(session, "deleted")
                with pytest.raises(ProductNotFound):
                    await seed_product(session, "deleted", 100)
                await session.rollback()
                with pytest.raises(ProductNotFound):
                    async with session.begin():
                        await decrease_stock(session, "deleted")
                session.expunge(product)
                with pytest.raises(IntegrityError):
                    async with session.begin():
                        await create_product(session, "deleted", 100)
                persisted = await session.get(ProductModel, "deleted")
                assert persisted is not None
                assert persisted.available == 3
                assert persisted.is_deleted is True
        finally:
            await engine.dispose()

    asyncio.run(scenario())

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from template_fastcrud_api.contracts.reservations import Product, Reservation
from template_fastcrud_api.core.database import create_primary_engine
from template_fastcrud_api.core.database_metrics import create_database_metrics
from template_fastcrud_api.core.metrics import create_metrics
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.models.reservations import ProductModel, ReservationModel
from template_fastcrud_api.repositories.reservations import (
    create_product,
    save_reservation,
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


def test_fastcrud_inputs_live_only_in_repository_module() -> None:
    import template_fastcrud_api.repositories.reservations as repository

    for name in (
        "ProductCreate",
        "ProductSelect",
        "ReservationCreate",
        "IdempotencyCreate",
        "IdempotencySelect",
    ):
        schema = getattr(repository, name)
        assert schema.__module__ == repository.__name__
        assert not name.startswith("_")

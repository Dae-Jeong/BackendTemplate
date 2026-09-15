from fastcrud import FastCRUD
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from template_fastcrud_api.models.reservations import (
    IdempotencyKeyModel,
    ProductModel,
    ReservationModel,
)

product_crud = FastCRUD(ProductModel)
reservation_crud = FastCRUD(ReservationModel)
idempotency_crud = FastCRUD(IdempotencyKeyModel)


async def insert_product_if_absent(
    session: AsyncSession, product_id: str, stock: int
) -> None:
    await session.execute(
        sqlite_insert(ProductModel)
        .values(id=product_id, available=stock)
        .on_conflict_do_nothing(index_elements=[ProductModel.id])
    )


async def decrement_stock_if_available(session: AsyncSession, product_id: str) -> bool:
    changed = await session.scalar(
        update(ProductModel)
        .where(
            ProductModel.id == product_id,
            ProductModel.available > 0,
            ProductModel.is_deleted.is_(False),
        )
        .values(available=ProductModel.available - 1)
        .returning(ProductModel.id)
    )
    return changed is not None

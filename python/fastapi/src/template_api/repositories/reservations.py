from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from template_api.contracts.reservations import Product, Reservation
from template_api.exceptions.reservations import (
    IdempotencyConflict,
    ProductNotFound,
    SoldOut,
)
from template_api.models.reservations import idempotency_keys, products, reservations


async def seed_product(session: AsyncSession, product_id: str, stock: int) -> Product:
    await session.execute(
        sqlite_insert(products)
        .values(id=product_id, available=stock)
        .on_conflict_do_nothing(index_elements=[products.c.id])
    )
    return await get_product(session, product_id)


async def get_product(session: AsyncSession, product_id: str) -> Product:
    row = (
        await session.execute(select(products).where(products.c.id == product_id))
    ).one_or_none()
    if row is None:
        raise ProductNotFound()
    return Product(product_id=row.id, available=row.available)


async def decrease_stock(session: AsyncSession, product_id: str) -> None:
    changed = await session.scalar(
        update(products)
        .where(products.c.id == product_id, products.c.available > 0)
        .values(available=products.c.available - 1)
        .returning(products.c.id)
    )
    if changed is None:
        await get_product(session, product_id)
        raise SoldOut()


async def save_reservation(session: AsyncSession, reservation: Reservation) -> None:
    await session.execute(
        insert(reservations).values(
            id=reservation.reservation_id,
            product_id=reservation.product_id,
            created_at=reservation.created_at.isoformat(),
        )
    )


async def find_matching_replay(
    session: AsyncSession, key: str, product_id: str
) -> Reservation | None:
    row = (
        await session.execute(
            select(idempotency_keys).where(idempotency_keys.c.key == key)
        )
    ).one_or_none()
    if row is None:
        return None
    if row.product_id != product_id:
        raise IdempotencyConflict()
    response = row.response
    return Reservation(
        response["reservation_id"],
        response["product_id"],
        datetime.fromisoformat(response["created_at"]),
    )


async def save_idempotency(
    session: AsyncSession, key: str, reservation: Reservation
) -> None:
    await session.execute(
        insert(idempotency_keys).values(
            key=key,
            product_id=reservation.product_id,
            reservation_id=reservation.reservation_id,
            response={
                "reservation_id": reservation.reservation_id,
                "product_id": reservation.product_id,
                "created_at": reservation.created_at.isoformat(),
            },
        )
    )

import json

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from template_api.contracts.reservations import Product, ReplayRecord, Reservation
from template_api.models.reservations import idempotency_keys, products, reservations
from template_api.schemas.reservations import reservation_adapter


async def seed_product(
    session: AsyncSession, product_id: str, stock: int
) -> Product | None:
    await session.execute(
        sqlite_insert(products)
        .values(id=product_id, available=stock)
        .on_conflict_do_nothing(index_elements=[products.c.id])
    )
    return await find_product(session, product_id)


async def find_product(session: AsyncSession, product_id: str) -> Product | None:
    row = (
        await session.execute(select(products).where(products.c.id == product_id))
    ).one_or_none()
    if row is None:
        return None
    return Product(product_id=row.id, available=row.available)


async def decrease_stock_if_available(session: AsyncSession, product_id: str) -> bool:
    changed = await session.scalar(
        update(products)
        .where(products.c.id == product_id, products.c.available > 0)
        .values(available=products.c.available - 1)
        .returning(products.c.id)
    )
    return changed is not None


async def save_reservation(session: AsyncSession, reservation: Reservation) -> None:
    await session.execute(
        insert(reservations).values(
            id=reservation.reservation_id,
            product_id=reservation.product_id,
            created_at=reservation.created_at.isoformat(),
        )
    )


async def find_replay(session: AsyncSession, key: str) -> ReplayRecord | None:
    row = (
        await session.execute(
            select(idempotency_keys).where(idempotency_keys.c.key == key)
        )
    ).one_or_none()
    if row is None:
        return None
    return ReplayRecord(
        product_id=row.product_id,
        reservation=reservation_adapter.validate_json(
            json.dumps(row.response), strict=True
        ),
    )


async def save_idempotency(
    session: AsyncSession, key: str, reservation: Reservation
) -> None:
    await session.execute(
        insert(idempotency_keys).values(
            key=key,
            product_id=reservation.product_id,
            reservation_id=reservation.reservation_id,
            response=reservation_adapter.dump_python(reservation, mode="json"),
        )
    )

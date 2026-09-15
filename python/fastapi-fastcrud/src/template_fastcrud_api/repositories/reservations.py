from datetime import datetime

from fastcrud import FastCRUD
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from template_fastcrud_api.contracts.reservations import (
    Product as ProductRecord,
)
from template_fastcrud_api.contracts.reservations import (
    Reservation,
)
from template_fastcrud_api.exceptions.reservations import (
    IdempotencyConflict,
    ProductNotFound,
    SoldOut,
)
from template_fastcrud_api.models.reservations import (
    IdempotencyKeyModel,
    ProductModel,
    ReservationModel,
)
from template_fastcrud_api.schemas.reservations import (
    IdempotencyRecord,
    ProductSelect,
    ReservationCreate,
)

product_crud = FastCRUD(ProductModel)
reservation_crud = FastCRUD(ReservationModel)
idempotency_crud = FastCRUD(IdempotencyKeyModel)


async def seed_product(
    session: AsyncSession, product_id: str, stock: int
) -> ProductRecord:
    await session.execute(
        sqlite_insert(ProductModel)
        .values(id=product_id, available=stock)
        .on_conflict_do_nothing(index_elements=[ProductModel.id])
    )
    return await get_product(session, product_id)


async def get_product(session: AsyncSession, product_id: str) -> ProductRecord:
    selected = await product_crud.get(
        db=session,
        schema_to_select=ProductSelect,
        return_as_model=True,
        id=product_id,
        is_deleted=False,
    )
    if selected is None:
        raise ProductNotFound()
    return ProductRecord(product_id=selected.id, available=selected.available)


async def decrease_stock(session: AsyncSession, product_id: str) -> None:
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
    if changed is None:
        await get_product(session, product_id)
        raise SoldOut()


async def save_reservation_and_replay(
    session: AsyncSession, key: str, reservation: Reservation
) -> None:
    await reservation_crud.create(
        db=session,
        object=ReservationCreate(
            id=reservation.reservation_id,
            product_id=reservation.product_id,
            created_at=reservation.created_at.isoformat(),
        ),
        commit=False,
    )
    await idempotency_crud.create(
        db=session,
        object=IdempotencyRecord(
            key=key,
            product_id=reservation.product_id,
            reservation_id=reservation.reservation_id,
            response={
                "reservation_id": reservation.reservation_id,
                "product_id": reservation.product_id,
                "created_at": reservation.created_at.isoformat(),
            },
        ),
        commit=False,
    )


async def find_matching_replay(
    session: AsyncSession, key: str, product_id: str
) -> Reservation | None:
    selected = await idempotency_crud.get(
        db=session,
        schema_to_select=IdempotencyRecord,
        return_as_model=True,
        key=key,
    )
    if selected is None:
        return None
    if selected.product_id != product_id:
        raise IdempotencyConflict()
    response = selected.response
    return Reservation(
        response["reservation_id"],
        response["product_id"],
        datetime.fromisoformat(response["created_at"]),
    )

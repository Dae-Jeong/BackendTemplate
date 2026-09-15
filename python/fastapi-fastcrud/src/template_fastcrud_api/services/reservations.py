from datetime import UTC
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from template_fastcrud_api.contracts.reservations import Reservation, ReservationResult
from template_fastcrud_api.core.contracts import Clock
from template_fastcrud_api.core.database_metrics import DatabaseMetrics
from template_fastcrud_api.core.transactions import transactional
from template_fastcrud_api.crud.reservations import (
    decrement_stock_if_available,
    idempotency_crud,
    product_crud,
    reservation_crud,
)
from template_fastcrud_api.exceptions.reservations import SoldOut
from template_fastcrud_api.schemas.reservations import (
    IdempotencyRecord,
    ProductSelect,
    ReservationCreate,
)
from template_fastcrud_api.validation.reservations import (
    validate_product_exists,
    validate_replay_product,
)


@transactional
async def reserve(
    *,
    session: AsyncSession,
    metrics: DatabaseMetrics,
    product_id: str,
    key: str,
    clock: Clock,
) -> ReservationResult:
    existing = await idempotency_crud.get(
        db=session,
        schema_to_select=IdempotencyRecord,
        return_as_model=True,
        key=key,
    )
    if existing is not None:
        return ReservationResult(
            reservation=validate_replay_product(product_id, existing),
            replayed=True,
        )

    if not await decrement_stock_if_available(session, product_id):
        product = await product_crud.get(
            db=session,
            schema_to_select=ProductSelect,
            return_as_model=True,
            id=product_id,
            is_deleted=False,
        )
        validate_product_exists(product)
        raise SoldOut()

    reservation = Reservation(
        reservation_id=uuid4().hex,
        product_id=product_id,
        created_at=clock().astimezone(UTC),
    )
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
            response=reservation,
        ),
        commit=False,
    )
    return ReservationResult(reservation=reservation, replayed=False)

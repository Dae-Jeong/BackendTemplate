from datetime import UTC
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from template_api.contracts.reservations import Reservation, ReservationResult
from template_api.core.contracts import Clock
from template_api.core.database_metrics import DatabaseMetrics
from template_api.core.transactions import transactional
from template_api.exceptions.reservations import SoldOut
from template_api.repositories.reservations import (
    decrease_stock_if_available,
    find_product,
    find_replay,
    save_idempotency,
    save_reservation,
)
from template_api.validation.reservations import (
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
    existing = await find_replay(session, key)
    if existing is not None:
        return ReservationResult(
            reservation=validate_replay_product(product_id, existing), replayed=True
        )
    if not await decrease_stock_if_available(session, product_id):
        validate_product_exists(await find_product(session, product_id))
        raise SoldOut()
    reservation = Reservation(
        reservation_id=uuid4().hex,
        product_id=product_id,
        created_at=clock().astimezone(UTC),
    )
    await save_reservation(session, reservation)
    await save_idempotency(session, key, reservation)
    return ReservationResult(reservation=reservation, replayed=False)

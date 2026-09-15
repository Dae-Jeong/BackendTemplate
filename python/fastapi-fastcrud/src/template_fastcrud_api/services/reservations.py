from datetime import UTC
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from template_fastcrud_api.contracts.reservations import Reservation, ReservationResult
from template_fastcrud_api.core.contracts import Clock
from template_fastcrud_api.core.database_metrics import DatabaseMetrics
from template_fastcrud_api.core.transactions import transactional
from template_fastcrud_api.repositories.reservations import (
    decrease_stock,
    find_matching_replay,
    save_idempotency,
    save_reservation,
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
    existing = await find_matching_replay(session, key, product_id)
    if existing is not None:
        return ReservationResult(existing, replayed=True)
    await decrease_stock(session, product_id)
    reservation = Reservation(uuid4().hex, product_id, clock().astimezone(UTC))
    await save_reservation(session, reservation)
    await save_idempotency(session, key, reservation)
    return ReservationResult(reservation, replayed=False)

from datetime import UTC
from sqlite3 import SQLITE_BUSY, SQLITE_LOCKED
from time import monotonic
from uuid import uuid4

from sqlalchemy.exc import OperationalError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from template_fastcrud_api.contracts.database import TransactionOutcome
from template_fastcrud_api.contracts.reservations import Reservation, ReservationResult
from template_fastcrud_api.core.contracts import Clock
from template_fastcrud_api.core.database import acquire_primary_connection
from template_fastcrud_api.core.database_metrics import DatabaseMetrics
from template_fastcrud_api.exceptions.database import DatabaseBusy, DatabasePoolTimeout
from template_fastcrud_api.repositories.reservations import (
    decrease_stock,
    find_matching_replay,
    save_idempotency,
    save_reservation,
)


async def reserve_once(
    session: AsyncSession, product_id: str, key: str, clock: Clock
) -> ReservationResult:
    existing = await find_matching_replay(session, key, product_id)
    if existing is not None:
        return ReservationResult(existing, replayed=True)
    await decrease_stock(session, product_id)
    reservation = Reservation(uuid4().hex, product_id, clock().astimezone(UTC))
    await save_reservation(session, reservation)
    await save_idempotency(session, key, reservation)
    return ReservationResult(reservation, replayed=False)


async def reserve(
    *,
    session: AsyncSession,
    metrics: DatabaseMetrics,
    product_id: str,
    key: str,
    clock: Clock,
) -> ReservationResult:
    started = monotonic()
    outcome = TransactionOutcome.FAILED
    body_error: BaseException | None = None
    try:
        async with session.begin():
            try:
                await acquire_primary_connection(session, metrics, write=True)
                result = await reserve_once(session, product_id, key, clock)
            except BaseException as error:
                body_error = error
                raise
        outcome = TransactionOutcome.COMMITTED
        return result
    except BaseException as error:
        if error is body_error:
            outcome = TransactionOutcome.ROLLED_BACK
        if isinstance(error, TimeoutError):
            raise DatabasePoolTimeout() from error
        if isinstance(error, OperationalError) and getattr(
            error.orig, "sqlite_errorcode", 0
        ) & 0xFF in (SQLITE_BUSY, SQLITE_LOCKED):
            raise DatabaseBusy() from error
        raise
    finally:
        metrics.record_transaction(outcome, monotonic() - started)

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from inspect import Parameter, signature
from sqlite3 import SQLITE_BUSY, SQLITE_LOCKED
from time import monotonic
from typing import cast

from sqlalchemy.exc import OperationalError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from template_api.contracts.database import TransactionOutcome
from template_api.core.database import acquire_primary_connection
from template_api.core.database_metrics import DatabaseMetrics
from template_api.exceptions.database import (
    ConcurrentTransactionUse,
    DatabaseBusy,
    DatabasePoolTimeout,
    TransactionOwnershipError,
    TransactionRollbackOnly,
)


@dataclass
class TransactionState:
    owner: asyncio.Task[object]
    rollback_cause: BaseException | None = None


def record_transaction_safely(
    metrics: DatabaseMetrics, outcome: TransactionOutcome, started: float
) -> None:
    try:
        metrics.record_transaction(outcome, monotonic() - started)
    except Exception:
        metrics.owner.failed = True


def transactional[**P, R](
    function: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    """Run an async service in its explicit keyword-only session transaction."""
    parameters = signature(function).parameters
    for name in ("session", "metrics"):
        parameter = parameters.get(name)
        if (
            parameter is None
            or parameter.kind is not Parameter.KEYWORD_ONLY
            or parameter.default is not Parameter.empty
        ):
            raise TypeError(f"@transactional requires required keyword-only {name}")

    @wraps(function)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        if "session" not in kwargs or "metrics" not in kwargs:
            raise TypeError(
                "@transactional requires session and metrics keyword arguments"
            )
        session = cast(AsyncSession, kwargs["session"])
        metrics = cast(DatabaseMetrics, kwargs["metrics"])
        state_key = f"{__name__}.state"
        existing = cast(TransactionState | None, session.info.get(state_key))
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("@transactional requires an asyncio Task")
        if existing is not None:
            if existing.owner is not task:
                raise ConcurrentTransactionUse(
                    "A decorator-managed session cannot be shared across tasks"
                )
            try:
                return await function(*args, **kwargs)
            except BaseException as error:
                if existing.rollback_cause is None:
                    existing.rollback_cause = error
                raise

        started = monotonic()
        outcome = TransactionOutcome.FAILED
        if session.in_transaction():
            raise TransactionOwnershipError(
                "@transactional requires a session without an existing transaction"
            )

        state = TransactionState(cast(asyncio.Task[object], task))
        session.info[state_key] = state
        try:
            async with session.begin() as transaction:
                await acquire_primary_connection(session, metrics, write=True)
                result = await function(*args, **kwargs)
                if state.rollback_cause is not None:
                    raise TransactionRollbackOnly(
                        "A nested transactional call failed; the transaction was rolled back"
                    ) from state.rollback_cause
                if (
                    session.get_transaction() is not transaction
                    or not transaction.is_active
                ):
                    raise TransactionOwnershipError(
                        "Do not commit or roll back inside @transactional"
                    )
            outcome = TransactionOutcome.COMMITTED
            return result
        except TimeoutError as error:
            raise DatabasePoolTimeout() from error
        except OperationalError as error:
            sqlite_errorcode = getattr(error.orig, "sqlite_errorcode", 0) & 0xFF
            if sqlite_errorcode in (SQLITE_BUSY, SQLITE_LOCKED):
                raise DatabaseBusy() from error
            raise
        finally:
            session.info.pop(state_key, None)
            record_transaction_safely(metrics, outcome, started)

    return wrapped

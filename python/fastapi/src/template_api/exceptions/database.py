class DatabaseBusy(Exception):
    """SQLite write lock could not be acquired within its configured timeout."""


class DatabasePoolTimeout(Exception):
    """No connection was available within the pool acquisition budget."""


class TransactionRollbackOnly(RuntimeError):
    """A caught nested failure forced the decorator-owned transaction to roll back."""


class TransactionOwnershipError(RuntimeError):
    """The caller changed or preempted the decorator-owned transaction."""


class ConcurrentTransactionUse(RuntimeError):
    """Another asyncio task owns this decorator-managed session."""

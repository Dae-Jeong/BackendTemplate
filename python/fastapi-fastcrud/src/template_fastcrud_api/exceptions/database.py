class DatabaseBusy(Exception):
    """SQLite write lock could not be acquired within its configured timeout."""


class DatabasePoolTimeout(Exception):
    """No connection was available within the pool acquisition budget."""

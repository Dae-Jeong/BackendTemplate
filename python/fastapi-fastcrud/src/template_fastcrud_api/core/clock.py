from datetime import UTC, datetime


def system_clock() -> datetime:
    return datetime.now(UTC)

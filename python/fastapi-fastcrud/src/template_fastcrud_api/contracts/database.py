from enum import StrEnum


class TransactionOutcome(StrEnum):
    COMMITTED = "committed"
    FAILED = "failed"


class AcquisitionOutcome(StrEnum):
    ACQUIRED = "acquired"
    TIMEOUT = "timeout"
    FAILED = "failed"

from enum import StrEnum


class TransactionOutcome(StrEnum):
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class AcquisitionOutcome(StrEnum):
    ACQUIRED = "acquired"
    TIMEOUT = "timeout"
    FAILED = "failed"

from collections.abc import Callable
from dataclasses import dataclass

from prometheus_client import Counter, Gauge, Histogram

from template_fastcrud_api.contracts.database import (
    AcquisitionOutcome,
    TransactionOutcome,
)
from template_fastcrud_api.core.metrics import HttpMetrics

DB_DURATION_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1,
    2.5,
    5,
    10,
    30,
    60,
    120,
)


@dataclass
class DatabaseMetrics:
    owner: HttpMetrics
    connections: Gauge
    hold: Histogram
    sessions: Gauge
    acquisition: Histogram
    timeouts: Counter
    transactions: Counter
    transaction_duration: Histogram

    def record(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception:
            self.owner.failed = True

    def record_acquisition(self, outcome: AcquisitionOutcome, seconds: float) -> None:
        self.record(
            lambda: self.acquisition.labels("primary", outcome.value).observe(seconds)
        )
        if outcome is AcquisitionOutcome.TIMEOUT:
            self.record(self.timeouts.inc)

    def record_transaction(self, outcome: TransactionOutcome, seconds: float) -> None:
        self.record(lambda: self.transactions.labels("primary", outcome.value).inc())
        self.record(
            lambda: self.transaction_duration.labels("primary", outcome.value).observe(
                seconds
            )
        )


def create_database_metrics(owner: HttpMetrics, limit: int) -> DatabaseMetrics:
    labels = {"role": "primary"}
    connections = Gauge(
        "db_pool_connections_in_use",
        "Connections currently checked out.",
        labels,
        registry=owner.registry,
    ).labels(**labels)
    hold = Histogram(
        "db_pool_connection_hold_seconds",
        "Time from checkout to return or detach.",
        labels,
        buckets=DB_DURATION_BUCKETS,
        registry=owner.registry,
    ).labels(**labels)
    Gauge(
        "db_pool_connection_limit",
        "Configured pool size plus allowed overflow.",
        labels,
        registry=owner.registry,
    ).labels(**labels).set(limit)
    sessions = Gauge(
        "db_sessions_active",
        "Sessions owned by the session provider.",
        labels,
        registry=owner.registry,
    ).labels(**labels)
    acquisition = Histogram(
        "db_connection_acquire_seconds",
        "Explicit connection acquisition including connect and validation costs.",
        ("role", "outcome"),
        buckets=DB_DURATION_BUCKETS,
        registry=owner.registry,
    )
    timeouts = Counter(
        "db_pool_timeouts_total",
        "Pool timeouts at explicit connection acquisition.",
        labels,
        registry=owner.registry,
    ).labels(**labels)
    transactions = Counter(
        "db_transactions_total",
        "Business transaction outcomes after finalization.",
        ("role", "outcome"),
        registry=owner.registry,
    )
    duration = Histogram(
        "db_transaction_duration_seconds",
        "Business transaction duration including commit or rollback.",
        ("role", "outcome"),
        buckets=DB_DURATION_BUCKETS,
        registry=owner.registry,
    )
    # Initialize bounded labels so Prometheus can observe the first increment.
    for acquisition_outcome in AcquisitionOutcome:
        acquisition.labels("primary", acquisition_outcome.value)
    for transaction_outcome in TransactionOutcome:
        transactions.labels("primary", transaction_outcome.value)
        duration.labels("primary", transaction_outcome.value)
    return DatabaseMetrics(
        owner,
        connections,
        hold,
        sessions,
        acquisition,
        timeouts,
        transactions,
        duration,
    )

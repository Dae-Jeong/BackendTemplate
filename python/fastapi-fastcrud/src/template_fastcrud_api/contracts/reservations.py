from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    product_id: str
    created_at: datetime


@dataclass(frozen=True)
class ReservationResult:
    reservation: Reservation
    replayed: bool

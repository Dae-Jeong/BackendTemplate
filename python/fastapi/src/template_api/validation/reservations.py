from template_api.contracts.reservations import Product, ReplayRecord, Reservation
from template_api.exceptions.reservations import (
    IdempotencyConflict,
    ProductNotFound,
)


def validate_replay_product(
    requested_product_id: str, replay: ReplayRecord
) -> Reservation:
    if replay.product_id != requested_product_id:
        raise IdempotencyConflict()
    return replay.reservation


def validate_product_exists(product: Product | None) -> Product:
    if product is None:
        raise ProductNotFound()
    return product

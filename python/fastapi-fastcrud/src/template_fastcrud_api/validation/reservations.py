from template_fastcrud_api.contracts.reservations import Reservation
from template_fastcrud_api.exceptions.reservations import (
    IdempotencyConflict,
    ProductNotFound,
)
from template_fastcrud_api.schemas.reservations import (
    IdempotencyRecord,
    ProductSelect,
)


def validate_replay_product(
    requested_product_id: str, replay: IdempotencyRecord
) -> Reservation:
    if replay.product_id != requested_product_id:
        raise IdempotencyConflict()
    return replay.response


def validate_product_exists(product: ProductSelect | None) -> ProductSelect:
    if product is None:
        raise ProductNotFound()
    return product

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_serializer

from template_fastcrud_api.contracts.reservations import Reservation

_RESERVATION_ADAPTER = TypeAdapter(Reservation)


class ReserveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")


class ReservationData(BaseModel):
    reservation_id: str
    product_id: str
    created_at: datetime


class ProductSelect(BaseModel):
    id: str
    available: int


class ReservationCreate(BaseModel):
    id: str
    product_id: str
    created_at: str


class IdempotencyRecord(BaseModel):
    key: str
    product_id: str
    reservation_id: str
    response: Reservation

    @field_serializer("response")
    def serialize_response(self, response: Reservation) -> dict[str, str]:
        return _RESERVATION_ADAPTER.dump_python(response, mode="json")

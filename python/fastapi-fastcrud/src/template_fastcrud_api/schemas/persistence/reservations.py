from pydantic import BaseModel


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
    response: dict[str, str]

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReserveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")


class ReservationData(BaseModel):
    reservation_id: str
    product_id: str
    created_at: datetime

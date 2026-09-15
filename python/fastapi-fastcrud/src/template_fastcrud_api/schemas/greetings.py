from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GreetingData(BaseModel):
    model_config = ConfigDict(frozen=True)
    message: str
    generated_at: datetime

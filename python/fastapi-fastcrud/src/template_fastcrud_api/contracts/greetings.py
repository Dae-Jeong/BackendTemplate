from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Greeting:
    message: str
    generated_at: datetime

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import StringConstraints

from template_fastcrud_api.dependencies.clock import ClockDep
from template_fastcrud_api.http.errors import PROBLEM_RESPONSES
from template_fastcrud_api.schemas.greetings import GreetingData
from template_fastcrud_api.schemas.responses import Success
from template_fastcrud_api.services.greetings import make_greeting

router = APIRouter(prefix="/v1/greetings", tags=["greetings"])

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80), Query()
]


@router.get("", response_model=Success[GreetingData], responses=PROBLEM_RESPONSES)
def greeting(name: Name, clock: ClockDep) -> Success[GreetingData]:
    result = make_greeting(name=name, clock=clock)
    return Success(
        data=GreetingData(message=result.message, generated_at=result.generated_at)
    )

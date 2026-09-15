from typing import Annotated

from fastapi import APIRouter, Header, Response

from template_api.dependencies.clock import ClockDep
from template_api.dependencies.database import DatabaseMetricsDep, PrimarySessionDep
from template_api.http.errors import PROBLEM_RESPONSES
from template_api.schemas.reservations import ReservationData, ReserveRequest
from template_api.schemas.responses import Problem, Success
from template_api.services.reservations import reserve

router = APIRouter(prefix="/v1/reservations", tags=["reservations"])
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
]


@router.post(
    "",
    status_code=201,
    response_model=Success[ReservationData],
    responses={**PROBLEM_RESPONSES, 409: {"model": Problem}, 503: {"model": Problem}},
)
async def create_reservation(
    body: ReserveRequest,
    response: Response,
    idempotency_key: IdempotencyKey,
    session: PrimarySessionDep,
    metrics: DatabaseMetricsDep,
    clock: ClockDep,
) -> Success[ReservationData]:
    result = await reserve(
        session=session,
        metrics=metrics,
        product_id=body.product_id,
        key=idempotency_key,
        clock=clock,
    )
    response.headers["Idempotency-Replayed"] = "true" if result.replayed else "false"
    return Success(
        data=ReservationData.model_validate(result.reservation, from_attributes=True)
    )

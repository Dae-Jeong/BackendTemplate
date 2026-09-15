from fastapi import Request
from fastapi.responses import JSONResponse

from template_fastcrud_api.exceptions.database import DatabaseBusy, DatabasePoolTimeout
from template_fastcrud_api.http.errors import problem_response
from template_fastcrud_api.schemas.responses import ErrorCode


async def database_unavailable(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, DatabaseBusy):
        code = ErrorCode.DATABASE_BUSY
    elif isinstance(exc, DatabasePoolTimeout):
        code = ErrorCode.DATABASE_POOL_TIMEOUT
    else:
        raise exc
    return problem_response(
        request, status=503, code=code, headers={"Retry-After": "1"}
    )

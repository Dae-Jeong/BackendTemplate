from collections.abc import Callable, Mapping
from http import HTTPStatus
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from template_fastcrud_api.exceptions.application import ApplicationError
from template_fastcrud_api.schemas.responses import (
    ErrorCode,
    FieldError,
    FieldErrorCode,
    Problem,
)

FIELD_CODES = {
    "missing": FieldErrorCode.REQUIRED,
    "string_too_short": FieldErrorCode.TOO_SHORT,
    "string_too_long": FieldErrorCode.TOO_LONG,
}

# 현재 공개 입력 계약입니다. 새 입력 추가 시 승인한 필드 경로만 확장합니다.
PUBLIC_LOCATIONS = {
    ("query", "name"),
    ("body", "product_id"),
    ("header", "Idempotency-Key"),
}


def problem_response(
    request: Request,
    *,
    status: int,
    code: ErrorCode,
    errors: list[FieldError] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or uuid4().hex
    request.state.request_id = request_id
    try:
        title = HTTPStatus(status).phrase
    except ValueError:
        title = "HTTP Error"
    problem = Problem(
        title=title,
        status=status,
        code=code,
        request_id=request_id,
        errors=errors,
    )
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=status,
        media_type="application/problem+json",
        headers={
            **{
                key: value
                for key, value in (headers or {}).items()
                if key.lower() not in {"content-type", "content-length", "x-request-id"}
            },
            "X-Request-ID": request_id,
        },
    )


async def application_error(
    request: Request,
    exc: Exception,
    *,
    status: HTTPStatus,
    code: ErrorCode,
) -> JSONResponse:
    """구체 업무 예외에 partial로 연결합니다. 예외 원문은 공개하지 않습니다."""
    if not isinstance(exc, ApplicationError):
        raise exc
    if not 400 <= status < 500 or code is ErrorCode.INTERNAL_ERROR:
        raise ValueError("Invalid application error response mapping")
    return problem_response(request, status=status, code=code)


async def validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = []
    for error in exc.errors()[:20]:
        location = tuple(error.get("loc", ()))
        errors.append(
            FieldError(
                location=list(location) if location in PUBLIC_LOCATIONS else [],
                code=FIELD_CODES.get(error.get("type", ""), FieldErrorCode.INVALID),
            )
        )
    return problem_response(
        request, status=422, code=ErrorCode.INVALID_INPUT, errors=errors
    )


async def http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    status = exc.status_code if 400 <= exc.status_code <= 599 else 500
    code = {
        404: ErrorCode.NOT_FOUND,
        405: ErrorCode.METHOD_NOT_ALLOWED,
    }.get(status, ErrorCode.INTERNAL_ERROR if status >= 500 else ErrorCode.HTTP_ERROR)
    return problem_response(request, status=status, code=code, headers=exc.headers)


async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    # 원인 로그는 바깥의 관측 경계가 한 번만 기록합니다.
    return problem_response(request, status=500, code=ErrorCode.INTERNAL_ERROR)


# FastAPI의 동적 response metadata 경계입니다.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {
        "description": HTTPStatus(status).phrase,
        "model": Problem,
    }
    for status in (404, 405, 422, 500)
}


def problem_openapi(
    app: FastAPI, generate: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    """동적 OpenAPI 문서 경계입니다. 모델 스키마는 FastAPI가 생성합니다."""
    if app.openapi_schema is None:
        schema = generate()
        for path in schema["paths"].values():
            for operation in path.values():
                for response in operation.get("responses", {}).values():
                    content = response.get("content", {})
                    if (
                        content.get("application/json", {})
                        .get("schema", {})
                        .get("$ref")
                        == "#/components/schemas/Problem"
                    ):
                        content["application/problem+json"] = content.pop(
                            "application/json"
                        )
        app.openapi_schema = schema
    return app.openapi_schema

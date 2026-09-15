from functools import partial
from http import HTTPStatus

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from template_fastcrud_api.bootstrap.contracts import PrepareResources
from template_fastcrud_api.bootstrap.lifespan import (
    create_lifespan,
    prepare_resources,
)
from template_fastcrud_api.core.clock import system_clock
from template_fastcrud_api.core.contracts import Clock, LogContext
from template_fastcrud_api.core.database_metrics import create_database_metrics
from template_fastcrud_api.core.metrics import create_metrics
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.exceptions.database import DatabaseBusy, DatabasePoolTimeout
from template_fastcrud_api.exceptions.reservations import (
    IdempotencyConflict,
    ProductNotFound,
    SoldOut,
)
from template_fastcrud_api.http.database import database_unavailable
from template_fastcrud_api.http.errors import (
    application_error,
    http_error,
    internal_error,
    problem_openapi,
    validation_error,
)
from template_fastcrud_api.routers.greetings import router as greetings_router
from template_fastcrud_api.routers.health import router as health_router
from template_fastcrud_api.routers.index import router as index_router
from template_fastcrud_api.routers.metrics import router as metrics_router
from template_fastcrud_api.routers.reservations import router as reservations_router
from template_fastcrud_api.schemas.responses import ErrorCode


def create_app(
    settings: Settings,
    *,
    clock: Clock = system_clock,
    prepare: PrepareResources | None = None,
) -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.service_version,
        lifespan=create_lifespan(
            prepare
            if prepare is not None
            else partial(prepare_resources, settings=settings)
        ),
    )
    app.state.clock = clock
    app.state.ready = False
    app.state.metrics = create_metrics()
    if settings.db_primary_url:
        app.state.database_metrics = create_database_metrics(
            app.state.metrics, settings.db_pool_size + settings.db_pool_max_overflow
        )
    app.state.log_context = LogContext(
        settings.app_name, settings.service_version, settings.app_environment
    )
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(Exception, internal_error)
    app.include_router(index_router)
    app.include_router(greetings_router)
    app.include_router(health_router)
    app.include_router(metrics_router)
    if settings.db_primary_url:
        app.include_router(reservations_router)
        for error, status, code in (
            (ProductNotFound, HTTPStatus.NOT_FOUND, ErrorCode.PRODUCT_NOT_FOUND),
            (SoldOut, HTTPStatus.CONFLICT, ErrorCode.SOLD_OUT),
            (IdempotencyConflict, HTTPStatus.CONFLICT, ErrorCode.IDEMPOTENCY_CONFLICT),
        ):
            app.add_exception_handler(
                error, partial(application_error, status=status, code=code)
            )
        app.add_exception_handler(DatabaseBusy, database_unavailable)
        app.add_exception_handler(DatabasePoolTimeout, database_unavailable)
    # FastAPI가 지원하는 인스턴스별 OpenAPI 함수 교체입니다. self는 partial로 고정합니다.
    app.openapi = partial(problem_openapi, app, app.openapi)  # ty: ignore[invalid-assignment]
    return app

import logging
from functools import partial
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.logging import JsonFormatter
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.exceptions.application import ApplicationError
from template_fastcrud_api.http.errors import application_error
from template_fastcrud_api.http.observation import HttpObservation
from template_fastcrud_api.schemas.responses import ErrorCode, Problem


class MissingResourceError(ApplicationError):
    """서비스에서 발생시키는 업무 오류의 테스트 대역입니다."""


@pytest.mark.parametrize("registered", [True, False])
def test_explicit_mapping_and_unregistered_error_fallback(
    registered: bool, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(Settings())
    original = MissingResourceError("private-resource")
    if registered:
        app.add_exception_handler(
            MissingResourceError,
            partial(
                application_error,
                status=HTTPStatus.NOT_FOUND,
                code=ErrorCode.NOT_FOUND,
            ),
        )

    @app.get(
        "/test/resource",
        responses={404: {"model": Problem, "description": "Resource not found"}},
    )
    def missing() -> None:
        raise original

    caplog.set_level(logging.INFO, logger="template_fastcrud_api.http.observation")
    with TestClient(
        HttpObservation(app, app.state.metrics, log_context=app.state.log_context),
        raise_server_exceptions=False,
    ) as client:
        response = client.get("/test/resource")
    assert response.status_code == (404 if registered else 500)
    problem = Problem.model_validate(response.json())
    assert problem.code == (
        ErrorCode.NOT_FOUND if registered else ErrorCode.INTERNAL_ERROR
    )
    assert response.headers["content-type"] == "application/problem+json"
    assert problem.request_id == response.headers["x-request-id"]
    assert "private-resource" not in response.text
    failures = [r for r in caplog.records if r.msg == "http.failed"]
    assert len(failures) == (0 if registered else 1)
    if failures:
        assert failures[0].exc_info and failures[0].exc_info[1] is original
    summaries = [r for r in caplog.records if r.msg == "http.completed"]
    assert len(summaries) == 1
    formatter = JsonFormatter(app.state.log_context)
    assert all("private-resource" not in formatter.format(r) for r in caplog.records)
    content = app.openapi()["paths"]["/test/resource"]["get"]["responses"]["404"][
        "content"
    ]
    assert set(content) == {"application/problem+json"}


def test_mapping_is_per_app_and_unregistered_sibling_propagates() -> None:
    class OtherError(ApplicationError):
        pass

    mapped = create_app(Settings())
    unmapped = create_app(Settings())
    mapped.add_exception_handler(
        MissingResourceError,
        partial(
            application_error, status=HTTPStatus.NOT_FOUND, code=ErrorCode.NOT_FOUND
        ),
    )
    sibling = OtherError("private-sibling")
    missing = MissingResourceError("private-missing")

    @mapped.get("/test/failure")
    def fail_sibling() -> None:
        raise sibling

    @unmapped.get("/test/failure")
    def fail_missing() -> None:
        raise missing

    with TestClient(mapped) as mapped_client, TestClient(unmapped) as unmapped_client:
        with pytest.raises(OtherError) as caught_sibling:
            mapped_client.get("/test/failure")
        with pytest.raises(MissingResourceError) as caught_missing:
            unmapped_client.get("/test/failure")
    assert caught_sibling.value is sibling
    assert caught_missing.value is missing


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (HTTPStatus.OK, ErrorCode.NOT_FOUND),
        (HTTPStatus.INTERNAL_SERVER_ERROR, ErrorCode.NOT_FOUND),
        (HTTPStatus.NOT_FOUND, ErrorCode.INTERNAL_ERROR),
    ],
)
def test_invalid_mapping_is_not_reported_as_business_rejection(
    status: HTTPStatus, code: ErrorCode
) -> None:
    app = create_app(Settings())
    app.add_exception_handler(
        MissingResourceError, partial(application_error, status=status, code=code)
    )

    @app.get("/test/failure")
    def fail() -> None:
        raise MissingResourceError("private-error")

    with TestClient(
        HttpObservation(app, app.state.metrics), raise_server_exceptions=False
    ) as client:
        response = client.get("/test/failure")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "private-error" not in response.text

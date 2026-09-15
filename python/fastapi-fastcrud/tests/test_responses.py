import asyncio

import pytest
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.testclient import TestClient
from starlette.types import Message

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.http.observation import HttpObservation
from template_fastcrud_api.schemas.responses import Problem


@pytest.mark.parametrize(
    ("method", "path", "status", "code", "field_code"),
    [
        ("GET", "/v1/greetings", 422, "INVALID_INPUT", "REQUIRED"),
        ("GET", "/v1/greetings?name=%20", 422, "INVALID_INPUT", "TOO_SHORT"),
        (
            "GET",
            "/v1/greetings?name=" + "private" * 20,
            422,
            "INVALID_INPUT",
            "TOO_LONG",
        ),
        ("GET", "/private-path?token=private-token", 404, "NOT_FOUND", None),
        ("POST", "/v1/greetings?name=Marin", 405, "METHOD_NOT_ALLOWED", None),
        ("GET", "/test/error", 500, "INTERNAL_ERROR", None),
    ],
)
def test_problem_contract_and_request_id(
    method: str,
    path: str,
    status: int,
    code: str,
    field_code: str | None,
) -> None:
    app = create_app(Settings())

    @app.get("/test/error")
    def fail() -> None:
        raise ValueError("private-exception")

    with TestClient(
        HttpObservation(app, app.state.metrics), raise_server_exceptions=False
    ) as client:
        response = client.request(method, path, headers={"X-Request-ID": "private-id"})
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    problem = Problem.model_validate(response.json())
    assert problem.status == status
    assert problem.code == code
    assert problem.request_id == response.headers["x-request-id"]
    assert len(problem.request_id) == 32
    assert "private" not in response.text
    if field_code:
        assert response.json()["errors"] == [
            {"location": ["query", "name"], "code": field_code}
        ]
    else:
        assert "errors" not in response.json()
    if status == 405:
        assert response.headers["allow"] == "GET"


def test_success_special_responses_and_http_exception_headers() -> None:
    app = create_app(Settings())

    @app.get("/test/no-content", status_code=204)
    def empty() -> Response:
        return Response(status_code=204)

    @app.get("/test/limited")
    def limited() -> None:
        raise HTTPException(
            429,
            detail="private-detail",
            headers={
                "Retry-After": "3",
                "Content-Type": "text/html",
                "Content-Length": "1",
                "x-request-id": "private-id",
            },
        )

    with TestClient(HttpObservation(app, app.state.metrics)) as client:
        assert client.get("/").json() == {"data": {"message": "Hello, FastAPI!"}}
        greeting = client.get("/v1/greetings?name=Marin")
        assert set(greeting.json()) == {"data"}
        assert greeting.json()["data"]["message"] == "Hello, Marin!"
        assert "x-request-id" in greeting.headers
        assert client.get("/health/live").json() == {"status": "alive"}
        assert client.get("/metrics").headers["content-type"].startswith("text/plain")
        assert client.get("/test/no-content").content == b""
        limited_response = client.get("/test/limited")
        assert limited_response.status_code == 429
        assert limited_response.headers["retry-after"] == "3"
        assert limited_response.headers["content-type"] == "application/problem+json"
        assert int(limited_response.headers["content-length"]) == len(
            limited_response.content
        )
        assert "private" not in limited_response.text


def test_openapi_matches_response_models_and_media_types() -> None:
    app = create_app(Settings())
    schema = app.openapi()
    responses = schema["paths"]["/v1/greetings"]["get"]["responses"]
    success_ref = responses["200"]["content"]["application/json"]["schema"]["$ref"]
    assert (
        "data"
        in schema["components"]["schemas"][success_ref.rsplit("/", 1)[-1]]["properties"]
    )
    for status in ("404", "405", "422", "500"):
        assert set(responses[status]["content"]) == {"application/problem+json"}
        assert (
            responses[status]["content"]["application/problem+json"]["schema"]["$ref"]
            == "#/components/schemas/Problem"
        )
    assert "FieldError" in schema["components"]["schemas"]
    assert "HTTPValidationError" not in schema["components"]["schemas"]


def test_error_handler_does_not_send_again_after_stream_started() -> None:
    app = create_app(Settings())
    original = ValueError("private-stream-error")

    @app.get("/test/stream")
    def stream() -> StreamingResponse:
        async def body():
            yield b"first"
            raise original

        return StreamingResponse(body())

    sent: list[Message] = []

    async def receive() -> Message:
        await asyncio.Future()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    with pytest.raises(ValueError) as caught:
        asyncio.run(
            HttpObservation(app, app.state.metrics)(
                {
                    "type": "http",
                    "asgi": {"spec_version": "2.4"},
                    "method": "GET",
                    "path": "/test/stream",
                    "root_path": "",
                    "query_string": b"",
                    "headers": [],
                    "scheme": "http",
                    "server": ("test", 80),
                },
                receive,
                send,
            )
        )
    assert caught.value is original
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1
    assert starts[0]["status"] == 200
    assert not any(b"INTERNAL_ERROR" in m.get("body", b"") for m in sent)

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.contracts.greetings import Greeting
from template_fastcrud_api.core.clock import system_clock
from template_fastcrud_api.core.contracts import Clock
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.dependencies.clock import get_clock
from template_fastcrud_api.services.greetings import make_greeting


def fixed_clock() -> datetime:
    return datetime(2026, 9, 7, tzinfo=UTC)


def test_usecase_accepts_clock_without_fastapi() -> None:
    assert make_greeting(name="Marin", clock=fixed_clock) == Greeting(
        message="Hello, Marin!", generated_at=fixed_clock()
    )


@pytest.mark.parametrize("name", ["  Marin  ", "한글", "x" * 80])
def test_greeting_normalizes_input(name: str) -> None:
    app = create_app(Settings(), clock=fixed_clock)
    with TestClient(app) as client:
        response = client.get("/v1/greetings", params={"name": name})
    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "message": f"Hello, {name.strip()}!",
            "generated_at": "2026-09-07T00:00:00Z",
        }
    }


@pytest.mark.parametrize("name", [None, "", " \t ", "x" * 81])
def test_invalid_input_does_not_execute_usecase(
    name: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    usecase = Mock(side_effect=AssertionError("업무 함수가 실행되면 안 됩니다."))
    monkeypatch.setattr(
        "template_fastcrud_api.routers.greetings.make_greeting", usecase
    )
    clock = Mock(side_effect=AssertionError("clock이 실행되면 안 됩니다."))
    app = create_app(Settings(), clock=clock)
    with TestClient(app) as client:
        response = client.get(
            "/v1/greetings", params={} if name is None else {"name": name}
        )
    assert response.status_code == 422
    usecase.assert_not_called()
    clock.assert_not_called()


def test_override_is_app_local_and_restorable() -> None:
    original = Mock(return_value=datetime(2026, 1, 1, tzinfo=UTC))
    first = create_app(Settings(), clock=original)
    second = create_app(Settings(), clock=original)

    def override_clock() -> Clock:
        return fixed_clock

    first.dependency_overrides[get_clock] = override_clock
    with TestClient(first) as first_client, TestClient(second) as second_client:
        path = "/v1/greetings?name=Marin"
        try:
            assert (
                first_client.get(path).json()["data"]["generated_at"]
                == "2026-09-07T00:00:00Z"
            )
            assert (
                second_client.get(path).json()["data"]["generated_at"]
                == "2026-01-01T00:00:00Z"
            )
        finally:
            first.dependency_overrides.clear()
        assert (
            first_client.get(path).json()["data"]["generated_at"]
            == "2026-01-01T00:00:00Z"
        )


def test_app_assembly_does_not_call_clock() -> None:
    clock = Mock(side_effect=AssertionError("조립 시 clock을 실행하면 안 됩니다."))
    create_app(Settings(), clock=clock)
    clock.assert_not_called()


def test_system_clock_returns_utc() -> None:
    assert system_clock().tzinfo is UTC

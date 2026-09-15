import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pytest import MonkeyPatch

from template_fastcrud_api.bootstrap.app import create_app
from template_fastcrud_api.core.settings import Settings


@pytest.mark.parametrize(
    "url",
    [
        "invalid",
        "sqlite+aiosqlite:///:memory:",
        "postgresql://localhost/db",
        "sqlite+aiosqlite:///db?mode=memory",
    ],
)
def test_database_url_rejects_unsupported_modes(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(db_primary_url=url)


def test_environment_overrides_dotenv(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("APP_NAME=from-file\nSERVER_PORT=19080\n")
    monkeypatch.setenv("APP_NAME", "from-environment")
    settings = Settings()
    assert settings.app_name == "from-environment"
    assert settings.server_port == 19080


def test_app_settings_are_independent() -> None:
    first = create_app(Settings(app_name="first", service_version="1"))
    second = create_app(Settings(app_name="second", service_version="2"))
    with TestClient(first) as client:
        assert client.get("/").json() == {"data": {"message": "Hello, FastAPI!"}}
        assert client.get("/openapi.json").json()["info"]["title"] == "first"
    assert second.title == "second"
    assert second.version == "2"


def test_invalid_environment_exits_without_leaking_input(tmp_path: Path) -> None:
    secret = "synthetic-secret-value"
    result = subprocess.run(
        [sys.executable, "-m", "template_fastcrud_api.run"],
        cwd=tmp_path,
        env={**os.environ, "SERVER_PORT": secret},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert "server_port: int_parsing" in result.stderr
    assert secret not in result.stderr + result.stdout

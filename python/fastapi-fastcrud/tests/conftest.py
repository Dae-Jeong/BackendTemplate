import os
import subprocess
import sys
from pathlib import Path

import pytest

from template_fastcrud_api.core.settings import Settings


@pytest.fixture(autouse=True)
def isolate_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """개인 환경 설정과 프로젝트 .env가 테스트에 유입되지 않게 합니다."""
    monkeypatch.chdir(tmp_path)
    for name in tuple(os.environ):
        if name.lower() in Settings.model_fields:
            monkeypatch.delenv(name)


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    url = f"sqlite+aiosqlite:///{tmp_path}/reservations.db"
    config = Path(__file__).resolve().parents[1] / "alembic.ini"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(config), "upgrade", "head"],
        env={**os.environ, "DB_PRIMARY_URL": url},
        check=True,
        capture_output=True,
    )
    return url

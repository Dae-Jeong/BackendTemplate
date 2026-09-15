from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", frozen=True
    )

    app_name: str = Field(default="Backend Template FastCRUD", min_length=1)
    service_version: str = Field(default="0.1.0", min_length=1)
    app_environment: str = Field(default="local", min_length=1, max_length=64)
    server_host: str = Field(default="127.0.0.1", min_length=1)
    server_port: int = Field(default=18092, ge=1, le=65535)
    shutdown_timeout_seconds: int = Field(default=15, ge=1, le=300)
    log_level: Literal["debug", "info", "warning", "error", "critical"] = "info"
    db_primary_url: str = Field(default="", repr=False)
    db_pool_size: int = Field(default=4, ge=1, le=100)
    db_pool_max_overflow: int = Field(default=0, ge=0, le=100)
    db_pool_timeout_seconds: float = Field(default=2, gt=0, le=60)
    db_sqlite_busy_timeout_seconds: float = Field(default=2, gt=0, le=60)

    @field_validator("db_primary_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value:
            return value
        try:
            url = make_url(value)
        except ArgumentError as error:
            raise ValueError("Invalid database URL") from error
        if (
            url.drivername != "sqlite+aiosqlite"
            or not url.database
            or url.database == ":memory:"
            or url.query
            or url.host
        ):
            raise ValueError("Use a file SQLite URL without query options")
        return value

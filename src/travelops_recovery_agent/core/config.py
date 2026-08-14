"""Validated application configuration."""

from enum import StrEnum

from pydantic import PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRAVELOPS_",
        case_sensitive=False,
        extra="forbid",
        frozen=True,
    )

    environment: Environment = Environment.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO
    service_token: SecretStr | None = None
    database_url: SecretStr | None = None
    workflow_event_retention_hours: PositiveInt = 168
    workflow_event_batch_size: PositiveInt = 100
    workflow_sse_heartbeat_seconds: PositiveInt = 10

"""Validated application configuration."""

from enum import StrEnum
from pathlib import Path

from pydantic import PositiveInt, SecretStr, model_validator
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
    failure_injection_enabled: bool = False
    failure_injection_seed: int = 42
    evaluation_report_path: Path = Path("reports/phase-11-evaluation.json")
    phase_12_evaluation_report_path: Path = Path(
        "reports/phase-12-context-evaluation.json"
    )

    @model_validator(mode="after")
    def reject_production_failure_injection(self) -> "Settings":
        if (
            self.environment is Environment.PRODUCTION
            and self.failure_injection_enabled
        ):
            raise ValueError("failure injection cannot be enabled in production")
        return self

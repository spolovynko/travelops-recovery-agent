"""Tests for application configuration."""

import pytest
from pydantic import SecretStr, ValidationError

from travelops_recovery_agent.core.config import Environment, LogLevel, Settings


@pytest.fixture(autouse=True)
def clear_travelops_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "TRAVELOPS_ENVIRONMENT",
        "TRAVELOPS_LOG_LEVEL",
        "TRAVELOPS_SERVICE_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


def test_settings_use_defaults() -> None:
    settings = Settings()

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level is LogLevel.INFO
    assert settings.service_token is None


def test_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRAVELOPS_ENVIRONMENT", "test")
    monkeypatch.setenv("TRAVELOPS_LOG_LEVEL", "WARNING")

    settings = Settings()

    assert settings.environment is Environment.TEST
    assert settings.log_level is LogLevel.WARNING


def test_constructor_values_override_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRAVELOPS_ENVIRONMENT", "test")

    settings = Settings(environment=Environment.PRODUCTION)

    assert settings.environment is Environment.PRODUCTION


def test_invalid_environment_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRAVELOPS_ENVIRONMENT", "staging")

    with pytest.raises(ValidationError) as error:
        Settings()

    message = str(error.value)
    assert "environment" in message
    assert "development" in message
    assert "production" in message


def test_secret_is_masked() -> None:
    secret = "do-not-expose"
    settings = Settings(service_token=SecretStr(secret))

    assert settings.service_token is not None
    assert secret not in repr(settings)
    assert str(settings.service_token) == "**********"

"""Tests for the HTTP application boundary."""

import json
from typing import cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from travelops_recovery_agent.api.app import create_app
from travelops_recovery_agent.api.middleware import REQUEST_ID_HEADER
from travelops_recovery_agent.core.config import Environment, Settings


def test_application_factory_uses_injected_settings() -> None:
    settings = Settings(environment=Environment.TEST)

    app = create_app(settings)

    assert app.state.settings is settings


def test_health_endpoint_reports_liveness() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_describes_health_endpoint() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    schema = app.openapi()

    assert schema["info"]["title"] == "TravelOps Recovery Agent"
    assert "/health" in schema["paths"]
    assert "get" in schema["paths"]["/health"]


def test_response_contains_generated_request_id() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    with TestClient(app) as client:
        response = client.get("/health")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert str(UUID(request_id)) == request_id


def test_request_log_correlates_with_response(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(Settings(environment=Environment.TEST))

    with TestClient(app) as client:
        response = client.get("/health")

    captured = capsys.readouterr()
    events = [
        cast(dict[str, object], json.loads(line))
        for line in captured.err.splitlines()
        if line
    ]
    event = next(
        event for event in events if event["message"] == "http_request_completed"
    )

    assert event["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert event["http_method"] == "GET"
    assert event["http_path"] == "/health"
    assert event["http_status"] == 200


def test_secret_is_not_written_to_request_log(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "do-not-log-this-value"
    app = create_app(
        Settings(
            environment=Environment.TEST,
            service_token=SecretStr(secret),
        )
    )

    with TestClient(app) as client:
        client.get("/health")

    assert secret not in capsys.readouterr().err

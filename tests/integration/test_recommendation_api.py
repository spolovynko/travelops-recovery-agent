"""Real-PostgreSQL recommendation API contract."""

from functools import partial

import pytest
from fastapi.testclient import TestClient

from travelops_recovery_agent.api.app import create_app
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.application.services import RecoveryDataService
from travelops_recovery_agent.core.config import Environment, Settings
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.persistence.session import SessionFactory
from travelops_recovery_agent.persistence.unit_of_work import (
    SqlAlchemyRecoveryDataUnitOfWork,
)


@pytest.mark.integration
def test_workspace_and_recommendation_endpoint_return_validated_evidence(
    clean_session_factory: SessionFactory,
) -> None:
    factory = partial(SqlAlchemyRecoveryDataUnitOfWork, clean_session_factory)
    RecoveryDataService(factory, Environment.TEST).seed(generate_dataset(seed=42))
    query_service = OperationalQueryService(factory)

    with TestClient(
        create_app(
            Settings(environment=Environment.TEST),
            recovery_query_service=query_service,
        )
    ) as client:
        workspace = client.get("/api/v1/recovery-cases/CASE-0001")
        recommendation = client.get("/api/v1/recovery-cases/CASE-0001/recommendation")

    assert workspace.status_code == 200
    assert recommendation.status_code == 200
    assert workspace.json()["recommendation"] == recommendation.json()
    payload = recommendation.json()
    assert payload["outcome"] == "recommended"
    assert payload["recommended_itinerary"]["validation"]["valid"] is True
    assert payload["recommended_itinerary"]["evidence_references"]
    assert payload["other_validated_options"]
    assert all(
        option["validation"]["valid"] for option in payload["other_validated_options"]
    )
    assert all(
        option["validation"]["rejection_reasons"]
        for option in payload["option_results"]
        if not option["validation"]["valid"]
    )

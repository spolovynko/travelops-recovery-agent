"""Developer context inspector API tests."""

from fastapi.testclient import TestClient

from travelops_recovery_agent.api.app import create_app
from travelops_recovery_agent.core.config import Environment, Settings


def test_developer_context_inspector_returns_safe_governed_report() -> None:
    with TestClient(create_app(Settings(environment=Environment.TEST))) as client:
        response = client.get(
            "/api/v1/developer/context-inspector",
            params={
                "case_id": "CASE-0002",
                "task": "investigate",
                "workflow_node": "model_reasoning",
                "operator_role": "recovery_operator",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "travelops.context.v1"
    assert payload["mandatory_evidence_coverage"] == 1
    assert any(
        decision["reason"] == "cross_case_evidence" for decision in payload["decisions"]
    )
    serialized = response.text.lower()
    assert "authorization header" not in serialized
    assert "cookie" not in serialized


def test_context_inspector_is_unavailable_in_production() -> None:
    with TestClient(create_app(Settings(environment=Environment.PRODUCTION))) as client:
        response = client.get(
            "/api/v1/developer/context-inspector",
            params={"case_id": "CASE-0002"},
        )

    assert response.status_code == 404

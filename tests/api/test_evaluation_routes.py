from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from travelops_recovery_agent.api.app import create_app
from travelops_recovery_agent.context_evaluation.harness import run_context_evaluation
from travelops_recovery_agent.core.config import Environment, Settings
from travelops_recovery_agent.evaluation.harness import run_evaluation


def test_evaluation_api_returns_frozen_report(tmp_path: Path) -> None:
    report_path = tmp_path / "evaluation.json"
    report_path.write_text(
        run_evaluation(
            generated_at=datetime(2026, 8, 14, tzinfo=UTC)
        ).model_dump_json(),
        encoding="utf-8",
    )
    settings = Settings(
        environment=Environment.TEST, evaluation_report_path=report_path
    )
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/api/v1/evaluations/phase-11")
    assert response.status_code == 200
    assert response.json()["contract"]["dataset_version"] == "phase-11.0.0"
    assert response.json()["totals"]["booking_writes_without_valid_approval"] == 0


def test_evaluation_api_explains_missing_report(tmp_path: Path) -> None:
    settings = Settings(
        environment=Environment.TEST,
        evaluation_report_path=tmp_path / "missing.json",
    )
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/api/v1/evaluations/phase-11")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"


def test_context_evaluation_api_returns_phase_12_comparison(tmp_path: Path) -> None:
    report_path = tmp_path / "context-evaluation.json"
    report_path.write_text(
        run_context_evaluation(
            generated_at=datetime(2026, 8, 14, tzinfo=UTC)
        ).model_dump_json(),
        encoding="utf-8",
    )
    settings = Settings(
        environment=Environment.TEST,
        phase_12_evaluation_report_path=report_path,
    )

    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/api/v1/evaluations/phase-12")

    assert response.status_code == 200
    assert response.json()["dataset_version"] == "phase-12.0.0"
    assert response.json()["selective_context"]["prohibited_tool_exposure"] == 0

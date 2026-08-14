"""Real-database API and SSE replay tests for durable workflows."""

from functools import partial

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from travelops_recovery_agent.agent.fixtures import RecordedTool
from travelops_recovery_agent.agent.graph import AgentGraphContext, AgentGraphState
from travelops_recovery_agent.agent.tools import ReadOnlyToolDispatcher
from travelops_recovery_agent.api.app import create_app
from travelops_recovery_agent.application.services import RecoveryDataService
from travelops_recovery_agent.core.config import Environment, Settings
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.persistence.session import SessionFactory
from travelops_recovery_agent.persistence.unit_of_work import (
    SqlAlchemyRecoveryDataUnitOfWork,
)
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS
from travelops_recovery_agent.workflow.checkpoints import CheckpointStore
from travelops_recovery_agent.workflow.executor import WorkflowExecutor
from travelops_recovery_agent.workflow.models import WorkflowRun
from travelops_recovery_agent.workflow.persistence import WorkflowRepository
from travelops_recovery_agent.workflow.runtime import UnavailableDecisionModel
from travelops_recovery_agent.workflow.service import DurableWorkflowService


class UnavailableContextFactory:
    def __call__(
        self, run: WorkflowRun, graph_state: AgentGraphState | None
    ) -> AgentGraphContext:
        del run, graph_state
        return AgentGraphContext(
            model=UnavailableDecisionModel(),
            dispatcher=ReadOnlyToolDispatcher(
                RecordedTool(
                    name=item.name, required_permission=item.required_permission
                )
                for item in TOOL_SCHEMAS
            ),
            actor_id="api-test",
        )


@pytest.mark.integration
def test_start_inspect_terminal_sse_and_last_event_id_replay(
    clean_session_factory: SessionFactory,
    test_database_url: str,
) -> None:
    RecoveryDataService(
        partial(SqlAlchemyRecoveryDataUnitOfWork, clean_session_factory),
        Environment.TEST,
    ).seed(generate_dataset(seed=42))
    settings = Settings(
        environment=Environment.TEST,
        database_url=SecretStr(test_database_url),
    )
    store = CheckpointStore(settings).open()
    service = DurableWorkflowService(
        WorkflowRepository(clean_session_factory), store, UnavailableContextFactory()
    )
    executor = WorkflowExecutor(service, max_workers=1)
    try:
        with TestClient(
            create_app(
                settings,
                workflow_service=service,
                workflow_executor=executor,
            )
        ) as client:
            started = client.post("/api/v1/recovery-cases/CASE-0007/workflow-runs")
            assert started.status_code == 202
            run_id = started.json()["run_id"]
            for _ in range(50):
                inspected = client.get(f"/api/v1/workflow-runs/{run_id}")
                if inspected.json()["status"] == "failed":
                    break
            assert inspected.json()["failure_code"] == "model_failure"

            stream = client.get(f"/api/v1/workflow-runs/{run_id}/events")
            assert stream.status_code == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            ids = [
                line.removeprefix("id: ")
                for line in stream.text.splitlines()
                if line.startswith("id: ")
            ]
            assert len(ids) >= 5
            assert len(ids) == len(set(ids))
            assert "workflow.failed" in stream.text

            replay = client.get(
                f"/api/v1/workflow-runs/{run_id}/events",
                headers={"Last-Event-ID": ids[2]},
            )
            replay_ids = [
                line.removeprefix("id: ")
                for line in replay.text.splitlines()
                if line.startswith("id: ")
            ]
            assert replay_ids == ids[3:]
    finally:
        store.close()


@pytest.mark.integration
def test_sse_reports_a_retention_gap_and_snapshot_reset(
    clean_session_factory: SessionFactory,
    test_database_url: str,
) -> None:
    RecoveryDataService(
        partial(SqlAlchemyRecoveryDataUnitOfWork, clean_session_factory),
        Environment.TEST,
    ).seed(generate_dataset(seed=42))
    settings = Settings(
        environment=Environment.TEST,
        database_url=SecretStr(test_database_url),
    )
    store = CheckpointStore(settings).open()
    service = DurableWorkflowService(
        WorkflowRepository(clean_session_factory), store, UnavailableContextFactory()
    )
    run = service.create_run("CASE-0007")
    service.execute(run.identity.run_id)
    with clean_session_factory.begin() as session:
        session.execute(
            text(
                "DELETE FROM workflow.workflow_events "
                "WHERE run_id = :run_id AND sequence <= 3"
            ),
            {"run_id": run.identity.run_id},
        )
    executor = WorkflowExecutor(service, max_workers=1)
    try:
        with TestClient(
            create_app(
                settings,
                workflow_service=service,
                workflow_executor=executor,
            )
        ) as client:
            response = client.get(
                f"/api/v1/workflow-runs/{run.identity.run_id}/events",
                headers={"Last-Event-ID": f"{run.identity.run_id}:1"},
            )
        assert "stream.replay_reset_required" in response.text
        assert '"snapshot_required":true' in response.text
    finally:
        store.close()

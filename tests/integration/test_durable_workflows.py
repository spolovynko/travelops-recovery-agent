"""Real-PostgreSQL durability, restart, lifecycle, and event tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from functools import partial

import pytest
from pydantic import SecretStr
from sqlalchemy import func, inspect, select

from travelops_recovery_agent.agent.fixtures import (
    RECORDED_SCENARIOS,
    SUCCESSFUL_INVESTIGATION,
    RecordedDecisionModel,
    RecordedScenario,
    RecordedTool,
)
from travelops_recovery_agent.agent.graph import AgentGraphContext, AgentGraphState
from travelops_recovery_agent.agent.tools import ReadOnlyToolDispatcher
from travelops_recovery_agent.application.proposals import ProposalService
from travelops_recovery_agent.application.services import RecoveryDataService
from travelops_recovery_agent.core.config import Environment, Settings
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.persistence.models import BookingChangeRecord
from travelops_recovery_agent.persistence.session import (
    SessionFactory,
    create_database_engine,
    create_session_factory,
)
from travelops_recovery_agent.persistence.unit_of_work import (
    SqlAlchemyRecoveryDataUnitOfWork,
)
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS
from travelops_recovery_agent.workflow.checkpoints import CheckpointStore
from travelops_recovery_agent.workflow.models import (
    WorkflowEventType,
    WorkflowRun,
    WorkflowStatus,
)
from travelops_recovery_agent.workflow.persistence import (
    DuplicateActiveRunError,
    WorkflowRepository,
)
from travelops_recovery_agent.workflow.runtime import (
    ApplicationGraphContextFactory,
    UnavailableDecisionModel,
)
from travelops_recovery_agent.workflow.service import (
    DurableWorkflowService,
    ResumeRejectedError,
)


def seed_business_data(session_factory: SessionFactory) -> None:
    service = RecoveryDataService(
        partial(SqlAlchemyRecoveryDataUnitOfWork, session_factory),
        Environment.TEST,
    )
    service.seed(generate_dataset(seed=42))


class RecordedContextFactory:
    """Rebuild a recorded model from the checkpointed model-turn count."""

    def __init__(self, scenario: RecordedScenario) -> None:
        self.scenario = scenario

    def __call__(
        self, run: WorkflowRun, graph_state: AgentGraphState | None
    ) -> AgentGraphContext:
        used_steps = 0 if graph_state is None else graph_state["run_state"].current_turn
        remaining = self.scenario.steps[used_steps:]
        scenario = self.scenario.model_copy(update={"steps": remaining})
        dispatcher = ReadOnlyToolDispatcher(
            RecordedTool(
                name=schema.name,
                required_permission=schema.required_permission,
                fail=schema.name in self.scenario.failing_tools,
            )
            for schema in TOOL_SCHEMAS
        )

        def run_clock() -> datetime:
            return (
                run.created_at + timedelta(seconds=self.scenario.deadline_seconds)
                if self.scenario.start_at_deadline
                else run.created_at
            )

        return AgentGraphContext(
            model=RecordedDecisionModel(scenario),
            dispatcher=dispatcher,
            actor_id="durability-test",
            clock=run_clock,
        )


def build_service(
    repository: WorkflowRepository,
    store: CheckpointStore,
    scenario: RecordedScenario,
) -> DurableWorkflowService:
    return DurableWorkflowService(
        repository,
        store,
        RecordedContextFactory(scenario),
        run_timeout=timedelta(seconds=scenario.deadline_seconds),
        max_model_turns=scenario.max_model_turns,
        max_malformed_retries=scenario.max_malformed_retries,
    )


@pytest.fixture
def workflow_database(
    clean_session_factory: SessionFactory,
    test_database_url: str,
) -> Iterator[tuple[Settings, WorkflowRepository, CheckpointStore]]:
    seed_business_data(clean_session_factory)
    settings = Settings(
        environment=Environment.TEST,
        database_url=SecretStr(test_database_url),
    )
    store = CheckpointStore(settings).open()
    try:
        yield settings, WorkflowRepository(clean_session_factory), store
    finally:
        store.close()


@pytest.mark.integration
def test_checkpoint_tables_are_isolated_from_business_tables(
    workflow_database: tuple[Settings, WorkflowRepository, CheckpointStore],
    test_database_url: str,
) -> None:
    _, _, _ = workflow_database
    engine = create_database_engine(Settings(database_url=SecretStr(test_database_url)))
    try:
        inspector = inspect(engine)
        workflow_tables = set(inspector.get_table_names(schema="workflow"))
        public_tables = set(inspector.get_table_names())
        assert {
            "workflow_runs",
            "workflow_events",
            "checkpoints",
            "checkpoint_blobs",
            "checkpoint_writes",
            "checkpoint_migrations",
        } <= workflow_tables
        assert "checkpoints" not in public_tables
        assert "recovery_cases" in public_tables
    finally:
        engine.dispose()


@pytest.mark.integration
def test_tool_checkpoint_survives_store_disposal_and_resumes_without_repetition(
    workflow_database: tuple[Settings, WorkflowRepository, CheckpointStore],
    test_database_url: str,
) -> None:
    settings, repository, first_store = workflow_database
    first_service = build_service(repository, first_store, SUCCESSFUL_INVESTIGATION)
    run = first_service.create_run("CASE-0007")
    paused = first_service.execute(run.identity.run_id, max_steps=4)
    paused_state = first_service.get_graph_state(run.identity.run_id)
    assert paused.status is WorkflowStatus.PAUSED
    assert paused_state is not None
    assert len(paused_state["run_state"].tool_observations) == 1

    first_store.close()
    restarted_engine = create_database_engine(
        Settings(database_url=SecretStr(test_database_url))
    )
    restarted_store = CheckpointStore(settings).open()
    try:
        restarted_service = build_service(
            WorkflowRepository(create_session_factory(restarted_engine)),
            restarted_store,
            SUCCESSFUL_INVESTIGATION,
        )
        finished = restarted_service.execute(run.identity.run_id)
        finished_state = restarted_service.get_graph_state(run.identity.run_id)
        events = restarted_service.list_events(run.identity.run_id, limit=250)
        assert finished.status is WorkflowStatus.COMPLETED
        assert finished_state is not None
        assert len(finished_state["run_state"].tool_observations) == 1
        assert (
            sum(event.type is WorkflowEventType.TOOL_COMPLETED for event in events) == 1
        )
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    finally:
        restarted_store.close()
        restarted_engine.dispose()


@pytest.mark.integration
def test_validated_recommendation_checkpoint_resumes_without_duplicate_work(
    workflow_database: tuple[Settings, WorkflowRepository, CheckpointStore],
    test_database_url: str,
) -> None:
    settings, repository, first_store = workflow_database
    first_engine = create_database_engine(
        Settings(database_url=SecretStr(test_database_url))
    )
    first_sessions = create_session_factory(first_engine)
    first_service = DurableWorkflowService(
        repository,
        first_store,
        ApplicationGraphContextFactory(
            first_sessions,
            model_factory=lambda _: UnavailableDecisionModel(),
        ),
        enable_recommendations=True,
    )
    run = first_service.create_run("CASE-0001")
    paused = first_service.execute(run.identity.run_id, max_steps=1)
    paused_state = first_service.get_graph_state(run.identity.run_id)
    assert paused.status is WorkflowStatus.PAUSED
    assert paused_state is not None
    assert paused_state["run_state"].recommendation is not None
    assert tuple(paused_state["node_history"]) == ("validated_recommendation",)

    first_store.close()
    first_engine.dispose()
    restarted_engine = create_database_engine(
        Settings(database_url=SecretStr(test_database_url))
    )
    restarted_store = CheckpointStore(settings).open()
    try:
        restarted_service = DurableWorkflowService(
            WorkflowRepository(create_session_factory(restarted_engine)),
            restarted_store,
            ApplicationGraphContextFactory(
                create_session_factory(restarted_engine),
                model_factory=lambda _: UnavailableDecisionModel(),
            ),
            enable_recommendations=True,
        )
        finished = restarted_service.execute(run.identity.run_id)
        state = restarted_service.get_graph_state(run.identity.run_id)
        events = restarted_service.list_events(run.identity.run_id, limit=250)

        assert finished.status is WorkflowStatus.COMPLETED
        assert state is not None
        assert state["run_state"].recommendation is not None
        assert state["run_state"].recommendation.recommended_itinerary is not None
        assert tuple(state["node_history"]) == (
            "validated_recommendation",
            "completion",
        )
        recommendation_events = [
            event
            for event in events
            if event.type
            in {
                WorkflowEventType.RECOMMENDATION_COMPLETED,
                WorkflowEventType.RECOMMENDATION_ESCALATED,
            }
        ]
        assert [event.type for event in recommendation_events] == [
            WorkflowEventType.RECOMMENDATION_COMPLETED
        ]
    finally:
        restarted_store.close()
        restarted_engine.dispose()


@pytest.mark.integration
def test_phase_ten_pauses_for_stored_approval_and_executes_once_after_restart(
    workflow_database: tuple[Settings, WorkflowRepository, CheckpointStore],
    test_database_url: str,
) -> None:
    settings, repository, first_store = workflow_database
    first_engine = create_database_engine(
        Settings(database_url=SecretStr(test_database_url))
    )
    sessions = create_session_factory(first_engine)
    context = ApplicationGraphContextFactory(
        sessions,
        model_factory=lambda _: UnavailableDecisionModel(),
        enable_proposals=True,
    )
    service = DurableWorkflowService(
        repository,
        first_store,
        context,
        enable_recommendations=True,
        enable_proposals=True,
    )
    run = service.create_run("CASE-0002")
    paused = service.execute(run.identity.run_id)
    state = service.get_graph_state(run.identity.run_id)
    assert paused.status is WorkflowStatus.PAUSED
    assert state is not None
    assert state["run_state"].proposal_status == "awaiting_approval"
    proposal_id = state["run_state"].proposal_id
    assert proposal_id is not None

    proposal_service = ProposalService(sessions)
    proposal = proposal_service.get(proposal_id).proposal
    proposal_service.decide(
        proposal_id,
        version=proposal.version,
        itinerary_fingerprint=proposal.itinerary_fingerprint,
        approve=True,
        actor_id="operator-1",
        actor_role="recovery_operator",
        correlation_id=run.identity.run_id,
    )

    # Stop after the effect node to model a backend loss before graph completion.
    after_effect = service.execute(run.identity.run_id, max_steps=1)
    assert after_effect.status is WorkflowStatus.PAUSED
    with sessions() as session:
        assert session.scalar(select(func.count(BookingChangeRecord.id))) == 1

    first_store.close()
    first_engine.dispose()
    restarted_engine = create_database_engine(
        Settings(database_url=SecretStr(test_database_url))
    )
    restarted_store = CheckpointStore(settings).open()
    try:
        restarted_sessions = create_session_factory(restarted_engine)
        restarted = DurableWorkflowService(
            WorkflowRepository(restarted_sessions),
            restarted_store,
            ApplicationGraphContextFactory(
                restarted_sessions,
                model_factory=lambda _: UnavailableDecisionModel(),
                enable_proposals=True,
            ),
            enable_recommendations=True,
            enable_proposals=True,
        )
        completed = restarted.execute(run.identity.run_id)
        final_state = restarted.get_graph_state(run.identity.run_id)
        assert completed.status is WorkflowStatus.COMPLETED
        assert final_state is not None
        assert final_state["run_state"].proposal_status == "executed"
        with restarted_sessions() as session:
            assert session.scalar(select(func.count(BookingChangeRecord.id))) == 1
    finally:
        restarted_store.close()
        restarted_engine.dispose()


@pytest.mark.integration
@pytest.mark.parametrize("scenario_name", tuple(RECORDED_SCENARIOS))
def test_every_recorded_scenario_reaches_its_phase_seven_terminal_shape(
    scenario_name: str,
    workflow_database: tuple[Settings, WorkflowRepository, CheckpointStore],
) -> None:
    _, repository, store = workflow_database
    scenario = RECORDED_SCENARIOS[scenario_name]
    service = build_service(repository, store, scenario)
    run = service.create_run("CASE-0007")

    terminal = service.execute(run.identity.run_id)
    state = service.get_graph_state(run.identity.run_id)

    assert terminal.status.is_terminal
    assert state is not None
    assert state["run_state"].status.value == terminal.status.value


@pytest.mark.integration
def test_duplicate_start_cancel_and_repeated_resume_are_idempotent(
    workflow_database: tuple[Settings, WorkflowRepository, CheckpointStore],
) -> None:
    _, repository, store = workflow_database
    service = build_service(repository, store, SUCCESSFUL_INVESTIGATION)
    run = service.create_run("CASE-0007")
    with pytest.raises(DuplicateActiveRunError) as duplicate:
        service.create_run("CASE-0007")
    assert duplicate.value.run_id == run.identity.run_id

    first_cancel = service.request_cancellation(run.identity.run_id)
    second_cancel = service.request_cancellation(run.identity.run_id)
    assert second_cancel.cancel_requested_at == first_cancel.cancel_requested_at
    cancelled = service.execute(run.identity.run_id)
    assert cancelled.status is WorkflowStatus.CANCELLED
    events = service.list_events(run.identity.run_id, limit=250)
    assert (
        sum(event.type is WorkflowEventType.CANCELLATION_REQUESTED for event in events)
        == 1
    )
    assert sum(event.type is WorkflowEventType.RUN_CANCELLED for event in events) == 1
    with pytest.raises(ResumeRejectedError):
        service.execute(run.identity.run_id)


@pytest.mark.integration
def test_event_retention_removes_only_expired_progress_rows(
    workflow_database: tuple[Settings, WorkflowRepository, CheckpointStore],
) -> None:
    _, repository, store = workflow_database
    service = build_service(repository, store, SUCCESSFUL_INVESTIGATION)
    run = service.create_run("CASE-0007")
    service.execute(run.identity.run_id)

    removed = service.apply_event_retention(timedelta(seconds=-1))

    assert removed > 0
    assert service.list_events(run.identity.run_id) == ()
    assert service.get_run(run.identity.run_id).status is WorkflowStatus.COMPLETED

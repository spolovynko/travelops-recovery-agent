"""Safe HTTP projections for durable investigations and progress events."""

from datetime import datetime
from typing import Annotated, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from travelops_recovery_agent.agent.graph import AgentGraphState, GraphNode
from travelops_recovery_agent.application.proposal_models import ProposalStatus
from travelops_recovery_agent.application.recommendation_models import (
    RecommendationResult,
)
from travelops_recovery_agent.workflow.models import WorkflowRun, WorkflowStatus


class WorkflowViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SafeToolActivityView(WorkflowViewModel):
    observation_id: str
    tool_name: str
    ok: bool


class WorkflowRunView(WorkflowViewModel):
    run_id: str
    thread_id: str
    case_id: str
    status: WorkflowStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested: bool
    current_node: GraphNode | None
    completed_steps: tuple[GraphNode, ...]
    current_turn: Annotated[int, Field(ge=0)]
    retry_count: Annotated[int, Field(ge=0)]
    tool_activity: tuple[SafeToolActivityView, ...]
    evidence_ids: tuple[str, ...]
    outcome_summary: str | None
    information_question: str | None
    missing_fields: tuple[str, ...]
    failure_code: str | None
    failure_message: str | None
    last_event_sequence: Annotated[int, Field(ge=0)]
    recommendation: RecommendationResult | None
    proposal_id: str | None = None
    proposal_status: ProposalStatus | None = None
    proposal_execution_result: dict[str, JsonValue] | None = None


class WorkflowConflictView(WorkflowViewModel):
    error: str
    existing_run_id: str | None = None


def workflow_run_view(
    run: WorkflowRun, state: AgentGraphState | None
) -> WorkflowRunView:
    if state is None:
        return WorkflowRunView(
            run_id=run.identity.run_id,
            thread_id=run.identity.thread_id,
            case_id=run.identity.case_id,
            status=run.status,
            created_at=run.created_at,
            updated_at=run.updated_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            cancel_requested=run.cancel_requested_at is not None,
            current_node="intake" if run.status.is_active else None,
            completed_steps=(),
            current_turn=0,
            retry_count=0,
            tool_activity=(),
            evidence_ids=(),
            outcome_summary=None,
            information_question=None,
            missing_fields=(),
            failure_code=run.failure_code,
            failure_message=None,
            last_event_sequence=run.last_event_sequence,
            recommendation=None,
            proposal_id=None,
            proposal_status=None,
            proposal_execution_result=None,
        )
    agent_state = state["run_state"]
    outcome = agent_state.final_outcome
    information = agent_state.information_request
    failure = agent_state.failure
    current_node: GraphNode | None = None
    if run.status.is_active and state["route"] != "end":
        current_node = cast(GraphNode, state["route"])
    return WorkflowRunView(
        run_id=run.identity.run_id,
        thread_id=run.identity.thread_id,
        case_id=run.identity.case_id,
        status=run.status,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        cancel_requested=run.cancel_requested_at is not None,
        current_node=current_node,
        completed_steps=tuple(state["node_history"]),
        current_turn=agent_state.current_turn,
        retry_count=agent_state.malformed_retry_count,
        tool_activity=tuple(
            SafeToolActivityView(
                observation_id=item.observation_id,
                tool_name=item.tool_name,
                ok=item.ok,
            )
            for item in agent_state.tool_observations
        ),
        evidence_ids=tuple(
            item.observation_id for item in agent_state.tool_observations
        ),
        outcome_summary=None if outcome is None else outcome.summary,
        information_question=None if information is None else information.question,
        missing_fields=() if information is None else information.missing_fields,
        failure_code=run.failure_code,
        failure_message=None if failure is None else failure.message,
        last_event_sequence=run.last_event_sequence,
        recommendation=agent_state.recommendation,
        proposal_id=agent_state.proposal_id,
        proposal_status=(
            ProposalStatus(agent_state.proposal_status)
            if agent_state.proposal_status
            else None
        ),
        proposal_execution_result=agent_state.proposal_execution_result,
    )

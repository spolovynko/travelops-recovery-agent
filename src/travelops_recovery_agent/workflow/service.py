"""Durable boundary-by-boundary execution around the Phase 7 graph."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from langchain_core.runnables import RunnableConfig

from travelops_recovery_agent.agent.graph import (
    AgentGraphState,
    GraphNode,
    build_recovery_graph,
    create_graph_state,
)
from travelops_recovery_agent.agent.models import (
    AgentRunState,
    CallToolDecision,
    ConversationMessage,
    ConversationRole,
    RunBudget,
    RunStatus,
)
from travelops_recovery_agent.workflow.checkpoints import CheckpointStore
from travelops_recovery_agent.workflow.models import (
    SafePayload,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowRun,
    WorkflowStatus,
    new_workflow_identity,
)
from travelops_recovery_agent.workflow.persistence import WorkflowRepository
from travelops_recovery_agent.workflow.runtime import GraphContextFactory


def utc_now() -> datetime:
    return datetime.now(UTC)


class ResumeRejectedError(RuntimeError):
    """Raised when another runner owns a run or the run is already terminal."""


class DurableWorkflowService:
    """Coordinate checkpoints, leases, cancellation, and safe event projection."""

    def __init__(
        self,
        repository: WorkflowRepository,
        checkpoint_store: CheckpointStore,
        context_factory: GraphContextFactory,
        *,
        clock: Callable[[], datetime] = utc_now,
        lease_duration: timedelta = timedelta(seconds=30),
        run_timeout: timedelta = timedelta(minutes=5),
        max_model_turns: int = 8,
        max_malformed_retries: int = 1,
        enable_recommendations: bool = False,
        enable_proposals: bool = False,
    ) -> None:
        self._repository = repository
        self._checkpoint_store = checkpoint_store
        self._context_factory = context_factory
        self._clock = clock
        self._lease_duration = lease_duration
        self._run_timeout = run_timeout
        self._max_model_turns = max_model_turns
        self._max_malformed_retries = max_malformed_retries
        self._runner_id = f"runner-{uuid4().hex}"
        self._initial_node: GraphNode = (
            "validated_recommendation" if enable_recommendations else "intake"
        )
        self._graph = build_recovery_graph(
            checkpoint_store.saver,
            enable_recommendations=enable_recommendations,
            enable_proposals=enable_proposals,
        )

    def create_run(self, case_id: str) -> WorkflowRun:
        now = self._clock()
        run = self._repository.create_run(new_workflow_identity(case_id), now)
        self._repository.append_event(
            run.identity.run_id,
            WorkflowEventType.RUN_CREATED,
            now,
            {"case_id": case_id, "status": WorkflowStatus.CREATED.value},
        )
        return self._repository.get_run(run.identity.run_id)

    def get_run(self, run_id: str) -> WorkflowRun:
        return self._repository.get_run(run_id)

    def get_graph_state(self, run_id: str) -> AgentGraphState | None:
        run = self._repository.get_run(run_id)
        snapshot = self._graph.get_state(self._config(run))
        if not snapshot.values:
            return None
        return cast(AgentGraphState, snapshot.values)

    def list_events(
        self, run_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> tuple[WorkflowEvent, ...]:
        return self._repository.list_events(
            run_id, after_sequence=after_sequence, limit=limit
        )

    def oldest_event_sequence(self, run_id: str) -> int | None:
        self._repository.get_run(run_id)
        return self._repository.oldest_event_sequence(run_id)

    def apply_event_retention(self, retention: timedelta) -> int:
        return self._repository.delete_events_before(self._clock() - retention)

    def request_cancellation(self, run_id: str) -> WorkflowRun:
        before = self._repository.get_run(run_id)
        if before.status.is_terminal or before.cancel_requested_at is not None:
            return before
        now = self._clock()
        self._repository.request_cancellation(run_id, now)
        self._repository.append_event(
            run_id,
            WorkflowEventType.CANCELLATION_REQUESTED,
            now,
            {"status": WorkflowStatus.CANCELLING.value},
        )
        return self._repository.get_run(run_id)

    def execute(self, run_id: str, *, max_steps: int | None = None) -> WorkflowRun:
        now = self._clock()
        lease_owner = f"{self._runner_id}:{uuid4().hex}"
        claimed = self._repository.acquire_lease(
            run_id,
            owner=lease_owner,
            now=now,
            duration=self._lease_duration,
        )
        if claimed is None:
            raise ResumeRejectedError("workflow is already running or terminal")

        existing_state = self.get_graph_state(run_id)
        starting = existing_state is None
        self._repository.append_event(
            run_id,
            (
                WorkflowEventType.RUN_STARTED
                if starting
                else WorkflowEventType.RUN_RESUMED
            ),
            now,
            {"status": WorkflowStatus.RUNNING.value},
        )
        context = self._context_factory(claimed, existing_state)
        graph_input: AgentGraphState | None = (
            create_graph_state(self._initial_state(claimed)) if starting else None
        )
        completed_steps = 0

        while True:
            current_run = self._repository.get_run(run_id)
            if current_run.cancel_requested_at is not None:
                return self._cancel_at_boundary(current_run, lease_owner)
            renewed = self._repository.acquire_lease(
                run_id,
                owner=lease_owner,
                now=self._clock(),
                duration=self._lease_duration,
            )
            if renewed is None:
                raise ResumeRejectedError("workflow lease could not be renewed")

            before = self.get_graph_state(run_id)
            next_node = self._next_node(run_id, before)
            self._emit_node_started(run_id, next_node, before)
            self._graph.invoke(
                graph_input,
                config=self._config(current_run),
                context=context,
                interrupt_after="*",
                durability="sync",
            )
            graph_input = None
            after = self.get_graph_state(run_id)
            if after is None:
                raise RuntimeError("graph checkpoint was not persisted")
            self._emit_node_completed(run_id, next_node, before, after)
            completed_steps += 1

            snapshot = self._graph.get_state(self._config(current_run))
            if not snapshot.next:
                return self._finish_from_graph(current_run, after, lease_owner)
            if (
                next_node == "proposal_approval"
                and after["run_state"].proposal_status == "awaiting_approval"
            ):
                paused_at = self._clock()
                paused = self._repository.release_lease(
                    run_id,
                    owner=lease_owner,
                    now=paused_at,
                    status=WorkflowStatus.PAUSED,
                )
                self._repository.append_event(
                    run_id,
                    WorkflowEventType.RUN_PAUSED,
                    paused_at,
                    {
                        "status": WorkflowStatus.PAUSED.value,
                        "reason": "awaiting_authoritative_approval",
                        "proposal_id": after["run_state"].proposal_id,
                    },
                )
                return self._repository.get_run(paused.identity.run_id)
            if max_steps is not None and completed_steps >= max_steps:
                paused_at = self._clock()
                paused = self._repository.release_lease(
                    run_id,
                    owner=lease_owner,
                    now=paused_at,
                    status=WorkflowStatus.PAUSED,
                )
                self._repository.append_event(
                    run_id,
                    WorkflowEventType.RUN_PAUSED,
                    paused_at,
                    {"status": WorkflowStatus.PAUSED.value},
                )
                return self._repository.get_run(paused.identity.run_id)

    def _config(self, run: WorkflowRun) -> RunnableConfig:
        return {
            "configurable": {"thread_id": run.identity.thread_id},
            "recursion_limit": self._max_model_turns * 5 + 10,
        }

    def _initial_state(self, run: WorkflowRun) -> AgentRunState:
        started_at = run.created_at
        return AgentRunState(
            run_id=run.identity.run_id,
            case_id=run.identity.case_id,
            messages=(
                ConversationMessage(
                    role=ConversationRole.OPERATOR,
                    content=f"Investigate recovery case {run.identity.case_id}.",
                ),
            ),
            started_at=started_at,
            budget=RunBudget(
                max_model_turns=self._max_model_turns,
                max_malformed_retries=self._max_malformed_retries,
                deadline_at=started_at + self._run_timeout,
            ),
        )

    def _next_node(self, run_id: str, state: AgentGraphState | None) -> GraphNode:
        run = self._repository.get_run(run_id)
        snapshot = self._graph.get_state(self._config(run))
        if snapshot.next:
            return cast(GraphNode, snapshot.next[0])
        if state is None:
            return self._initial_node
        raise RuntimeError("terminal graph has no next node")

    def _emit_node_started(
        self,
        run_id: str,
        node: GraphNode,
        state: AgentGraphState | None,
    ) -> None:
        now = self._clock()
        self._repository.append_event(
            run_id,
            WorkflowEventType.NODE_STARTED,
            now,
            {"node": node},
        )
        if node == "tool_execution" and state is not None:
            decision = state["pending_decision"]
            if isinstance(decision, CallToolDecision):
                self._repository.append_event(
                    run_id,
                    WorkflowEventType.TOOL_STARTED,
                    now,
                    {"tool_name": decision.tool_name},
                )

    def _emit_node_completed(
        self,
        run_id: str,
        node: GraphNode,
        before: AgentGraphState | None,
        after: AgentGraphState,
    ) -> None:
        now = self._clock()
        run_state = after["run_state"]
        self._repository.append_event(
            run_id,
            WorkflowEventType.NODE_COMPLETED,
            now,
            {
                "node": node,
                "run_status": run_state.status.value,
                "current_turn": run_state.current_turn,
            },
        )
        previous_observations = (
            0 if before is None else len(before["run_state"].tool_observations)
        )
        for observation in run_state.tool_observations[previous_observations:]:
            tool_payload: SafePayload = {
                "tool_name": observation.tool_name,
                "ok": observation.ok,
                "observation_id": observation.observation_id,
            }
            self._repository.append_event(
                run_id, WorkflowEventType.TOOL_COMPLETED, now, tool_payload
            )
            self._repository.append_event(
                run_id,
                WorkflowEventType.EVIDENCE_RECORDED,
                now,
                {
                    "observation_id": observation.observation_id,
                    "tool_name": observation.tool_name,
                },
            )
        before_retries = (
            0 if before is None else before["run_state"].malformed_retry_count
        )
        if run_state.malformed_retry_count > before_retries:
            self._repository.append_event(
                run_id,
                WorkflowEventType.RETRY_SCHEDULED,
                now,
                {
                    "reason_code": "malformed_output",
                    "retry_count": run_state.malformed_retry_count,
                },
            )
        if node == "validated_recommendation" and run_state.recommendation is not None:
            recommendation = run_state.recommendation
            recommended = recommendation.recommended_itinerary
            self._repository.append_event(
                run_id,
                (
                    WorkflowEventType.RECOMMENDATION_COMPLETED
                    if recommended is not None
                    else WorkflowEventType.RECOMMENDATION_ESCALATED
                ),
                now,
                {
                    "outcome": recommendation.outcome.value,
                    "recommended_option_id": (
                        None if recommended is None else recommended.option_id
                    ),
                    "validated_option_count": len(
                        recommendation.other_validated_options
                    )
                    + (1 if recommended is not None else 0),
                    "rejected_option_count": len(
                        [
                            item
                            for item in recommendation.option_results
                            if not item.validation.valid
                        ]
                    ),
                    "evidence_completeness": (
                        recommendation.evidence_completeness.value
                    ),
                },
            )
        if node == "proposal_approval" and run_state.proposal_id is not None:
            before_status = (
                None if before is None else before["run_state"].proposal_status
            )
            proposal_payload: SafePayload = {
                "proposal_id": run_state.proposal_id,
                "proposal_status": run_state.proposal_status,
            }
            if run_state.proposal_status == "awaiting_approval":
                self._repository.append_event(
                    run_id,
                    WorkflowEventType.PROPOSAL_AWAITING_APPROVAL,
                    now,
                    proposal_payload,
                )
            elif run_state.proposal_status == "executed":
                if before_status == "awaiting_approval":
                    self._repository.append_event(
                        run_id,
                        WorkflowEventType.APPROVAL_RECORDED,
                        now,
                        proposal_payload,
                    )
                self._repository.append_event(
                    run_id,
                    WorkflowEventType.REVALIDATION_COMPLETED,
                    now,
                    {**proposal_payload, "status": "passed"},
                )
                self._repository.append_event(
                    run_id,
                    WorkflowEventType.EXECUTION_COMPLETED,
                    now,
                    {**proposal_payload, "status": "succeeded"},
                )
            elif run_state.proposal_status in {
                "rejected",
                "expired",
                "revalidation_failed",
                "execution_failed",
            }:
                self._repository.append_event(
                    run_id,
                    WorkflowEventType.PROPOSAL_ESCALATED,
                    now,
                    proposal_payload,
                )

    def _finish_from_graph(
        self, run: WorkflowRun, state: AgentGraphState, lease_owner: str
    ) -> WorkflowRun:
        now = self._clock()
        agent_state = state["run_state"]
        status_map = {
            RunStatus.COMPLETED: WorkflowStatus.COMPLETED,
            RunStatus.AWAITING_INFORMATION: WorkflowStatus.AWAITING_INFORMATION,
            RunStatus.FAILED: WorkflowStatus.FAILED,
        }
        workflow_status = status_map.get(agent_state.status)
        if workflow_status is None:
            raise RuntimeError("graph ended without a trusted terminal state")
        failure_code = (
            None if agent_state.failure is None else agent_state.failure.code.value
        )
        finished = self._repository.release_lease(
            run.identity.run_id,
            owner=lease_owner,
            now=now,
            status=workflow_status,
            failure_code=failure_code,
        )
        event_type = {
            WorkflowStatus.COMPLETED: WorkflowEventType.RUN_COMPLETED,
            WorkflowStatus.AWAITING_INFORMATION: (
                WorkflowEventType.RUN_AWAITING_INFORMATION
            ),
            WorkflowStatus.FAILED: WorkflowEventType.RUN_FAILED,
        }[workflow_status]
        payload: SafePayload = {"status": workflow_status.value}
        if agent_state.final_outcome is not None:
            payload.update(
                {
                    "summary": agent_state.final_outcome.summary,
                    "evidence_ids": list(agent_state.final_outcome.evidence_ids),
                    "limitations": list(agent_state.final_outcome.limitations),
                }
            )
        elif agent_state.information_request is not None:
            payload.update(
                {
                    "question": agent_state.information_request.question,
                    "missing_fields": list(
                        agent_state.information_request.missing_fields
                    ),
                }
            )
        elif agent_state.failure is not None:
            payload.update(
                {
                    "error_code": agent_state.failure.code.value,
                    "message": agent_state.failure.message,
                }
            )
        self._repository.append_event(
            run.identity.run_id,
            event_type,
            now,
            payload,
        )
        return self._repository.get_run(finished.identity.run_id)

    def _cancel_at_boundary(self, run: WorkflowRun, lease_owner: str) -> WorkflowRun:
        now = self._clock()
        cancelled = self._repository.release_lease(
            run.identity.run_id,
            owner=lease_owner,
            now=now,
            status=WorkflowStatus.CANCELLED,
        )
        self._repository.append_event(
            run.identity.run_id,
            WorkflowEventType.RUN_CANCELLED,
            now,
            {"status": WorkflowStatus.CANCELLED.value},
        )
        return self._repository.get_run(cancelled.identity.run_id)

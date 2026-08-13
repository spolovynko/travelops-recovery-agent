"""Deterministic routing and equivalence tests for the Phase 7 LangGraph."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from travelops_recovery_agent.agent.fixtures import (
    RECORDED_SCENARIOS,
    RecordedDecisionModel,
    RecordedScenario,
    RecordedTool,
)
from travelops_recovery_agent.agent.graph import (
    AgentGraphState,
    GraphNode,
    RecoveryGraphRunner,
)
from travelops_recovery_agent.agent.loop import AgentLoop
from travelops_recovery_agent.agent.models import (
    AgentFailureCode,
    AgentOutcome,
    AgentRunState,
    ConversationMessage,
    ConversationRole,
    RunBudget,
    RunStatus,
)
from travelops_recovery_agent.agent.tools import ReadOnlyToolDispatcher
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS

STARTED_AT = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def build_state(scenario: RecordedScenario) -> AgentRunState:
    """Build the same trusted initial state for either orchestrator."""

    return AgentRunState(
        run_id=f"RUN-{scenario.name}",
        case_id="CASE-0007",
        messages=(
            ConversationMessage(
                role=ConversationRole.OPERATOR,
                content="Investigate recovery case CASE-0007.",
            ),
        ),
        started_at=STARTED_AT,
        budget=RunBudget(
            max_model_turns=scenario.max_model_turns,
            max_malformed_retries=scenario.max_malformed_retries,
            deadline_at=(STARTED_AT + timedelta(seconds=scenario.deadline_seconds)),
        ),
    )


def build_dispatcher(scenario: RecordedScenario) -> ReadOnlyToolDispatcher:
    """Build the same complete recorded Phase 4 dispatcher for either path."""

    return ReadOnlyToolDispatcher(
        RecordedTool(
            name=schema.name,
            required_permission=schema.required_permission,
            fail=schema.name in scenario.failing_tools,
        )
        for schema in TOOL_SCHEMAS
    )


def build_clock(scenario: RecordedScenario) -> Callable[[], datetime]:
    """Return the fixed scenario clock used by both orchestrators."""

    deadline = STARTED_AT + timedelta(seconds=scenario.deadline_seconds)
    return (lambda: deadline) if scenario.start_at_deadline else (lambda: STARTED_AT)


def run_graph_scenario(
    name: str,
) -> tuple[AgentRunState, tuple[AgentGraphState, ...], RecordedDecisionModel]:
    """Run one recording and retain every complete graph-state snapshot."""

    scenario = RECORDED_SCENARIOS[name]
    model = RecordedDecisionModel(scenario)
    runner = RecoveryGraphRunner(
        model,
        build_dispatcher(scenario),
        actor_id="recorded-agent",
        clock=build_clock(scenario),
    )
    snapshots = tuple(runner.stream_states(build_state(scenario)))
    return snapshots[-1]["run_state"], snapshots, model


@pytest.mark.parametrize(
    ("name", "expected_status", "expected_failure"),
    [
        ("successful_investigation", RunStatus.COMPLETED, None),
        ("ask_for_information", RunStatus.AWAITING_INFORMATION, None),
        ("normal_finish", RunStatus.COMPLETED, None),
        ("tool_failure", RunStatus.FAILED, AgentFailureCode.TOOL_FAILURE),
        ("unknown_tool", RunStatus.FAILED, AgentFailureCode.UNKNOWN_TOOL),
        (
            "repeated_tool_call",
            RunStatus.FAILED,
            AgentFailureCode.REPEATED_TOOL_CALL,
        ),
        ("malformed_recovery", RunStatus.COMPLETED, None),
        (
            "malformed_exhaustion",
            RunStatus.FAILED,
            AgentFailureCode.MALFORMED_DECISION,
        ),
        (
            "maximum_turn_exhaustion",
            RunStatus.FAILED,
            AgentFailureCode.BUDGET_EXHAUSTED,
        ),
        (
            "deadline_exhaustion",
            RunStatus.FAILED,
            AgentFailureCode.DEADLINE_EXCEEDED,
        ),
    ],
)
def test_graph_replays_every_required_deterministic_scenario(
    name: str,
    expected_status: RunStatus,
    expected_failure: AgentFailureCode | None,
) -> None:
    result, _, _ = run_graph_scenario(name)

    assert result.status is expected_status
    if expected_failure is None:
        assert result.failure is None
    else:
        assert result.failure is not None
        assert result.failure.code is expected_failure


@pytest.mark.parametrize("name", tuple(RECORDED_SCENARIOS))
def test_manual_loop_and_graph_have_identical_trusted_results(name: str) -> None:
    scenario = RECORDED_SCENARIOS[name]
    manual_model = RecordedDecisionModel(scenario)
    graph_model = RecordedDecisionModel(scenario)
    manual_result = AgentLoop(
        manual_model,
        build_dispatcher(scenario),
        actor_id="equivalence-agent",
        clock=build_clock(scenario),
    ).run(build_state(scenario))
    graph_result = RecoveryGraphRunner(
        graph_model,
        build_dispatcher(scenario),
        actor_id="equivalence-agent",
        clock=build_clock(scenario),
    ).run(build_state(scenario))

    assert graph_result.status is manual_result.status
    assert graph_result.final_outcome == manual_result.final_outcome
    assert graph_result.information_request == manual_result.information_request
    assert (
        graph_result.failure.code if graph_result.failure is not None else None
    ) == (manual_result.failure.code if manual_result.failure is not None else None)
    assert tuple(item.tool_name for item in graph_result.tool_observations) == tuple(
        item.tool_name for item in manual_result.tool_observations
    )
    assert graph_result.tool_observations == manual_result.tool_observations
    assert (
        graph_result.final_outcome.evidence_ids
        if graph_result.final_outcome is not None
        else ()
    ) == (
        manual_result.final_outcome.evidence_ids
        if manual_result.final_outcome is not None
        else ()
    )
    assert graph_result.model_dump_json() == manual_result.model_dump_json()
    assert [request.model_dump_json() for request in graph_model.requests] == [
        request.model_dump_json() for request in manual_model.requests
    ]


@pytest.mark.parametrize(
    ("name", "expected_history"),
    [
        (
            "successful_investigation",
            (
                "intake",
                "model_reasoning",
                "decision_validation",
                "tool_execution",
                "outcome_handling",
                "model_reasoning",
                "decision_validation",
                "outcome_handling",
                "completion",
            ),
        ),
        (
            "ask_for_information",
            (
                "intake",
                "model_reasoning",
                "decision_validation",
                "information_or_escalation",
                "completion",
            ),
        ),
        (
            "normal_finish",
            (
                "intake",
                "model_reasoning",
                "decision_validation",
                "outcome_handling",
                "completion",
            ),
        ),
        (
            "unknown_tool",
            (
                "intake",
                "model_reasoning",
                "decision_validation",
                "tool_execution",
                "safe_failure",
            ),
        ),
        (
            "malformed_recovery",
            (
                "intake",
                "model_reasoning",
                "decision_validation",
                "model_reasoning",
                "decision_validation",
                "outcome_handling",
                "completion",
            ),
        ),
        (
            "deadline_exhaustion",
            ("intake", "model_reasoning", "safe_failure"),
        ),
    ],
)
def test_node_history_makes_conditional_routing_explicit(
    name: str,
    expected_history: tuple[GraphNode, ...],
) -> None:
    _, snapshots, _ = run_graph_scenario(name)

    assert snapshots[-1]["node_history"] == expected_history
    assert tuple(len(snapshot["node_history"]) for snapshot in snapshots) == tuple(
        range(len(snapshots))
    )


def test_complete_state_is_inspectable_after_every_node() -> None:
    result, snapshots, _ = run_graph_scenario("successful_investigation")

    assert len(snapshots) == 10
    assert snapshots[0]["node_history"] == ()
    assert snapshots[-1]["run_state"] == result
    for snapshot in snapshots:
        assert set(snapshot) == {
            "run_state",
            "node_history",
            "route",
            "pending_decision",
            "model_error_code",
            "pending_failure",
        }
        AgentRunState.model_validate(snapshot["run_state"])
        serialized = str(snapshot).lower()
        assert "database_url" not in serialized
        assert "password" not in serialized
        assert "repository" not in serialized
        assert "dispatcher" not in serialized


def test_graph_topology_contains_every_required_node_and_terminal() -> None:
    scenario = RECORDED_SCENARIOS["normal_finish"]
    runner = RecoveryGraphRunner(
        RecordedDecisionModel(scenario),
        build_dispatcher(scenario),
        actor_id="topology-agent",
        clock=build_clock(scenario),
    )
    drawable = runner.graph.get_graph()

    assert set(drawable.nodes) == {
        "__start__",
        "intake",
        "model_reasoning",
        "decision_validation",
        "tool_execution",
        "outcome_handling",
        "information_or_escalation",
        "completion",
        "safe_failure",
        "__end__",
    }
    edge_pairs = {(edge.source, edge.target) for edge in drawable.edges}
    assert ("__start__", "intake") in edge_pairs
    assert ("completion", "__end__") in edge_pairs
    assert ("safe_failure", "__end__") in edge_pairs


def test_terminal_input_fails_closed_without_calling_the_model() -> None:
    scenario = RECORDED_SCENARIOS["normal_finish"]
    payload = build_state(scenario).model_dump(mode="python")
    payload.update(
        {
            "status": RunStatus.COMPLETED,
            "final_outcome": AgentOutcome(summary="Already complete."),
        }
    )
    terminal_state = AgentRunState.model_validate(payload)
    model = RecordedDecisionModel(scenario)
    runner = RecoveryGraphRunner(
        model,
        build_dispatcher(scenario),
        actor_id="invariant-agent",
        clock=build_clock(scenario),
    )

    snapshots = tuple(runner.stream_states(terminal_state))

    assert snapshots[-1]["run_state"].failure is not None
    assert (
        snapshots[-1]["run_state"].failure.code
        is AgentFailureCode.IMPOSSIBLE_TRANSITION
    )
    assert snapshots[-1]["node_history"] == ("intake", "safe_failure")
    assert model.requests == []


def test_deadline_exhaustion_never_calls_the_model() -> None:
    result, _, model = run_graph_scenario("deadline_exhaustion")

    assert result.failure is not None
    assert result.failure.code is AgentFailureCode.DEADLINE_EXCEEDED
    assert model.requests == []

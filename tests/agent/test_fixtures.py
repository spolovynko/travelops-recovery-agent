"""Tests for deterministic recorded model fixtures."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from travelops_recovery_agent.agent.fixtures import (
    RECORDED_SCENARIOS,
    RecordedDecisionModel,
    RecordedScenario,
    RecordedTool,
    get_recorded_scenario,
)
from travelops_recovery_agent.agent.loop import AgentLoop
from travelops_recovery_agent.agent.models import (
    AgentFailureCode,
    AgentRunState,
    CallToolDecision,
    ConversationMessage,
    ConversationRole,
    RunBudget,
    RunStatus,
)
from travelops_recovery_agent.agent.tools import ReadOnlyToolDispatcher
from travelops_recovery_agent.tools.models import (
    GetBookingInput,
    GetDisruptionPolicyInput,
    GetFlightStatusInput,
    SearchAlternativeItinerariesInput,
    ValidateItineraryInput,
)
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS

STARTED_AT = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def build_dispatcher(scenario: RecordedScenario) -> ReadOnlyToolDispatcher:
    return ReadOnlyToolDispatcher(
        RecordedTool(
            name=schema.name,
            required_permission=schema.required_permission,
            fail=schema.name in scenario.failing_tools,
        )
        for schema in TOOL_SCHEMAS
    )


def run_recorded_scenario(name: str) -> tuple[AgentRunState, RecordedDecisionModel]:
    scenario = RECORDED_SCENARIOS[name]
    deadline_at = STARTED_AT + timedelta(seconds=scenario.deadline_seconds)
    state = AgentRunState(
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
            deadline_at=deadline_at,
        ),
    )
    model = RecordedDecisionModel(scenario)
    clock = (
        (lambda: deadline_at) if scenario.start_at_deadline else (lambda: STARTED_AT)
    )
    result = AgentLoop(
        model,
        build_dispatcher(scenario),
        actor_id="recorded-phase-6-agent",
        clock=clock,
    ).run(state)
    return result, model


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
def test_recorded_scenario_reaches_expected_terminal_result(
    name: str,
    expected_status: RunStatus,
    expected_failure: AgentFailureCode | None,
) -> None:
    result, _ = run_recorded_scenario(name)

    assert result.status is expected_status
    if expected_failure is None:
        assert result.failure is None
    else:
        assert result.failure is not None
        assert result.failure.code is expected_failure


def test_every_required_recorded_scenario_is_present() -> None:
    assert set(RECORDED_SCENARIOS) == {
        "successful_investigation",
        "ask_for_information",
        "normal_finish",
        "tool_failure",
        "unknown_tool",
        "repeated_tool_call",
        "malformed_recovery",
        "malformed_exhaustion",
        "maximum_turn_exhaustion",
        "deadline_exhaustion",
    }


def test_recorded_registered_tool_arguments_match_phase_4_input_models() -> None:
    input_models: dict[str, type[BaseModel]] = {
        "get_booking": GetBookingInput,
        "get_flight_status": GetFlightStatusInput,
        "get_disruption_policy": GetDisruptionPolicyInput,
        "search_alternative_itineraries": SearchAlternativeItinerariesInput,
        "validate_itinerary": ValidateItineraryInput,
    }

    for scenario in RECORDED_SCENARIOS.values():
        for step in scenario.steps:
            if isinstance(step, CallToolDecision) and step.tool_name in input_models:
                input_models[step.tool_name].model_validate(step.arguments)


def test_recorded_scenario_replay_is_byte_for_byte_deterministic() -> None:
    first, first_model = run_recorded_scenario("successful_investigation")
    second, second_model = run_recorded_scenario("successful_investigation")

    assert first.model_dump_json() == second.model_dump_json()
    assert [request.model_dump_json() for request in first_model.requests] == [
        request.model_dump_json() for request in second_model.requests
    ]


def test_deadline_fixture_never_calls_the_recorded_model() -> None:
    result, model = run_recorded_scenario("deadline_exhaustion")

    assert result.failure is not None
    assert result.failure.code is AgentFailureCode.DEADLINE_EXCEEDED
    assert model.requests == []


def test_fixture_catalogue_contains_no_credentials_or_provider_configuration() -> None:
    serialized = "".join(
        scenario.model_dump_json() for scenario in RECORDED_SCENARIOS.values()
    ).lower()

    assert "api_key" not in serialized
    assert "password" not in serialized
    assert "database_url" not in serialized
    assert "ollama" not in serialized
    assert "openai" not in serialized


def test_unknown_recorded_scenario_returns_none() -> None:
    assert get_recorded_scenario("not-recorded") is None

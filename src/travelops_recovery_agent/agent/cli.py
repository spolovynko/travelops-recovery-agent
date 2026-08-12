"""Command-line demonstration for deterministic Phase 6 agent scenarios."""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated

from pydantic import Field

from travelops_recovery_agent.agent.fixtures import (
    RECORDED_SCENARIOS,
    RecordedDecisionModel,
    RecordedModelStep,
    RecordedScenario,
    RecordedTool,
)
from travelops_recovery_agent.agent.loop import AgentLoop
from travelops_recovery_agent.agent.models import (
    AgentContractModel,
    AgentOutcome,
    AgentRunState,
    AskInformationDecision,
    ConversationMessage,
    ConversationRole,
    DecisionText,
    ReferenceText,
    RunBudget,
    RunStatus,
    SafeAgentFailure,
    ToolObservation,
)
from travelops_recovery_agent.agent.tools import ReadOnlyToolDispatcher
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS

RECORDED_STARTED_AT = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


class RecordedModelEvent(AgentContractModel):
    """One visible structured model event without hidden reasoning."""

    turn: Annotated[int, Field(ge=1, le=100)]
    step: RecordedModelStep


class RecordedRunResult(AgentContractModel):
    """Safe observable result printed by the Phase 6 demonstration."""

    scenario: ReferenceText
    description: DecisionText
    status: RunStatus
    stop_reason: ReferenceText
    turns_used: Annotated[int, Field(ge=0, le=100)]
    turn_budget: Annotated[int, Field(ge=1, le=100)]
    malformed_retries_used: Annotated[int, Field(ge=0, le=10)]
    model_events: tuple[RecordedModelEvent, ...]
    tool_observations: tuple[ToolObservation, ...]
    final_outcome: AgentOutcome | None
    information_request: AskInformationDecision | None
    failure: SafeAgentFailure | None


def build_parser() -> argparse.ArgumentParser:
    """Build the deterministic Phase 6 demonstration interface."""

    parser = argparse.ArgumentParser(
        description="Run one deterministic Phase 6 recorded agent scenario."
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        choices=tuple(RECORDED_SCENARIOS),
        default="successful_investigation",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the available deterministic scenario names.",
    )
    return parser


def run_recorded_scenario(scenario: RecordedScenario) -> RecordedRunResult:
    """Compose and execute one offline scenario through the complete loop."""

    deadline_at = RECORDED_STARTED_AT + timedelta(seconds=scenario.deadline_seconds)
    state = AgentRunState(
        run_id=f"RUN-{scenario.name}",
        case_id="CASE-0007",
        messages=(
            ConversationMessage(
                role=ConversationRole.OPERATOR,
                content="Investigate recovery case CASE-0007.",
            ),
        ),
        started_at=RECORDED_STARTED_AT,
        budget=RunBudget(
            max_model_turns=scenario.max_model_turns,
            max_malformed_retries=scenario.max_malformed_retries,
            deadline_at=deadline_at,
        ),
    )
    model = RecordedDecisionModel(scenario)
    dispatcher = ReadOnlyToolDispatcher(
        RecordedTool(
            name=schema.name,
            required_permission=schema.required_permission,
            fail=schema.name in scenario.failing_tools,
        )
        for schema in TOOL_SCHEMAS
    )
    clock = (
        (lambda: deadline_at)
        if scenario.start_at_deadline
        else (lambda: RECORDED_STARTED_AT)
    )
    terminal_state = AgentLoop(
        model,
        dispatcher,
        actor_id="recorded-phase-6-agent",
        clock=clock,
    ).run(state)

    if terminal_state.status is RunStatus.COMPLETED:
        stop_reason = "finished"
    elif terminal_state.status is RunStatus.AWAITING_INFORMATION:
        stop_reason = "information_requested"
    elif terminal_state.failure is not None:
        stop_reason = terminal_state.failure.code.value
    else:
        stop_reason = "impossible_terminal_state"

    return RecordedRunResult(
        scenario=scenario.name,
        description=scenario.description,
        status=terminal_state.status,
        stop_reason=stop_reason,
        turns_used=terminal_state.current_turn,
        turn_budget=terminal_state.budget.max_model_turns,
        malformed_retries_used=terminal_state.malformed_retry_count,
        model_events=tuple(
            RecordedModelEvent(turn=index, step=step)
            for index, step in enumerate(model.emitted_steps, start=1)
        ),
        tool_observations=terminal_state.tool_observations,
        final_outcome=terminal_state.final_outcome,
        information_request=terminal_state.information_request,
        failure=terminal_state.failure,
    )


def main(arguments: Sequence[str] | None = None) -> int:
    """Print one safe structured demonstration and return a useful exit code."""

    parsed = build_parser().parse_args(arguments)
    if parsed.list:
        print("\n".join(RECORDED_SCENARIOS))
        return 0

    scenario_name = str(parsed.scenario)
    result = run_recorded_scenario(RECORDED_SCENARIOS[scenario_name])
    print(result.model_dump_json(indent=2))
    return 0 if result.status is not RunStatus.FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Tests for the explicit transient agent run state."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.agent.models import (
    AgentFailureCode,
    AgentOutcome,
    AgentRunState,
    AskInformationDecision,
    ConversationMessage,
    ConversationRole,
    RunBudget,
    RunStatus,
    SafeAgentFailure,
    ToolObservation,
)

STARTED_AT = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def budget() -> RunBudget:
    return RunBudget(
        max_model_turns=6,
        max_malformed_retries=2,
        deadline_at=STARTED_AT + timedelta(seconds=30),
    )


def observation() -> ToolObservation:
    return ToolObservation(
        observation_id="observation-1",
        tool_name="get_booking",
        tool_call_fingerprint="fingerprint-1",
        ok=True,
        payload={"ok": True, "result": {"booking_id": "BKG-0007"}},
    )


def running_state(**changes: object) -> AgentRunState:
    values: dict[str, object] = {
        "run_id": "RUN-0001",
        "case_id": "CASE-0007",
        "started_at": STARTED_AT,
        "budget": budget(),
    }
    values.update(changes)
    return AgentRunState.model_validate(values)


def test_initial_state_contains_control_data_separate_from_messages() -> None:
    state = running_state(
        messages=(
            ConversationMessage(
                role=ConversationRole.OPERATOR,
                content="Investigate recovery case CASE-0007.",
            ),
        )
    )

    assert state.status is RunStatus.RUNNING
    assert state.current_turn == 0
    assert state.messages[0].role is ConversationRole.OPERATOR
    assert state.tool_observations == ()
    assert state.previous_tool_call_fingerprints == frozenset()
    assert state.final_outcome is None


def test_running_state_records_a_safe_tool_observation() -> None:
    state = running_state(
        current_turn=1,
        tool_observations=(observation(),),
        previous_tool_call_fingerprints=frozenset({"fingerprint-1"}),
        messages=(
            ConversationMessage(
                role=ConversationRole.TOOL,
                content="get_booking succeeded.",
                observation_id="observation-1",
            ),
        ),
    )

    assert state.tool_observations[0].payload["ok"] is True


def test_completed_state_requires_one_traceable_outcome() -> None:
    state = running_state(
        status=RunStatus.COMPLETED,
        current_turn=2,
        tool_observations=(observation(),),
        previous_tool_call_fingerprints=frozenset({"fingerprint-1"}),
        final_outcome=AgentOutcome(
            summary="The booking was retrieved.",
            evidence_ids=("observation-1",),
        ),
    )

    assert state.final_outcome is not None
    assert state.final_outcome.evidence_ids == ("observation-1",)


def test_awaiting_information_state_requires_the_operator_request() -> None:
    state = running_state(
        status=RunStatus.AWAITING_INFORMATION,
        current_turn=1,
        information_request=AskInformationDecision(
            summary="The booking identifier is missing.",
            question="What is the booking identifier?",
            missing_fields=("booking_id",),
        ),
    )

    assert state.information_request is not None
    assert state.information_request.missing_fields == ("booking_id",)


def test_failed_state_contains_only_a_safe_failure() -> None:
    state = running_state(
        status=RunStatus.FAILED,
        current_turn=1,
        failure=SafeAgentFailure(
            code=AgentFailureCode.UNKNOWN_TOOL,
            message="The requested tool is not available.",
        ),
    )

    assert state.failure is not None
    assert set(state.failure.model_dump()) == {"code", "message", "retryable"}


@pytest.mark.parametrize(
    ("status", "changes"),
    [
        (RunStatus.RUNNING, {"final_outcome": AgentOutcome(summary="Invalid.")}),
        (RunStatus.COMPLETED, {}),
        (
            RunStatus.AWAITING_INFORMATION,
            {
                "failure": SafeAgentFailure(
                    code=AgentFailureCode.MODEL_FAILURE,
                    message="Invalid.",
                )
            },
        ),
        (RunStatus.FAILED, {}),
    ],
)
def test_status_rejects_incompatible_terminal_fields(
    status: RunStatus, changes: dict[str, object]
) -> None:
    with pytest.raises(ValidationError, match="terminal fields"):
        running_state(status=status, **changes)


def test_run_rejects_turns_beyond_its_budget() -> None:
    with pytest.raises(ValidationError, match="model-turn budget"):
        running_state(current_turn=7)


def test_run_rejects_malformed_retry_count_beyond_turns_or_budget() -> None:
    with pytest.raises(ValidationError, match="cannot exceed model turns"):
        running_state(current_turn=1, malformed_retry_count=2)

    with pytest.raises(ValidationError, match="exceed their budget"):
        running_state(current_turn=3, malformed_retry_count=3)


def test_run_timestamps_must_be_timezone_aware_and_ordered() -> None:
    with pytest.raises(ValidationError, match="started_at must be timezone-aware"):
        running_state(started_at=datetime(2026, 8, 12, 12, 0))

    with pytest.raises(ValidationError, match="after started_at"):
        running_state(
            budget=RunBudget(
                max_model_turns=6,
                max_malformed_retries=2,
                deadline_at=STARTED_AT,
            )
        )


def test_observation_and_message_references_must_be_consistent() -> None:
    with pytest.raises(ValidationError, match="fingerprint must be recorded"):
        running_state(current_turn=1, tool_observations=(observation(),))

    with pytest.raises(ValidationError, match="known observations"):
        running_state(
            current_turn=1,
            messages=(
                ConversationMessage(
                    role=ConversationRole.TOOL,
                    content="Unknown observation.",
                    observation_id="observation-missing",
                ),
            ),
        )


def test_final_outcome_cannot_cite_unknown_evidence() -> None:
    with pytest.raises(ValidationError, match="unknown evidence"):
        running_state(
            status=RunStatus.COMPLETED,
            current_turn=1,
            final_outcome=AgentOutcome(
                summary="Unsupported conclusion.",
                evidence_ids=("observation-missing",),
            ),
        )


def test_tool_message_requires_an_observation_reference() -> None:
    with pytest.raises(ValidationError, match="must reference an observation"):
        ConversationMessage(
            role=ConversationRole.TOOL,
            content="A tool returned a result.",
        )


def test_state_is_immutable_and_rejects_unplanned_secret_fields() -> None:
    state = running_state()

    with pytest.raises(ValidationError, match="frozen"):
        state.current_turn = 1

    with pytest.raises(ValidationError, match="database_url"):
        running_state(database_url="postgresql://user:password@example.invalid/db")

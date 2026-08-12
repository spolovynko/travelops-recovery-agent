"""Tests for strict structured agent decisions."""

from typing import Any

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.agent.models import (
    AGENT_DECISION_ADAPTER,
    AgentOutcome,
    AskInformationDecision,
    CallToolDecision,
    FinishDecision,
    validate_agent_decision,
)


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (
            {
                "type": "call_tool",
                "summary": "Read the affected booking.",
                "tool_name": "get_booking",
                "arguments": {"booking_id": "BKG-0007"},
            },
            CallToolDecision,
        ),
        (
            {
                "type": "ask_information",
                "summary": "The booking identifier is missing.",
                "question": "What is the booking identifier?",
                "missing_fields": ["booking_id"],
            },
            AskInformationDecision,
        ),
        (
            {
                "type": "finish",
                "summary": "The read-only investigation is complete.",
                "outcome": {
                    "summary": "The booked flight is cancelled.",
                    "evidence_ids": ["observation-1"],
                    "limitations": ["Seat inventory was not evaluated."],
                },
            },
            FinishDecision,
        ),
    ],
)
def test_validate_exactly_one_supported_decision(
    payload: dict[str, Any], expected_type: type[object]
) -> None:
    decision = validate_agent_decision(payload)

    assert isinstance(decision, expected_type)


def test_decision_schema_uses_type_as_a_discriminator() -> None:
    schema = AGENT_DECISION_ADAPTER.json_schema()

    assert schema["discriminator"]["propertyName"] == "type"
    assert set(schema["discriminator"]["mapping"]) == {
        "call_tool",
        "ask_information",
        "finish",
    }
    assert len(schema["oneOf"]) == 3


def test_finish_decision_serializes_a_structured_outcome() -> None:
    decision = FinishDecision(
        summary="Investigation complete.",
        outcome=AgentOutcome(
            summary="The disruption policy allows next-day travel.",
            evidence_ids=("observation-2",),
            limitations=("No seat inventory is available in Phase 6.",),
        ),
    )

    assert decision.model_dump(mode="json") == {
        "type": "finish",
        "summary": "Investigation complete.",
        "outcome": {
            "status": "investigation_complete",
            "summary": "The disruption policy allows next-day travel.",
            "evidence_ids": ["observation-2"],
            "limitations": ["No seat inventory is available in Phase 6."],
        },
    }


def test_loose_prose_is_not_a_decision() -> None:
    with pytest.raises(ValidationError):
        validate_agent_decision("Please call get_booking for BKG-0007.")


def test_decision_cannot_mix_tool_call_and_finish_fields() -> None:
    with pytest.raises(ValidationError, match="outcome"):
        validate_agent_decision(
            {
                "type": "call_tool",
                "summary": "Read the booking and finish.",
                "tool_name": "get_booking",
                "arguments": {"booking_id": "BKG-0007"},
                "outcome": {
                    "summary": "This outcome must not be accepted.",
                },
            }
        )


def test_decision_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="hidden_reasoning"):
        validate_agent_decision(
            {
                "type": "finish",
                "summary": "Investigation complete.",
                "outcome": {"summary": "The investigation is complete."},
                "hidden_reasoning": "Do not retain this.",
            }
        )


def test_unknown_decision_type_is_rejected() -> None:
    with pytest.raises(
        ValidationError, match="does not match any of the expected tags"
    ):
        validate_agent_decision(
            {
                "type": "write_booking",
                "summary": "Attempt a write.",
            }
        )


def test_tool_arguments_must_be_json_compatible() -> None:
    with pytest.raises(ValidationError, match="arguments"):
        validate_agent_decision(
            {
                "type": "call_tool",
                "summary": "Call a tool with invalid arguments.",
                "tool_name": "get_booking",
                "arguments": {"unsafe": object()},
            }
        )


def test_missing_information_names_at_least_one_unique_field() -> None:
    with pytest.raises(ValidationError, match="missing_fields"):
        AskInformationDecision(
            summary="More information is required.",
            question="What is the booking identifier?",
            missing_fields=("booking_id", "booking_id"),
        )


def test_unknown_but_well_formed_tool_name_reaches_later_whitelist_check() -> None:
    decision = CallToolDecision(
        summary="Request an unavailable capability.",
        tool_name="delete_booking",
        arguments={"booking_id": "BKG-0007"},
    )

    assert decision.tool_name == "delete_booking"

"""Tests for deterministic repeated-tool-call fingerprints."""

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.agent.models import CallToolDecision
from travelops_recovery_agent.agent.tools import fingerprint_tool_call


def tool_call(
    *,
    summary: str = "Search for alternatives.",
    tool_name: str = "search_alternative_itineraries",
    arguments: object | None = None,
) -> CallToolDecision:
    payload = (
        {
            "origin": "BRU",
            "destination": "LHR",
            "requirements": {
                "passenger_count": 2,
                "preferences": ["direct", "morning"],
            },
        }
        if arguments is None
        else arguments
    )
    return CallToolDecision.model_validate(
        {
            "summary": summary,
            "tool_name": tool_name,
            "arguments": payload,
        }
    )


def test_identical_calls_have_the_same_fingerprint() -> None:
    first = tool_call()
    second = tool_call()

    assert fingerprint_tool_call(first) == fingerprint_tool_call(second)


def test_json_object_key_order_does_not_change_the_fingerprint() -> None:
    first = tool_call(
        arguments={
            "origin": "BRU",
            "destination": "LHR",
            "requirements": {
                "passenger_count": 2,
                "preferences": ["direct", "morning"],
            },
        }
    )
    reordered = tool_call(
        arguments={
            "requirements": {
                "preferences": ["direct", "morning"],
                "passenger_count": 2,
            },
            "destination": "LHR",
            "origin": "BRU",
        }
    )

    assert fingerprint_tool_call(first) == fingerprint_tool_call(reordered)


def test_decision_summary_does_not_change_call_identity() -> None:
    first = tool_call(summary="Search for alternatives.")
    rephrased = tool_call(summary="Find another itinerary.")

    assert fingerprint_tool_call(first) == fingerprint_tool_call(rephrased)


@pytest.mark.parametrize(
    "changed",
    [
        tool_call(arguments={"origin": "AMS", "destination": "LHR"}),
        tool_call(tool_name="validate_itinerary"),
        tool_call(
            arguments={
                "origin": "BRU",
                "destination": "LHR",
                "requirements": {
                    "passenger_count": 2,
                    "preferences": ["morning", "direct"],
                },
            }
        ),
    ],
)
def test_meaningful_call_changes_produce_a_different_fingerprint(
    changed: CallToolDecision,
) -> None:
    assert fingerprint_tool_call(tool_call()) != fingerprint_tool_call(changed)


def test_fingerprint_is_fixed_length_and_does_not_expose_arguments() -> None:
    fingerprint = fingerprint_tool_call(tool_call())

    assert fingerprint.startswith("sha256:")
    assert len(fingerprint) == 71
    assert "BRU" not in fingerprint
    assert "passenger_count" not in fingerprint


def test_fingerprinting_does_not_mutate_decision_arguments() -> None:
    decision = tool_call()
    before = decision.model_dump(mode="json")

    fingerprint_tool_call(decision)

    assert decision.model_dump(mode="json") == before


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected_before_fingerprinting(
    non_finite: float,
) -> None:
    with pytest.raises(ValidationError, match="finite number"):
        tool_call(arguments={"unsafe_number": non_finite})

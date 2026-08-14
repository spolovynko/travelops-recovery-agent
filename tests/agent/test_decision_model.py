"""Contract tests for the provider-independent model boundary."""

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.agent.decision_model import (
    DecisionModel,
    DecisionModelError,
    ModelErrorCode,
    ModelRequest,
    ModelToolDefinition,
)
from travelops_recovery_agent.agent.models import (
    AgentDecision,
    CallToolDecision,
    ConversationMessage,
    ConversationRole,
    ToolObservation,
)


def tool_definition(name: str = "get_booking") -> ModelToolDefinition:
    return ModelToolDefinition(
        name=name,
        description="Read one minimized booking.",
        input_schema={
            "type": "object",
            "properties": {"booking_id": {"type": "string"}},
            "required": ["booking_id"],
            "additionalProperties": False,
        },
    )


def model_request(**changes: object) -> ModelRequest:
    values: dict[str, object] = {
        "run_id": "RUN-0001",
        "case_id": "CASE-0007",
        "turn": 1,
        "messages": (
            ConversationMessage(
                role=ConversationRole.OPERATOR,
                content="Investigate recovery case CASE-0007.",
            ),
        ),
        "tools": (tool_definition(),),
    }
    values.update(changes)
    return ModelRequest.model_validate(values)


class ScriptedDecisionModel:
    """Minimal test double proving no provider SDK is required."""

    def __init__(self, decision: AgentDecision) -> None:
        self.decision = decision
        self.requests: list[ModelRequest] = []

    def decide(self, request: ModelRequest) -> AgentDecision:
        self.requests.append(request)
        return self.decision


def request_one_decision(model: DecisionModel, request: ModelRequest) -> AgentDecision:
    return model.decide(request)


def test_scripted_object_satisfies_model_protocol_without_an_sdk() -> None:
    scripted = ScriptedDecisionModel(
        CallToolDecision(
            summary="Read the affected booking.",
            tool_name="get_booking",
            arguments={"booking_id": "BKG-0007"},
        )
    )

    assert isinstance(scripted, DecisionModel)
    decision = request_one_decision(scripted, model_request())

    assert isinstance(decision, CallToolDecision)
    assert scripted.requests[0].case_id == "CASE-0007"


def test_model_request_contains_context_but_not_application_internals() -> None:
    request = model_request()

    assert set(request.model_dump()) == {
        "run_id",
        "case_id",
        "turn",
        "messages",
        "observations",
        "context_items",
        "tools",
    }
    serialized = request.model_dump_json()
    assert "database_url" not in serialized
    assert "repository" not in serialized
    assert "permissions" not in serialized


def test_model_request_rejects_database_or_provider_credentials() -> None:
    with pytest.raises(ValidationError, match="api_key"):
        model_request(api_key="secret-value")

    with pytest.raises(ValidationError, match="database_session"):
        model_request(database_session=object())


def test_model_request_requires_unique_tool_names() -> None:
    with pytest.raises(ValidationError, match="tool names must be unique"):
        model_request(tools=(tool_definition(), tool_definition()))


def test_tool_messages_must_reference_supplied_observations() -> None:
    tool_message = ConversationMessage(
        role=ConversationRole.TOOL,
        content="get_booking succeeded.",
        observation_id="observation-1",
    )

    with pytest.raises(ValidationError, match="supplied observations"):
        model_request(messages=(tool_message,))

    request = model_request(
        turn=2,
        messages=(tool_message,),
        observations=(
            ToolObservation(
                observation_id="observation-1",
                tool_name="get_booking",
                tool_call_fingerprint="fingerprint-1",
                ok=True,
                payload={"ok": True},
            ),
        ),
    )
    assert request.observations[0].observation_id == "observation-1"


def test_model_tool_definition_accepts_only_json_schema_data() -> None:
    with pytest.raises(ValidationError, match="input_schema"):
        ModelToolDefinition.model_validate(
            {
                "name": "get_booking",
                "description": "Read one minimized booking.",
                "input_schema": {"unsafe": object()},
            }
        )


def test_model_error_is_safe_and_provider_independent() -> None:
    error = DecisionModelError(
        ModelErrorCode.MALFORMED_OUTPUT,
        "model output did not match the decision schema",
    )

    assert error.code is ModelErrorCode.MALFORMED_OUTPUT
    assert str(error) == "model output did not match the decision schema"
    assert not hasattr(error, "raw_output")
    assert not hasattr(error, "api_key")


def test_object_without_decide_method_does_not_satisfy_protocol() -> None:
    assert not isinstance(object(), DecisionModel)

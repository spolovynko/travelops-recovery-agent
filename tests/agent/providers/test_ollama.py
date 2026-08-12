"""Offline contract tests for the local Ollama decision adapter."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import JsonValue, ValidationError

from travelops_recovery_agent.agent.loop import build_model_request
from travelops_recovery_agent.agent.model import (
    DecisionModel,
    DecisionModelError,
    ModelErrorCode,
    ModelRequest,
)
from travelops_recovery_agent.agent.models import (
    AgentRunState,
    CallToolDecision,
    ConversationMessage,
    ConversationRole,
    RunBudget,
)
from travelops_recovery_agent.agent.providers.ollama import (
    OllamaConfig,
    OllamaDecisionModel,
)
from travelops_recovery_agent.agent.tools import get_model_tool_definitions


class FakeTransport:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, JsonValue], float]] = []

    def post_json(
        self,
        url: str,
        payload: dict[str, JsonValue],
        timeout_seconds: float,
    ) -> object:
        self.calls.append((url, payload, timeout_seconds))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def request() -> ModelRequest:
    started_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    state = AgentRunState(
        run_id="RUN-0001",
        case_id="CASE-0007",
        current_turn=1,
        messages=(
            ConversationMessage(
                role=ConversationRole.OPERATOR,
                content="Investigate recovery case CASE-0007.",
            ),
        ),
        started_at=started_at,
        budget=RunBudget(
            max_model_turns=4,
            max_malformed_retries=1,
            deadline_at=started_at + timedelta(seconds=30),
        ),
    )
    return build_model_request(state)


def valid_response() -> dict[str, object]:
    return {
        "model": "qwen2.5:7b",
        "done": True,
        "message": {
            "role": "assistant",
            "content": (
                '{"type":"call_tool","summary":"Read the booking.",'
                '"tool_name":"get_booking",'
                '"arguments":{"booking_id":"BKG-0007"}}'
            ),
        },
    }


def test_adapter_satisfies_provider_independent_protocol() -> None:
    adapter = OllamaDecisionModel(
        OllamaConfig(model="test-model"),
        transport=FakeTransport(valid_response()),
    )

    assert isinstance(adapter, DecisionModel)
    assert isinstance(adapter.decide(request()), CallToolDecision)


def test_adapter_sends_schema_grounded_non_streaming_local_request() -> None:
    transport = FakeTransport(valid_response())
    adapter = OllamaDecisionModel(
        OllamaConfig(model="qwen2.5:7b", timeout_seconds=12),
        transport=transport,
    )

    decision = adapter.decide(request())
    url, payload, timeout = transport.calls[0]

    assert isinstance(decision, CallToolDecision)
    assert url == "http://127.0.0.1:11434/api/chat"
    assert timeout == 12
    assert payload["model"] == "qwen2.5:7b"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["options"] == {"temperature": 0}
    format_schema = payload["format"]
    assert isinstance(format_schema, dict)
    one_of = format_schema["oneOf"]
    assert isinstance(one_of, list)
    assert len(one_of) == 7
    definitions = format_schema["$defs"]
    assert isinstance(definitions, dict)
    booking_call = definitions["CallToolDecision_get_booking"]
    assert isinstance(booking_call, dict)
    booking_properties = booking_call["properties"]
    assert isinstance(booking_properties, dict)
    booking_arguments = booking_properties["arguments"]
    assert isinstance(booking_arguments, dict)
    assert booking_arguments["properties"] == {
        "booking_id": {
            "pattern": "^BKG-[A-Z0-9]+$",
            "title": "Booking Id",
            "type": "string",
        }
    }
    policy_call = definitions["CallToolDecision_get_disruption_policy"]
    assert isinstance(policy_call, dict)
    policy_properties = policy_call["properties"]
    assert isinstance(policy_properties, dict)
    policy_arguments = policy_properties["arguments"]
    assert isinstance(policy_arguments, dict)
    assert "$defs" not in policy_arguments
    policy_reference = policy_arguments["properties"]
    assert isinstance(policy_reference, dict)
    reference_schema = policy_reference["reference"]
    assert isinstance(reference_schema, dict)
    assert reference_schema["oneOf"] == [
        {
            "$ref": (
                "#/$defs/ToolInput_get_disruption_policy_RecoveryCasePolicyReference"
            )
        },
        {"$ref": ("#/$defs/ToolInput_get_disruption_policy_DisruptionPolicyReference")},
    ]

    messages = payload["messages"]
    assert isinstance(messages, list)
    first_message = messages[0]
    assert isinstance(first_message, dict)
    system_prompt = first_message["content"]
    assert isinstance(system_prompt, str)
    assert all(tool.name in system_prompt for tool in get_model_tool_definitions())
    assert "do not wrap it or add fields" in system_prompt
    assert "hidden reasoning" in system_prompt


@pytest.mark.parametrize(
    "base_url",
    [
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://user:password@127.0.0.1:11434",
        "http://127.0.0.1:11434/api",
        "http://127.0.0.1",
    ],
)
def test_config_rejects_nonlocal_credentialed_or_ambiguous_endpoint(
    base_url: str,
) -> None:
    with pytest.raises(ValidationError):
        OllamaConfig(base_url=base_url, model="test-model")


def test_config_requires_an_explicit_model_choice() -> None:
    with pytest.raises(ValidationError, match="model"):
        OllamaConfig.model_validate({})


def test_malformed_model_content_becomes_safe_retryable_boundary_error() -> None:
    response = valid_response()
    message = response["message"]
    assert isinstance(message, dict)
    message["content"] = "raw secret output api_key=must-not-escape"
    adapter = OllamaDecisionModel(
        OllamaConfig(model="test-model"),
        transport=FakeTransport(response),
    )

    with pytest.raises(DecisionModelError) as captured:
        adapter.decide(request())

    assert captured.value.code is ModelErrorCode.MALFORMED_OUTPUT
    assert "must-not-escape" not in str(captured.value)
    assert "api_key" not in str(captured.value)


def test_transport_failure_is_minimized_without_provider_details() -> None:
    adapter = OllamaDecisionModel(
        OllamaConfig(model="test-model"),
        transport=FakeTransport(RuntimeError("password=must-not-escape")),
    )

    with pytest.raises(DecisionModelError) as captured:
        adapter.decide(request())

    assert captured.value.code is ModelErrorCode.INVOCATION_FAILED
    assert str(captured.value) == "local model invocation failed"


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"done": False, "message": {"role": "assistant", "content": "{}"}},
        {"done": True, "message": {"role": "tool", "content": "{}"}},
    ],
)
def test_invalid_or_incomplete_provider_envelope_is_malformed_output(
    response: object,
) -> None:
    adapter = OllamaDecisionModel(
        OllamaConfig(model="test-model"),
        transport=FakeTransport(response),
    )

    with pytest.raises(DecisionModelError) as captured:
        adapter.decide(request())

    assert captured.value.code is ModelErrorCode.MALFORMED_OUTPUT


def test_payload_contains_no_credentials_or_application_internals() -> None:
    transport = FakeTransport(valid_response())
    OllamaDecisionModel(
        OllamaConfig(model="test-model"),
        transport=transport,
    ).decide(request())

    serialized = str(transport.calls[0][1]).lower()
    assert "api_key" not in serialized
    assert "password" not in serialized
    assert "database_url" not in serialized
    assert "repository" not in serialized
    assert "execution_context" not in serialized

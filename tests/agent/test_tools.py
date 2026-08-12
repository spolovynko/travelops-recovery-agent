"""Tests for safe Phase 4 tool-schema exposure to the model boundary."""

import json
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from pydantic import BaseModel, ConfigDict, JsonValue

from travelops_recovery_agent.agent.model import ModelRequest
from travelops_recovery_agent.agent.models import CallToolDecision
from travelops_recovery_agent.agent.tools import (
    ExecutableReadOnlyTool,
    ReadOnlyToolDispatcher,
    ToolDispatcherConfigurationError,
    UnknownToolError,
    get_model_tool_definitions,
    to_model_tool_definition,
)
from travelops_recovery_agent.application.query_services import (
    OperationalQueryService,
)
from travelops_recovery_agent.tools.adapters import (
    GetBookingTool,
    GetDisruptionPolicyTool,
    GetFlightStatusTool,
    SearchAlternativeItinerariesTool,
    ValidateItineraryTool,
)
from travelops_recovery_agent.tools.contracts import (
    ToolExecutionContext,
    ToolPermission,
)
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS

EXPECTED_TOOL_NAMES = [
    "get_booking",
    "get_flight_status",
    "get_disruption_policy",
    "search_alternative_itineraries",
    "validate_itinerary",
]


class StubResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_tool: str


class StubTool:
    def __init__(self, name: str, required_permission: ToolPermission) -> None:
        self.name = name
        self.required_permission = required_permission
        self.calls: list[tuple[object, ToolExecutionContext]] = []

    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> BaseModel:
        self.calls.append((input_data, context))
        return StubResult(selected_tool=self.name)


def executable_tools() -> tuple[StubTool, ...]:
    return tuple(
        StubTool(schema.name, schema.required_permission) for schema in TOOL_SCHEMAS
    )


def execution_context() -> ToolExecutionContext:
    return ToolExecutionContext(
        actor_id="phase-6-agent",
        correlation_id="RUN-0001",
        permissions=frozenset(ToolPermission),
        deadline_at=datetime.now(UTC) + timedelta(seconds=30),
    )


def test_model_receives_exactly_the_phase_4_read_only_catalogue() -> None:
    definitions = get_model_tool_definitions()

    assert [definition.name for definition in definitions] == EXPECTED_TOOL_NAMES
    assert "execute_sql" not in {definition.name for definition in definitions}
    assert "prepare_rebooking" not in {definition.name for definition in definitions}
    assert "execute_rebooking" not in {definition.name for definition in definitions}


def test_projection_reuses_phase_4_names_descriptions_and_input_schemas() -> None:
    definitions = get_model_tool_definitions()

    for source, definition in zip(TOOL_SCHEMAS, definitions, strict=True):
        assert definition.name == source.name
        assert definition.description == source.description
        assert definition.input_schema == source.input_schema
        assert definition.input_schema["additionalProperties"] is False


def test_model_definition_excludes_execution_and_application_internals() -> None:
    for definition in get_model_tool_definitions():
        assert set(definition.model_dump()) == {
            "name",
            "description",
            "input_schema",
        }
        serialized = definition.model_dump_json().lower()
        assert "required_permission" not in serialized
        assert "execution_context" not in serialized
        assert "actor_id" not in serialized
        assert "correlation_id" not in serialized
        assert "deadline_at" not in serialized
        assert "database" not in serialized
        assert "repository" not in serialized
        assert "sql" not in serialized
        assert "filesystem" not in serialized
        assert "http" not in serialized


def test_definitions_are_json_serializable_provider_neutral_data() -> None:
    payload = [
        definition.model_dump(mode="json")
        for definition in get_model_tool_definitions()
    ]

    serialized = json.dumps(payload, sort_keys=True)
    assert json.loads(serialized)[0]["name"] == "get_booking"


def test_projection_returns_detached_schema_copies() -> None:
    source = TOOL_SCHEMAS[0]
    projected = to_model_tool_definition(source)
    projected.input_schema["test_mutation"] = True

    fresh = to_model_tool_definition(source)
    assert "test_mutation" not in source.input_schema
    assert "test_mutation" not in fresh.input_schema


def test_definitions_fit_the_provider_independent_model_request() -> None:
    request = ModelRequest(
        run_id="RUN-0001",
        case_id="CASE-0007",
        turn=1,
        tools=get_model_tool_definitions(),
    )

    assert len(request.tools) == 5
    assert request.tools[-1].name == "validate_itinerary"


def test_dispatcher_invokes_only_the_decision_named_tool() -> None:
    tools = executable_tools()
    dispatcher = ReadOnlyToolDispatcher(tools)
    context = execution_context()
    arguments: dict[str, JsonValue] = {"booking_id": "BKG-0007"}

    result = dispatcher.dispatch(
        CallToolDecision(
            summary="Read the affected booking.",
            tool_name="get_booking",
            arguments=arguments,
        ),
        context,
    )

    assert result == StubResult(selected_tool="get_booking")
    assert dispatcher.tool_names == tuple(EXPECTED_TOOL_NAMES)
    assert tools[0].calls == [(arguments, context)]
    assert all(not tool.calls for tool in tools[1:])


def test_dispatcher_passes_a_detached_argument_copy() -> None:
    tools = executable_tools()
    dispatcher = ReadOnlyToolDispatcher(tools)
    arguments: dict[str, JsonValue] = {
        "reference": {"type": "recovery_case", "id": "CASE-0007"}
    }

    dispatcher.dispatch(
        CallToolDecision(
            summary="Read the disruption policy.",
            tool_name="get_disruption_policy",
            arguments=arguments,
        ),
        execution_context(),
    )

    received_arguments = tools[2].calls[0][0]
    assert received_arguments == arguments
    assert received_arguments is not arguments
    assert isinstance(received_arguments, dict)
    assert received_arguments["reference"] is not arguments["reference"]


def test_dispatcher_rejects_unknown_tool_without_guessing() -> None:
    dispatcher = ReadOnlyToolDispatcher(executable_tools())

    with pytest.raises(UnknownToolError, match="not registered"):
        dispatcher.dispatch(
            CallToolDecision(
                summary="Request an unavailable write capability.",
                tool_name="delete_booking",
                arguments={"booking_id": "BKG-0007"},
            ),
            execution_context(),
        )


def test_dispatcher_requires_complete_unique_registered_adapters() -> None:
    tools = executable_tools()

    with pytest.raises(ToolDispatcherConfigurationError, match="complete"):
        ReadOnlyToolDispatcher(tools[:-1])

    with pytest.raises(ToolDispatcherConfigurationError, match="unique"):
        ReadOnlyToolDispatcher((*tools, tools[0]))

    unknown = StubTool("execute_sql", ToolPermission.READ_BOOKING)
    with pytest.raises(ToolDispatcherConfigurationError, match="absent"):
        ReadOnlyToolDispatcher((*tools[:-1], unknown))


def test_dispatcher_requires_registry_permission_for_each_adapter() -> None:
    tools = list(executable_tools())
    tools[0] = StubTool("get_booking", ToolPermission.READ_FLIGHT_STATUS)

    with pytest.raises(ToolDispatcherConfigurationError, match="permission"):
        ReadOnlyToolDispatcher(tools)


def test_all_concrete_phase_4_adapters_implement_execution_protocol() -> None:
    service = cast(OperationalQueryService, object())
    adapters = (
        GetBookingTool(service),
        GetFlightStatusTool(service),
        GetDisruptionPolicyTool(service),
        SearchAlternativeItinerariesTool(service),
        ValidateItineraryTool(service),
    )

    assert all(isinstance(adapter, ExecutableReadOnlyTool) for adapter in adapters)

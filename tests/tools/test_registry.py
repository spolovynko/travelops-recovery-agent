"""Contract tests for stable tool discovery."""

import json

from travelops_recovery_agent.tools.contracts import ToolPermission
from travelops_recovery_agent.tools.registry import (
    TOOL_SCHEMAS,
    get_tool_schema,
)


def test_registry_exposes_every_phase_4_tool_in_stable_order() -> None:
    assert [schema.name for schema in TOOL_SCHEMAS] == [
        "get_booking",
        "get_flight_status",
        "get_disruption_policy",
        "search_alternative_itineraries",
        "validate_itinerary",
    ]
    assert [schema.required_permission for schema in TOOL_SCHEMAS] == [
        ToolPermission.READ_BOOKING,
        ToolPermission.READ_FLIGHT_STATUS,
        ToolPermission.READ_DISRUPTION_POLICY,
        ToolPermission.SEARCH_ALTERNATIVE_ITINERARIES,
        ToolPermission.VALIDATE_ITINERARY,
    ]


def test_registry_schemas_are_strict_serializable_contracts() -> None:
    for schema in TOOL_SCHEMAS:
        serialized = schema.model_dump_json()
        assert json.loads(serialized)["name"] == schema.name
        assert schema.input_schema["additionalProperties"] is False
        assert schema.execution_context_schema["additionalProperties"] is False
        assert "audit" in schema.success_schema["properties"]
        assert "error" in schema.failure_schema["properties"]


def test_registry_lookup_does_not_offer_generic_or_write_tools() -> None:
    assert get_tool_schema("get_booking") is TOOL_SCHEMAS[0]
    assert get_tool_schema("execute_sql") is None
    assert get_tool_schema("prepare_rebooking") is None
    assert get_tool_schema("execute_rebooking") is None

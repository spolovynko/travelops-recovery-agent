"""Stable discovery catalogue for read-only operational tools."""

from types import MappingProxyType
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from travelops_recovery_agent.tools.contracts import (
    ToolExecutionContext,
    ToolFailure,
    ToolPermission,
    ToolSuccess,
)
from travelops_recovery_agent.tools.models import (
    GetBookingInput,
    GetBookingOutput,
    GetDisruptionPolicyInput,
    GetDisruptionPolicyOutput,
    GetFlightStatusInput,
    GetFlightStatusOutput,
    SearchAlternativeItinerariesInput,
    SearchAlternativeItinerariesOutput,
    ValidateItineraryInput,
    ValidateItineraryOutput,
)


class ToolSchema(BaseModel):
    """Inspectable contracts and permission for one registered tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    required_permission: ToolPermission
    input_schema: dict[str, Any]
    success_schema: dict[str, Any]
    failure_schema: dict[str, Any]
    execution_context_schema: dict[str, Any]


def _schema(
    *,
    name: str,
    description: str,
    permission: ToolPermission,
    input_model: type[BaseModel],
    output_model: type[BaseModel],
) -> ToolSchema:
    """Build one immutable registry entry from Pydantic contract models."""

    return ToolSchema(
        name=name,
        description=description,
        required_permission=permission,
        input_schema=input_model.model_json_schema(),
        success_schema=cast(Any, ToolSuccess)[output_model].model_json_schema(),
        failure_schema=ToolFailure.model_json_schema(),
        execution_context_schema=ToolExecutionContext.model_json_schema(),
    )


TOOL_SCHEMAS = (
    _schema(
        name="get_booking",
        description="Read one minimized booking with passengers and ordered itinerary.",
        permission=ToolPermission.READ_BOOKING,
        input_model=GetBookingInput,
        output_model=GetBookingOutput,
    ),
    _schema(
        name="get_flight_status",
        description="Read scheduled facts and deterministic disruption-derived status.",
        permission=ToolPermission.READ_FLIGHT_STATUS,
        input_model=GetFlightStatusInput,
        output_model=GetFlightStatusOutput,
    ),
    _schema(
        name="get_disruption_policy",
        description="Resolve structured policy facts by case or disruption identifier.",
        permission=ToolPermission.READ_DISRUPTION_POLICY,
        input_model=GetDisruptionPolicyInput,
        output_model=GetDisruptionPolicyOutput,
    ),
    _schema(
        name="search_alternative_itineraries",
        description="Generate deterministic scheduled-flight candidates for a route.",
        permission=ToolPermission.SEARCH_ALTERNATIVE_ITINERARIES,
        input_model=SearchAlternativeItinerariesInput,
        output_model=SearchAlternativeItinerariesOutput,
    ),
    _schema(
        name="validate_itinerary",
        description="Validate stored flights using fixed deterministic itinerary rules.",
        permission=ToolPermission.VALIDATE_ITINERARY,
        input_model=ValidateItineraryInput,
        output_model=ValidateItineraryOutput,
    ),
)

TOOL_SCHEMAS_BY_NAME = MappingProxyType(
    {tool_schema.name: tool_schema for tool_schema in TOOL_SCHEMAS}
)


def get_tool_schema(name: str) -> ToolSchema | None:
    """Return one registered schema without exposing a mutable registry."""

    return TOOL_SCHEMAS_BY_NAME.get(name)

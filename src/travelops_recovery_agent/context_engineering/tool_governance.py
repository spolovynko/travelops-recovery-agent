"""Deny-by-default, state-aware tool schema exposure."""

from __future__ import annotations

import json
from dataclasses import dataclass

from travelops_recovery_agent.context_engineering.models import (
    ContextBuildRequest,
    ContextTask,
    GovernedTool,
    estimate_tokens,
)
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS


@dataclass(frozen=True)
class _Capability:
    name: str
    kind: str
    tasks: frozenset[ContextTask]
    workflow_nodes: frozenset[str]
    permission: str
    roles: frozenset[str] = frozenset()
    approval_required: bool = False
    input_schema: dict[str, object] | None = None


_READ_TASKS = frozenset({ContextTask.INTAKE, ContextTask.INVESTIGATE})
_TOOL_SCHEMAS = {schema.name: schema for schema in TOOL_SCHEMAS}


def _read(name: str, tasks: frozenset[ContextTask], nodes: set[str]) -> _Capability:
    schema = _TOOL_SCHEMAS[name]
    return _Capability(
        name=name,
        kind="read",
        tasks=tasks,
        workflow_nodes=frozenset(nodes),
        permission=schema.required_permission.value,
        input_schema=schema.input_schema,
    )


CAPABILITIES = (
    _read("get_booking", _READ_TASKS, {"intake", "model_reasoning"}),
    _read("get_flight_status", _READ_TASKS, {"model_reasoning"}),
    _read("get_disruption_policy", _READ_TASKS, {"model_reasoning"}),
    _read(
        "search_alternative_itineraries",
        frozenset({ContextTask.INVESTIGATE, ContextTask.RECOMMEND}),
        {"model_reasoning", "validated_recommendation"},
    ),
    _read(
        "validate_itinerary",
        frozenset({ContextTask.INVESTIGATE, ContextTask.RECOMMEND}),
        {"model_reasoning", "validated_recommendation"},
    ),
    _Capability(
        name="prepare_rebooking",
        kind="proposal",
        tasks=frozenset({ContextTask.PREPARE_PROPOSAL}),
        workflow_nodes=frozenset({"proposal_approval"}),
        permission="proposal:prepare",
        roles=frozenset({"recovery_operator", "proposal_preparer"}),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["case_id", "recommendation_reference"],
            "properties": {
                "case_id": {"type": "string"},
                "recommendation_reference": {"type": "string"},
            },
        },
    ),
    _Capability(
        name="execute_rebooking",
        kind="write",
        tasks=frozenset({ContextTask.EXECUTE_REBOOKING}),
        workflow_nodes=frozenset({"proposal_approval"}),
        permission="rebooking:execute",
        roles=frozenset({"recovery_operator"}),
        approval_required=True,
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["proposal_id", "idempotency_key"],
            "properties": {
                "proposal_id": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    ),
)


class ToolGovernancePolicy:
    """Select the minimum capability schemas and record every denial."""

    version = "phase-12.1"

    def evaluate(self, request: ContextBuildRequest) -> tuple[GovernedTool, ...]:
        governed: list[GovernedTool] = []
        for capability in CAPABILITIES:
            exposed, reason = self._decision(capability, request)
            schema = capability.input_schema if exposed else None
            estimate = (
                estimate_tokens(json.dumps(schema, sort_keys=True)) if schema else 0
            )
            governed.append(
                GovernedTool(
                    name=capability.name,
                    kind=capability.kind,  # type: ignore[arg-type]
                    exposed=exposed,
                    reason=reason,
                    token_estimate=estimate,
                    input_schema=schema,
                )
            )
        return tuple(governed)

    @staticmethod
    def _decision(
        capability: _Capability, request: ContextBuildRequest
    ) -> tuple[bool, str]:
        if request.task not in capability.tasks:
            return False, "task_not_allowed"
        if request.workflow_node not in capability.workflow_nodes:
            return False, "workflow_node_not_allowed"
        if capability.permission not in request.permissions:
            return False, "permission_missing"
        if capability.roles and request.operator_role not in capability.roles:
            return False, "role_not_allowed"
        if capability.approval_required and request.approval_status != "approved":
            return False, "approved_execution_boundary_required"
        if capability.kind == "write" and request.workflow_status not in {
            "paused",
            "running",
        }:
            return False, "workflow_state_not_executable"
        return True, "minimum_required_for_step"

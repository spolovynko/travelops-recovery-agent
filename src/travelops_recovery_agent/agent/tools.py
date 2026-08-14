"""Provider-neutral exposure of the existing Phase 4 tool catalogue."""

import json
from collections.abc import Iterable
from copy import deepcopy
from hashlib import sha256
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from travelops_recovery_agent.agent.decision_model import ModelToolDefinition
from travelops_recovery_agent.agent.models import CallToolDecision
from travelops_recovery_agent.tools.contracts import (
    ToolExecutionContext,
    ToolPermission,
)
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS, ToolSchema


def to_model_tool_definition(tool_schema: ToolSchema) -> ModelToolDefinition:
    """Project one non-executable Phase 4 schema to the narrow model boundary."""

    return ModelToolDefinition.model_validate(
        {
            "name": tool_schema.name,
            "description": tool_schema.description,
            "input_schema": deepcopy(tool_schema.input_schema),
        }
    )


def get_model_tool_definitions(
    names: frozenset[str] | None = None,
) -> tuple[ModelToolDefinition, ...]:
    """Return detached definitions for allowed registered read-only tools."""

    return tuple(
        to_model_tool_definition(schema)
        for schema in TOOL_SCHEMAS
        if names is None or schema.name in names
    )


def fingerprint_tool_call(decision: CallToolDecision) -> str:
    """Return a stable opaque fingerprint of a tool name and JSON arguments."""

    canonical_call = json.dumps(
        {
            "arguments": decision.arguments,
            "tool_name": decision.tool_name,
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sha256:{sha256(canonical_call.encode('utf-8')).hexdigest()}"


@runtime_checkable
class ExecutableReadOnlyTool(Protocol):
    """Narrow execution shape implemented by every Phase 4 adapter."""

    name: str
    required_permission: ToolPermission

    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> BaseModel:
        """Execute validated input and return a safe Phase 4 envelope."""


class ToolDispatcherConfigurationError(ValueError):
    """Raised when executable adapters do not match the safe catalogue."""


class UnknownToolError(ValueError):
    """Safe rejection of a model request for an unregistered tool."""


class ReadOnlyToolDispatcher:
    """Invoke exactly one whitelisted Phase 4 adapter by registered name."""

    def __init__(self, tools: Iterable[ExecutableReadOnlyTool]) -> None:
        registered_schemas = {schema.name: schema for schema in TOOL_SCHEMAS}
        resolved_tools: dict[str, ExecutableReadOnlyTool] = {}

        for tool in tools:
            if tool.name in resolved_tools:
                raise ToolDispatcherConfigurationError(
                    "executable tool names must be unique"
                )
            schema = registered_schemas.get(tool.name)
            if schema is None:
                raise ToolDispatcherConfigurationError(
                    "executable tool is absent from the Phase 4 registry"
                )
            if tool.required_permission is not schema.required_permission:
                raise ToolDispatcherConfigurationError(
                    "executable tool permission does not match its registry schema"
                )
            resolved_tools[tool.name] = tool

        if resolved_tools.keys() != registered_schemas.keys():
            raise ToolDispatcherConfigurationError(
                "executable tools must match the complete Phase 4 registry"
            )

        self._tools = MappingProxyType(resolved_tools)

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Return executable names in the stable Phase 4 catalogue order."""

        return tuple(schema.name for schema in TOOL_SCHEMAS)

    def required_permission_for(self, tool_name: str) -> ToolPermission:
        """Return the one permission for a registered executable tool."""

        tool = self._tools.get(tool_name)
        if tool is None:
            raise UnknownToolError("requested tool is not registered")
        return tool.required_permission

    def dispatch(
        self,
        decision: CallToolDecision,
        context: ToolExecutionContext,
    ) -> BaseModel:
        """Route one validated decision to only its named registered adapter."""

        tool = self._tools.get(decision.tool_name)
        if tool is None:
            raise UnknownToolError("requested tool is not registered")
        return tool.invoke(deepcopy(decision.arguments), context)

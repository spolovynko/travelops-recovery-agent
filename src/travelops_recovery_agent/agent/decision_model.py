"""Provider-independent boundary for requesting one structured decision."""

from enum import StrEnum
from typing import Annotated, Protocol, Self, runtime_checkable

from pydantic import Field, JsonValue, model_validator

from travelops_recovery_agent.agent.models import (
    AgentContractModel,
    AgentDecision,
    ConversationMessage,
    DecisionText,
    ReferenceText,
    ToolName,
    ToolObservation,
)


class ModelToolDefinition(AgentContractModel):
    """Minimal provider-neutral definition of one callable model tool."""

    name: ToolName
    description: DecisionText
    input_schema: dict[str, JsonValue]


class ModelContextItem(AgentContractModel):
    """Selected provider-neutral context projected from the Phase 12 builder."""

    evidence_id: ReferenceText
    source_type: ReferenceText
    authority: Annotated[int, Field(ge=0, le=4)]
    freshness: ReferenceText
    content: str = Field(min_length=1, max_length=12_000)
    compacted: bool = False


class ModelRequest(AgentContractModel):
    """Bounded provider-neutral context for one model turn."""

    run_id: ReferenceText
    case_id: ReferenceText
    turn: Annotated[int, Field(ge=1, le=100)]
    messages: Annotated[tuple[ConversationMessage, ...], Field(max_length=201)] = ()
    observations: Annotated[tuple[ToolObservation, ...], Field(max_length=100)] = ()
    context_items: Annotated[tuple[ModelContextItem, ...], Field(max_length=100)] = ()
    tools: Annotated[tuple[ModelToolDefinition, ...], Field(max_length=5)]

    @model_validator(mode="after")
    def validate_request_references(self) -> Self:
        tool_names = [tool.name for tool in self.tools]
        if len(set(tool_names)) != len(tool_names):
            raise ValueError("model tool names must be unique")

        observation_ids = {
            observation.observation_id for observation in self.observations
        }
        if len(observation_ids) != len(self.observations):
            raise ValueError("model observation identifiers must be unique")

        message_observations = {
            message.observation_id
            for message in self.messages
            if message.observation_id is not None
        }
        if not message_observations.issubset(observation_ids):
            raise ValueError("model tool messages must reference supplied observations")
        context_ids = [item.evidence_id for item in self.context_items]
        if len(context_ids) != len(set(context_ids)):
            raise ValueError("model context evidence identifiers must be unique")
        return self


class ModelErrorCode(StrEnum):
    """Safe failure categories exposed by a model adapter."""

    MALFORMED_OUTPUT = "malformed_output"
    INVOCATION_FAILED = "invocation_failed"


class DecisionModelError(Exception):
    """Safe provider-neutral error without raw output or credentials."""

    def __init__(self, code: ModelErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@runtime_checkable
class DecisionModel(Protocol):
    """A model capable of returning exactly one validated agent decision."""

    def decide(self, request: ModelRequest) -> AgentDecision:
        """Return one decision or raise a safe provider-neutral model error."""

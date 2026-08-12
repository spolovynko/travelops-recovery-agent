"""Strict models for provider-independent decisions and transient run state."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

DecisionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
ReferenceText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
ToolName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]*$",
    ),
]
RunCount = Annotated[int, Field(ge=0)]


class AgentContractModel(BaseModel):
    """Strict immutable base for agent-boundary data."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class AgentOutcome(AgentContractModel):
    """Structured conclusion produced when an investigation can finish."""

    status: Literal["investigation_complete"] = "investigation_complete"
    summary: DecisionText
    evidence_ids: tuple[ReferenceText, ...] = ()
    limitations: tuple[DecisionText, ...] = ()


class CallToolDecision(AgentContractModel):
    """Request one tool by name with JSON-compatible arguments."""

    type: Literal["call_tool"] = "call_tool"
    summary: DecisionText
    tool_name: ToolName
    arguments: dict[str, JsonValue]


class AskInformationDecision(AgentContractModel):
    """Pause the run and ask the operator for named missing information."""

    type: Literal["ask_information"] = "ask_information"
    summary: DecisionText
    question: DecisionText
    missing_fields: Annotated[
        tuple[ReferenceText, ...], Field(min_length=1, max_length=20)
    ]

    @field_validator("missing_fields")
    @classmethod
    def require_unique_missing_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("missing_fields must be unique")
        return value


class FinishDecision(AgentContractModel):
    """Finish the run with one structured investigation outcome."""

    type: Literal["finish"] = "finish"
    summary: DecisionText
    outcome: AgentOutcome


AgentDecision = Annotated[
    CallToolDecision | AskInformationDecision | FinishDecision,
    Field(discriminator="type"),
]

AGENT_DECISION_ADAPTER: TypeAdapter[AgentDecision] = TypeAdapter(AgentDecision)


def validate_agent_decision(value: object) -> AgentDecision:
    """Validate structured provider data without parsing decisions from prose."""

    return AGENT_DECISION_ADAPTER.validate_python(value)


class RunStatus(StrEnum):
    """Possible lifecycle states for one transient agent run."""

    RUNNING = "running"
    COMPLETED = "completed"
    AWAITING_INFORMATION = "awaiting_information"
    FAILED = "failed"


class ConversationRole(StrEnum):
    """Safe roles retained in the model-facing conversation view."""

    OPERATOR = "operator"
    AGENT = "agent"
    TOOL = "tool"
    APPLICATION = "application"


class AgentFailureCode(StrEnum):
    """Safe terminal failure categories owned by the agent loop."""

    BUDGET_EXHAUSTED = "budget_exhausted"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    REPEATED_TOOL_CALL = "repeated_tool_call"
    UNKNOWN_TOOL = "unknown_tool"
    MALFORMED_DECISION = "malformed_decision"
    TOOL_FAILURE = "tool_failure"
    MODEL_FAILURE = "model_failure"
    IMPOSSIBLE_TRANSITION = "impossible_transition"


class RunBudget(AgentContractModel):
    """Fixed limits that make one agent run finite."""

    max_model_turns: Annotated[int, Field(ge=1, le=100)]
    max_malformed_retries: Annotated[int, Field(ge=0, le=10)]
    deadline_at: datetime

    @field_validator("deadline_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("deadline_at must be timezone-aware")
        return value


class ConversationMessage(AgentContractModel):
    """Concise context message; it is only one view of application state."""

    role: ConversationRole
    content: DecisionText
    observation_id: ReferenceText | None = None

    @model_validator(mode="after")
    def validate_observation_reference(self) -> Self:
        if self.role is ConversationRole.TOOL and self.observation_id is None:
            raise ValueError("tool messages must reference an observation")
        if self.role is not ConversationRole.TOOL and self.observation_id is not None:
            raise ValueError("only tool messages may reference an observation")
        return self


class ToolObservation(AgentContractModel):
    """One safe structured result returned by a guarded Phase 4 tool."""

    observation_id: ReferenceText
    tool_name: ToolName
    tool_call_fingerprint: ReferenceText
    ok: bool
    payload: dict[str, JsonValue]


class SafeAgentFailure(AgentContractModel):
    """Minimized terminal failure safe to return or print."""

    code: AgentFailureCode
    message: DecisionText
    retryable: bool = False


class AgentRunState(AgentContractModel):
    """Complete in-memory control state for one bounded Phase 6 run."""

    run_id: ReferenceText
    case_id: ReferenceText
    status: RunStatus = RunStatus.RUNNING
    current_turn: RunCount = 0
    messages: Annotated[tuple[ConversationMessage, ...], Field(max_length=201)] = ()
    tool_observations: Annotated[
        tuple[ToolObservation, ...], Field(max_length=100)
    ] = ()
    previous_tool_call_fingerprints: Annotated[
        frozenset[ReferenceText], Field(max_length=100)
    ] = frozenset()
    malformed_retry_count: RunCount = 0
    started_at: datetime
    budget: RunBudget
    final_outcome: AgentOutcome | None = None
    information_request: AskInformationDecision | None = None
    failure: SafeAgentFailure | None = None

    @field_validator("started_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_run_invariants(self) -> Self:
        if self.started_at >= self.budget.deadline_at:
            raise ValueError("deadline_at must be after started_at")
        if self.current_turn > self.budget.max_model_turns:
            raise ValueError("current_turn exceeds the model-turn budget")
        if self.malformed_retry_count > self.current_turn:
            raise ValueError("malformed retries cannot exceed model turns")
        if self.malformed_retry_count > self.budget.max_malformed_retries:
            raise ValueError("malformed retries exceed their budget")
        if len(self.tool_observations) > self.current_turn:
            raise ValueError("tool observations cannot exceed model turns")

        observation_ids = [
            observation.observation_id for observation in self.tool_observations
        ]
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("tool observation identifiers must be unique")

        observation_fingerprints = {
            observation.tool_call_fingerprint for observation in self.tool_observations
        }
        if not observation_fingerprints.issubset(self.previous_tool_call_fingerprints):
            raise ValueError("each observation fingerprint must be recorded")

        known_observations = set(observation_ids)
        message_observations = {
            message.observation_id
            for message in self.messages
            if message.observation_id is not None
        }
        if not message_observations.issubset(known_observations):
            raise ValueError("tool messages must reference known observations")

        terminal_values = (
            self.final_outcome,
            self.information_request,
            self.failure,
        )
        expected_terminal_fields = {
            RunStatus.RUNNING: (False, False, False),
            RunStatus.COMPLETED: (True, False, False),
            RunStatus.AWAITING_INFORMATION: (False, True, False),
            RunStatus.FAILED: (False, False, True),
        }
        actual_terminal_fields = tuple(value is not None for value in terminal_values)
        if actual_terminal_fields != expected_terminal_fields[self.status]:
            raise ValueError("terminal fields do not match run status")

        if self.final_outcome is not None:
            evidence_ids = set(self.final_outcome.evidence_ids)
            if not evidence_ids.issubset(known_observations):
                raise ValueError("final outcome references unknown evidence")
        return self

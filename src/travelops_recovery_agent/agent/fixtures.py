"""Deterministic recorded model scenarios for tests and demonstrations."""

from datetime import timedelta
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import Field

from travelops_recovery_agent.agent.decision_model import (
    DecisionModelError,
    ModelErrorCode,
    ModelRequest,
)
from travelops_recovery_agent.agent.models import (
    AgentContractModel,
    AgentDecision,
    AgentOutcome,
    AskInformationDecision,
    CallToolDecision,
    DecisionText,
    FinishDecision,
    ReferenceText,
    ToolName,
)
from travelops_recovery_agent.tools.contracts import (
    ToolAuditMetadata,
    ToolAuditOutcome,
    ToolError,
    ToolErrorCode,
    ToolExecutionContext,
    ToolFailure,
    ToolPermission,
    ToolSuccess,
)


class RecordedModelError(AgentContractModel):
    """One safe provider-neutral error emitted at a recorded model step."""

    type: Literal["model_error"] = "model_error"
    code: ModelErrorCode
    message: DecisionText


RecordedModelStep = Annotated[
    CallToolDecision | AskInformationDecision | FinishDecision | RecordedModelError,
    Field(discriminator="type"),
]


class RecordedScenario(AgentContractModel):
    """One named deterministic model trajectory and its loop budgets."""

    name: ReferenceText
    description: DecisionText
    steps: Annotated[tuple[RecordedModelStep, ...], Field(min_length=1, max_length=100)]
    max_model_turns: Annotated[int, Field(ge=1, le=100)] = 4
    max_malformed_retries: Annotated[int, Field(ge=0, le=10)] = 1
    deadline_seconds: Annotated[int, Field(ge=1, le=300)] = 30
    failing_tools: frozenset[ToolName] = frozenset()
    start_at_deadline: bool = False


class RecordedDecisionModel:
    """Replay predefined decisions without network access or nondeterminism."""

    def __init__(self, scenario: RecordedScenario) -> None:
        self._scenario = scenario
        self._next_step = 0
        self.requests: list[ModelRequest] = []
        self._emitted_steps: list[RecordedModelStep] = []

    @property
    def emitted_steps(self) -> tuple[RecordedModelStep, ...]:
        """Return the immutable ordered trace of consumed recorded steps."""

        return tuple(self._emitted_steps)

    def decide(self, request: ModelRequest) -> AgentDecision:
        """Return the next recorded decision or raise its safe recorded error."""

        self.requests.append(request)
        if self._next_step >= len(self._scenario.steps):
            raise DecisionModelError(
                ModelErrorCode.INVOCATION_FAILED,
                "recorded model responses were exhausted",
            )
        step = self._scenario.steps[self._next_step]
        self._next_step += 1
        self._emitted_steps.append(step)
        if isinstance(step, RecordedModelError):
            raise DecisionModelError(step.code, step.message)
        return step


class RecordedToolOutput(AgentContractModel):
    """Small deterministic payload carried by a Phase 4 success envelope."""

    status: Literal["recorded_success"] = "recorded_success"


class RecordedTool:
    """Offline executable returning the existing safe Phase 4 envelopes."""

    def __init__(
        self,
        *,
        name: str,
        required_permission: ToolPermission,
        fail: bool = False,
    ) -> None:
        self.name = name
        self.required_permission = required_permission
        self._fail = fail

    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> ToolSuccess[RecordedToolOutput] | ToolFailure:
        """Return one fixed safe result without accessing any dependency."""

        del input_data
        outcome = ToolAuditOutcome.FAILED if self._fail else ToolAuditOutcome.SUCCEEDED
        recorded_at = context.deadline_at - timedelta(microseconds=1)
        audit = ToolAuditMetadata(
            tool_name=self.name,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            required_permission=self.required_permission,
            outcome=outcome,
            started_at=recorded_at,
            completed_at=recorded_at,
            duration_ms=0,
        )
        if self._fail:
            return ToolFailure(
                error=ToolError(
                    code=ToolErrorCode.DEPENDENCY_FAILURE,
                    message="recorded operational dependency failed",
                    retryable=False,
                ),
                audit=audit,
            )
        return ToolSuccess[RecordedToolOutput](
            result=RecordedToolOutput(),
            audit=audit,
        )


SUCCESSFUL_INVESTIGATION = RecordedScenario(
    name="successful_investigation",
    description="Read one booking and finish with evidence.",
    steps=(
        CallToolDecision(
            summary="Read the affected booking.",
            tool_name="get_booking",
            arguments={"booking_id": "BKG-0007"},
        ),
        FinishDecision(
            summary="The read-only investigation is complete.",
            outcome=AgentOutcome(
                summary="The booking evidence was collected.",
                evidence_ids=("observation-1",),
            ),
        ),
    ),
)

ASK_FOR_INFORMATION = RecordedScenario(
    name="ask_for_information",
    description="Ask the operator for a missing booking identifier.",
    steps=(
        AskInformationDecision(
            summary="The booking identifier is missing.",
            question="What is the booking identifier?",
            missing_fields=("booking_id",),
        ),
    ),
)

NORMAL_FINISH = RecordedScenario(
    name="normal_finish",
    description="Finish directly with a structured outcome.",
    steps=(
        FinishDecision(
            summary="No additional read is needed.",
            outcome=AgentOutcome(
                summary="The supplied facts are sufficient for this investigation.",
                limitations=("No operational tool was called.",),
            ),
        ),
    ),
)

TOOL_FAILURE = RecordedScenario(
    name="tool_failure",
    description="Request a tool that returns one safe failure.",
    steps=(
        CallToolDecision(
            summary="Read the affected booking.",
            tool_name="get_booking",
            arguments={"booking_id": "BKG-0007"},
        ),
    ),
    failing_tools=frozenset({"get_booking"}),
)

UNKNOWN_TOOL = RecordedScenario(
    name="unknown_tool",
    description="Request a capability absent from the read-only registry.",
    steps=(
        CallToolDecision(
            summary="Request an unavailable write capability.",
            tool_name="delete_booking",
            arguments={"booking_id": "BKG-0007"},
        ),
    ),
)

REPEATED_TOOL_CALL = RecordedScenario(
    name="repeated_tool_call",
    description="Repeat an identical read-only tool call.",
    steps=(
        CallToolDecision(
            summary="Read the affected booking.",
            tool_name="get_booking",
            arguments={"booking_id": "BKG-0007"},
        ),
        CallToolDecision(
            summary="Read the same booking again.",
            tool_name="get_booking",
            arguments={"booking_id": "BKG-0007"},
        ),
    ),
)

MALFORMED_RECOVERY = RecordedScenario(
    name="malformed_recovery",
    description="Recover from one malformed provider response, then finish.",
    steps=(
        RecordedModelError(
            code=ModelErrorCode.MALFORMED_OUTPUT,
            message="recorded output did not match the decision schema",
        ),
        FinishDecision(
            summary="The corrected decision is valid.",
            outcome=AgentOutcome(summary="Malformed-output recovery succeeded."),
        ),
    ),
)

MALFORMED_EXHAUSTION = RecordedScenario(
    name="malformed_exhaustion",
    description="Exhaust the fixed malformed-output retry allowance.",
    steps=(
        RecordedModelError(
            code=ModelErrorCode.MALFORMED_OUTPUT,
            message="first recorded malformed output",
        ),
        RecordedModelError(
            code=ModelErrorCode.MALFORMED_OUTPUT,
            message="second recorded malformed output",
        ),
    ),
    max_malformed_retries=1,
)

MAXIMUM_TURN_EXHAUSTION = RecordedScenario(
    name="maximum_turn_exhaustion",
    description="Use the only model turn for a successful tool call.",
    steps=(
        CallToolDecision(
            summary="Read the affected booking.",
            tool_name="get_booking",
            arguments={"booking_id": "BKG-0007"},
        ),
    ),
    max_model_turns=1,
)

DEADLINE_EXHAUSTION = RecordedScenario(
    name="deadline_exhaustion",
    description="Begin execution with the absolute deadline already reached.",
    steps=(
        FinishDecision(
            summary="This recorded decision must not be requested.",
            outcome=AgentOutcome(summary="The deadline prevents this outcome."),
        ),
    ),
    start_at_deadline=True,
)

RECORDED_SCENARIOS = MappingProxyType(
    {
        scenario.name: scenario
        for scenario in (
            SUCCESSFUL_INVESTIGATION,
            ASK_FOR_INFORMATION,
            NORMAL_FINISH,
            TOOL_FAILURE,
            UNKNOWN_TOOL,
            REPEATED_TOOL_CALL,
            MALFORMED_RECOVERY,
            MALFORMED_EXHAUSTION,
            MAXIMUM_TURN_EXHAUSTION,
            DEADLINE_EXHAUSTION,
        )
    }
)


def get_recorded_scenario(name: str) -> RecordedScenario | None:
    """Return one immutable scenario by stable name."""

    return RECORDED_SCENARIOS.get(name)

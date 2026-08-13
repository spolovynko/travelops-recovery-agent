"""Transition tests for the explicit bounded Phase 6 agent loop."""

from datetime import UTC, datetime, timedelta
from typing import cast

from pydantic import BaseModel, ConfigDict

from travelops_recovery_agent.agent.decision_model import (
    DecisionModelError,
    ModelErrorCode,
    ModelRequest,
)
from travelops_recovery_agent.agent.loop import AgentLoop
from travelops_recovery_agent.agent.model_request import build_model_request
from travelops_recovery_agent.agent.models import (
    AgentDecision,
    AgentFailureCode,
    AgentOutcome,
    AgentRunState,
    AskInformationDecision,
    CallToolDecision,
    ConversationMessage,
    ConversationRole,
    FinishDecision,
    RunBudget,
    RunStatus,
)
from travelops_recovery_agent.agent.tools import ReadOnlyToolDispatcher
from travelops_recovery_agent.tools.contracts import (
    ToolExecutionContext,
    ToolPermission,
)
from travelops_recovery_agent.tools.registry import TOOL_SCHEMAS

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


class ScriptedModel:
    def __init__(self, decisions: tuple[AgentDecision, ...]) -> None:
        self._decisions = decisions
        self.requests: list[ModelRequest] = []

    def decide(self, request: ModelRequest) -> AgentDecision:
        self.requests.append(request)
        return self._decisions[len(self.requests) - 1]


class SuccessfulToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool = True
    result: dict[str, str]


class SuccessfulStubTool:
    def __init__(self, name: str, permission: ToolPermission) -> None:
        self.name = name
        self.required_permission = permission
        self.contexts: list[ToolExecutionContext] = []

    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> BaseModel:
        self.contexts.append(context)
        return SuccessfulToolResult(
            result={"tool": self.name, "input_type": type(input_data).__name__}
        )


class SafeFailureToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool = False
    error: dict[str, str]


class SafeFailureStubTool(SuccessfulStubTool):
    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> BaseModel:
        self.contexts.append(context)
        return SafeFailureToolResult(
            error={"code": "dependency_failure", "message": "safe failure"}
        )


class ExplodingStubTool(SuccessfulStubTool):
    def invoke(
        self,
        input_data: object,
        context: ToolExecutionContext,
    ) -> BaseModel:
        self.contexts.append(context)
        raise RuntimeError("password=must-not-escape")


class UntrustedScriptedModel:
    def __init__(self, responses: tuple[object, ...]) -> None:
        self._responses = responses
        self.requests: list[ModelRequest] = []

    def decide(self, request: ModelRequest) -> AgentDecision:
        self.requests.append(request)
        response = self._responses[len(self.requests) - 1]
        if isinstance(response, Exception):
            raise response
        return cast(AgentDecision, response)


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self._values = values
        self._index = 0

    def __call__(self) -> datetime:
        value = self._values[min(self._index, len(self._values) - 1)]
        self._index += 1
        return value


def dispatcher() -> tuple[ReadOnlyToolDispatcher, tuple[SuccessfulStubTool, ...]]:
    tools = tuple(
        SuccessfulStubTool(schema.name, schema.required_permission)
        for schema in TOOL_SCHEMAS
    )
    return ReadOnlyToolDispatcher(tools), tools


def dispatcher_with_booking_tool(
    booking_tool: SuccessfulStubTool,
) -> ReadOnlyToolDispatcher:
    tools: list[SuccessfulStubTool] = [booking_tool]
    tools.extend(
        SuccessfulStubTool(schema.name, schema.required_permission)
        for schema in TOOL_SCHEMAS[1:]
    )
    return ReadOnlyToolDispatcher(tools)


def initial_state(*, max_turns: int = 4) -> AgentRunState:
    return AgentRunState(
        run_id="RUN-0001",
        case_id="CASE-0007",
        messages=(
            ConversationMessage(
                role=ConversationRole.OPERATOR,
                content="Investigate recovery case CASE-0007.",
            ),
        ),
        started_at=NOW,
        budget=RunBudget(
            max_model_turns=max_turns,
            max_malformed_retries=1,
            deadline_at=NOW + timedelta(seconds=30),
        ),
    )


def test_build_model_request_uses_typed_state_and_safe_catalogue() -> None:
    state = initial_state().model_copy(update={"current_turn": 1})

    request = build_model_request(state)

    assert request.run_id == state.run_id
    assert request.case_id == state.case_id
    assert request.turn == 1
    assert request.messages == state.messages
    assert [tool.name for tool in request.tools] == [
        schema.name for schema in TOOL_SCHEMAS
    ]


def test_loop_executes_one_tool_then_finishes_with_recorded_evidence() -> None:
    model = ScriptedModel(
        (
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
        )
    )
    tool_dispatcher, tools = dispatcher()

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert result.status is RunStatus.COMPLETED
    assert result.current_turn == 2
    assert result.final_outcome is not None
    assert result.final_outcome.evidence_ids == ("observation-1",)
    assert len(result.tool_observations) == 1
    assert result.tool_observations[0].ok is True
    assert len(model.requests) == 2
    assert model.requests[1].observations == result.tool_observations
    assert tools[0].contexts[0].permissions == frozenset({ToolPermission.READ_BOOKING})
    assert all(not tool.contexts for tool in tools[1:])


def test_loop_asks_operator_without_executing_a_tool() -> None:
    model = ScriptedModel(
        (
            AskInformationDecision(
                summary="The booking identifier is missing.",
                question="What is the booking identifier?",
                missing_fields=("booking_id",),
            ),
        )
    )
    tool_dispatcher, tools = dispatcher()

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert result.status is RunStatus.AWAITING_INFORMATION
    assert result.current_turn == 1
    assert result.information_request is not None
    assert result.information_request.missing_fields == ("booking_id",)
    assert all(not tool.contexts for tool in tools)


def test_loop_can_finish_directly_with_a_structured_outcome() -> None:
    model = ScriptedModel(
        (
            FinishDecision(
                summary="No additional read is needed.",
                outcome=AgentOutcome(
                    summary="The supplied facts are sufficient for this investigation.",
                    limitations=("No operational tool was called.",),
                ),
            ),
        )
    )
    tool_dispatcher, _ = dispatcher()

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert result.status is RunStatus.COMPLETED
    assert result.current_turn == 1
    assert result.final_outcome is not None
    assert result.final_outcome.limitations == ("No operational tool was called.",)
    assert result.tool_observations == ()


def test_loop_reaches_turn_budget_without_an_unbounded_iteration() -> None:
    model = ScriptedModel(
        (
            CallToolDecision(
                summary="Read the booking.",
                tool_name="get_booking",
                arguments={"booking_id": "BKG-0007"},
            ),
        )
    )
    tool_dispatcher, _ = dispatcher()

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state(max_turns=1))

    assert result.status is RunStatus.FAILED
    assert result.current_turn == 1
    assert result.failure is not None
    assert result.failure.code.value == "budget_exhausted"


def test_loop_stops_before_model_call_when_deadline_is_exhausted() -> None:
    model = ScriptedModel(
        (
            FinishDecision(
                summary="This decision must not be requested.",
                outcome=AgentOutcome(summary="Too late."),
            ),
        )
    )
    tool_dispatcher, _ = dispatcher()
    state = initial_state()

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: state.budget.deadline_at,
    ).run(state)

    assert result.status is RunStatus.FAILED
    assert result.current_turn == 0
    assert result.failure is not None
    assert result.failure.code is AgentFailureCode.DEADLINE_EXCEEDED
    assert model.requests == []


def test_loop_rechecks_deadline_after_model_call() -> None:
    model = ScriptedModel(
        (
            FinishDecision(
                summary="The model returned after the deadline.",
                outcome=AgentOutcome(summary="Too late."),
            ),
        )
    )
    tool_dispatcher, _ = dispatcher()
    state = initial_state()
    clock = SequenceClock(NOW, state.budget.deadline_at)

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=clock,
    ).run(state)

    assert result.status is RunStatus.FAILED
    assert result.current_turn == 1
    assert result.failure is not None
    assert result.failure.code is AgentFailureCode.DEADLINE_EXCEEDED


def test_loop_records_tool_result_then_stops_if_tool_returns_at_deadline() -> None:
    model = ScriptedModel(
        (
            CallToolDecision(
                summary="Read the affected booking.",
                tool_name="get_booking",
                arguments={"booking_id": "BKG-0007"},
            ),
        )
    )
    tool_dispatcher, tools = dispatcher()
    state = initial_state()
    clock = SequenceClock(
        NOW,
        NOW,
        NOW,
        state.budget.deadline_at,
    )

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=clock,
    ).run(state)

    assert result.status is RunStatus.FAILED
    assert result.failure is not None
    assert result.failure.code is AgentFailureCode.DEADLINE_EXCEEDED
    assert len(tools[0].contexts) == 1
    assert len(result.tool_observations) == 1


def test_loop_stops_repeated_identical_tool_call_before_second_execution() -> None:
    repeated = CallToolDecision(
        summary="Read the affected booking.",
        tool_name="get_booking",
        arguments={"booking_id": "BKG-0007"},
    )
    model = ScriptedModel((repeated, repeated))
    tool_dispatcher, tools = dispatcher()

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert result.status is RunStatus.FAILED
    assert result.failure is not None
    assert result.failure.code is AgentFailureCode.REPEATED_TOOL_CALL
    assert len(tools[0].contexts) == 1
    assert len(result.tool_observations) == 1


def test_loop_rejects_unknown_tool_without_executing_any_adapter() -> None:
    model = ScriptedModel(
        (
            CallToolDecision(
                summary="Request a write capability.",
                tool_name="delete_booking",
                arguments={"booking_id": "BKG-0007"},
            ),
        )
    )
    tool_dispatcher, tools = dispatcher()

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert result.status is RunStatus.FAILED
    assert result.failure is not None
    assert result.failure.code is AgentFailureCode.UNKNOWN_TOOL
    assert all(not tool.contexts for tool in tools)


def test_malformed_model_output_recovers_within_fixed_retry_limit() -> None:
    model = UntrustedScriptedModel(
        (
            "this is not a structured decision",
            FinishDecision(
                summary="The corrected decision is valid.",
                outcome=AgentOutcome(summary="Recovery succeeded."),
            ),
        )
    )
    tool_dispatcher, _ = dispatcher()

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert result.status is RunStatus.COMPLETED
    assert result.current_turn == 2
    assert result.malformed_retry_count == 1
    assert model.requests[1].messages[-1].role is ConversationRole.APPLICATION
    assert "required decision schema" in model.requests[1].messages[-1].content


def test_provider_reported_malformed_output_uses_same_recovery_path() -> None:
    model = UntrustedScriptedModel(
        (
            DecisionModelError(
                ModelErrorCode.MALFORMED_OUTPUT,
                "raw provider response must not escape",
            ),
            AskInformationDecision(
                summary="A booking identifier is required.",
                question="What is the booking identifier?",
                missing_fields=("booking_id",),
            ),
        )
    )
    tool_dispatcher, _ = dispatcher()

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert result.status is RunStatus.AWAITING_INFORMATION
    assert result.malformed_retry_count == 1
    assert "raw provider response" not in result.model_dump_json()


def test_malformed_output_stops_after_retry_limit() -> None:
    model = UntrustedScriptedModel(("bad output one", "bad output two"))
    tool_dispatcher, _ = dispatcher()

    result = AgentLoop(
        model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert result.status is RunStatus.FAILED
    assert result.current_turn == 2
    assert result.malformed_retry_count == 1
    assert result.failure is not None
    assert result.failure.code is AgentFailureCode.MALFORMED_DECISION
    assert "bad output" not in result.model_dump_json()


def test_safe_tool_failure_is_recorded_once_and_not_retried() -> None:
    model = ScriptedModel(
        (
            CallToolDecision(
                summary="Read the affected booking.",
                tool_name="get_booking",
                arguments={"booking_id": "BKG-0007"},
            ),
        )
    )
    booking_tool = SafeFailureStubTool("get_booking", ToolPermission.READ_BOOKING)

    result = AgentLoop(
        model,
        dispatcher_with_booking_tool(booking_tool),
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert result.status is RunStatus.FAILED
    assert result.failure is not None
    assert result.failure.code is AgentFailureCode.TOOL_FAILURE
    assert len(booking_tool.contexts) == 1
    assert len(result.tool_observations) == 1
    assert result.tool_observations[0].ok is False


def test_unexpected_model_and_tool_exceptions_are_minimized() -> None:
    tool_dispatcher, _ = dispatcher()
    model_result = AgentLoop(
        UntrustedScriptedModel((RuntimeError("api_key=must-not-escape"),)),
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    exploding_tool = ExplodingStubTool("get_booking", ToolPermission.READ_BOOKING)
    tool_result = AgentLoop(
        ScriptedModel(
            (
                CallToolDecision(
                    summary="Read the booking.",
                    tool_name="get_booking",
                    arguments={"booking_id": "BKG-0007"},
                ),
            )
        ),
        dispatcher_with_booking_tool(exploding_tool),
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert model_result.failure is not None
    assert model_result.failure.code is AgentFailureCode.MODEL_FAILURE
    assert tool_result.failure is not None
    assert tool_result.failure.code is AgentFailureCode.TOOL_FAILURE
    serialized = model_result.model_dump_json() + tool_result.model_dump_json()
    assert "must-not-escape" not in serialized
    assert "api_key" not in serialized
    assert "password" not in serialized


def test_terminal_input_and_unknown_evidence_fail_as_impossible_transitions() -> None:
    terminal_payload = initial_state().model_dump(mode="python")
    terminal_payload.update(
        {
            "status": RunStatus.COMPLETED,
            "final_outcome": AgentOutcome(summary="Already complete."),
        }
    )
    terminal_state = AgentRunState.model_validate(terminal_payload)
    empty_model = ScriptedModel(())
    tool_dispatcher, _ = dispatcher()

    terminal_result = AgentLoop(
        empty_model,
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(terminal_state)
    evidence_result = AgentLoop(
        ScriptedModel(
            (
                FinishDecision(
                    summary="Cite unavailable evidence.",
                    outcome=AgentOutcome(
                        summary="Unsupported outcome.",
                        evidence_ids=("observation-missing",),
                    ),
                ),
            )
        ),
        tool_dispatcher,
        actor_id="phase-6-agent",
        clock=lambda: NOW,
    ).run(initial_state())

    assert terminal_result.failure is not None
    assert terminal_result.failure.code is AgentFailureCode.IMPOSSIBLE_TRANSITION
    assert empty_model.requests == []
    assert evidence_result.failure is not None
    assert evidence_result.failure.code is AgentFailureCode.IMPOSSIBLE_TRANSITION

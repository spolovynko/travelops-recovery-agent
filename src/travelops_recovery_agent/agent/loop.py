"""Explicit bounded Python loop for one read-only agent investigation."""

from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from travelops_recovery_agent.agent.decision_model import (
    DecisionModel,
    DecisionModelError,
    ModelErrorCode,
)
from travelops_recovery_agent.agent.model_request import build_model_request
from travelops_recovery_agent.agent.models import (
    AgentDecision,
    AgentFailureCode,
    AgentRunState,
    AskInformationDecision,
    CallToolDecision,
    ConversationMessage,
    ConversationRole,
    FinishDecision,
    RunStatus,
    SafeAgentFailure,
    ToolObservation,
    validate_agent_decision,
)
from travelops_recovery_agent.agent.tools import (
    ReadOnlyToolDispatcher,
    UnknownToolError,
    fingerprint_tool_call,
)
from travelops_recovery_agent.tools.contracts import ToolExecutionContext


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(UTC)


def _replace_state(state: AgentRunState, **updates: object) -> AgentRunState:
    """Rebuild state so every transition reruns all Pydantic invariants."""

    payload = state.model_dump(mode="python")
    payload.update(updates)
    return AgentRunState.model_validate(payload)


class AgentLoop:
    """Coordinate one model decision and at most one tool call per turn."""

    def __init__(
        self,
        model: DecisionModel,
        dispatcher: ReadOnlyToolDispatcher,
        *,
        actor_id: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._model = model
        self._dispatcher = dispatcher
        self._actor_id = actor_id
        self._clock = clock

    def run(self, initial_state: AgentRunState) -> AgentRunState:
        """Run explicit bounded transitions until one terminal state is reached."""

        state = initial_state
        if state.status is not RunStatus.RUNNING:
            return self._fail(
                state,
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "an agent run must start in the running state",
            )

        first_turn = state.current_turn + 1
        for turn in range(first_turn, state.budget.max_model_turns + 1):
            if self._deadline_reached(state):
                return self._fail(
                    state,
                    AgentFailureCode.DEADLINE_EXCEEDED,
                    "the agent run deadline was reached",
                )

            state = _replace_state(state, current_turn=turn)
            request = build_model_request(state)
            try:
                raw_decision = self._model.decide(request)
            except DecisionModelError as error:
                if self._deadline_reached(state):
                    return self._fail(
                        state,
                        AgentFailureCode.DEADLINE_EXCEEDED,
                        "the agent run deadline was reached",
                    )
                if error.code is ModelErrorCode.MALFORMED_OUTPUT:
                    state = self._recover_malformed_decision(state)
                    if state.status is RunStatus.RUNNING:
                        continue
                    return state
                return self._fail(
                    state,
                    AgentFailureCode.MODEL_FAILURE,
                    "the model could not produce a decision",
                )
            except Exception:
                if self._deadline_reached(state):
                    return self._fail(
                        state,
                        AgentFailureCode.DEADLINE_EXCEEDED,
                        "the agent run deadline was reached",
                    )
                return self._fail(
                    state,
                    AgentFailureCode.MODEL_FAILURE,
                    "the model could not produce a decision",
                )

            try:
                decision = validate_agent_decision(raw_decision)
            except ValidationError:
                state = self._recover_malformed_decision(state)
                if state.status is RunStatus.RUNNING:
                    continue
                return state

            if self._deadline_reached(state):
                return self._fail(
                    state,
                    AgentFailureCode.DEADLINE_EXCEEDED,
                    "the agent run deadline was reached",
                )

            try:
                state = self._record_decision_summary(state, decision)
            except ValidationError:
                return self._fail(
                    state,
                    AgentFailureCode.IMPOSSIBLE_TRANSITION,
                    "the decision could not be recorded in the run state",
                )
            decision_object: object = decision
            if isinstance(decision_object, CallToolDecision):
                state = self._execute_tool(state, decision_object)
                if state.status is not RunStatus.RUNNING:
                    return state
                continue
            if isinstance(decision_object, AskInformationDecision):
                return _replace_state(
                    state,
                    status=RunStatus.AWAITING_INFORMATION,
                    information_request=decision_object,
                )
            if isinstance(decision_object, FinishDecision):
                try:
                    return _replace_state(
                        state,
                        status=RunStatus.COMPLETED,
                        final_outcome=decision_object.outcome,
                    )
                except ValidationError:
                    return self._fail(
                        state,
                        AgentFailureCode.IMPOSSIBLE_TRANSITION,
                        "the final outcome referenced unavailable evidence",
                    )
            return self._fail(
                state,
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "the model returned an unsupported decision",
            )

        return self._fail(
            state,
            AgentFailureCode.BUDGET_EXHAUSTED,
            "the model-turn budget was exhausted",
        )

    def _execute_tool(
        self,
        state: AgentRunState,
        decision: CallToolDecision,
    ) -> AgentRunState:
        fingerprint = fingerprint_tool_call(decision)
        if fingerprint in state.previous_tool_call_fingerprints:
            return self._fail(
                state,
                AgentFailureCode.REPEATED_TOOL_CALL,
                "an identical tool call was already attempted",
            )
        if self._deadline_reached(state):
            return self._fail(
                state,
                AgentFailureCode.DEADLINE_EXCEEDED,
                "the agent run deadline was reached",
            )

        try:
            required_permission = self._dispatcher.required_permission_for(
                decision.tool_name
            )
        except UnknownToolError:
            return self._fail(
                state,
                AgentFailureCode.UNKNOWN_TOOL,
                "the requested tool is not available",
            )

        try:
            state = _replace_state(
                state,
                previous_tool_call_fingerprints=(
                    state.previous_tool_call_fingerprints | {fingerprint}
                ),
            )
        except ValidationError:
            return self._fail(
                state,
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "the tool attempt could not be recorded in the run state",
            )
        try:
            context = ToolExecutionContext(
                actor_id=self._actor_id,
                correlation_id=state.run_id,
                permissions=frozenset({required_permission}),
                deadline_at=state.budget.deadline_at,
            )
            result = self._dispatcher.dispatch(decision, context)
            result_payload = result.model_dump(mode="json")
            succeeded = result_payload.get("ok") is True
            observation = ToolObservation.model_validate(
                {
                    "observation_id": (
                        f"observation-{len(state.tool_observations) + 1}"
                    ),
                    "tool_name": decision.tool_name,
                    "tool_call_fingerprint": fingerprint,
                    "ok": succeeded,
                    "payload": result_payload,
                }
            )
        except Exception:
            return self._fail(
                state,
                AgentFailureCode.TOOL_FAILURE,
                "a read-only tool could not return a safe result",
            )
        try:
            state = _replace_state(
                state,
                tool_observations=(*state.tool_observations, observation),
                messages=(
                    *state.messages,
                    ConversationMessage(
                        role=ConversationRole.TOOL,
                        content=(
                            f"{decision.tool_name} returned a safe "
                            f"{'success' if succeeded else 'failure'} result."
                        ),
                        observation_id=observation.observation_id,
                    ),
                ),
            )
        except ValidationError:
            return self._fail(
                state,
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "the tool observation could not be recorded in the run state",
            )
        if self._deadline_reached(state):
            return self._fail(
                state,
                AgentFailureCode.DEADLINE_EXCEEDED,
                "the agent run deadline was reached",
            )
        if not succeeded:
            return self._fail(
                state,
                AgentFailureCode.TOOL_FAILURE,
                "a read-only tool returned a safe failure",
            )
        return state

    def _recover_malformed_decision(self, state: AgentRunState) -> AgentRunState:
        if state.malformed_retry_count >= state.budget.max_malformed_retries:
            return self._fail(
                state,
                AgentFailureCode.MALFORMED_DECISION,
                "model output did not match the decision schema",
            )
        try:
            return _replace_state(
                state,
                malformed_retry_count=state.malformed_retry_count + 1,
                messages=(
                    *state.messages,
                    ConversationMessage(
                        role=ConversationRole.APPLICATION,
                        content=(
                            "The previous model output did not match the required "
                            "decision schema. Return exactly one structured decision."
                        ),
                    ),
                ),
            )
        except ValidationError:
            return self._fail(
                state,
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "malformed-output recovery could not update the run state",
            )

    def _record_decision_summary(
        self,
        state: AgentRunState,
        decision: AgentDecision,
    ) -> AgentRunState:
        return _replace_state(
            state,
            messages=(
                *state.messages,
                ConversationMessage(
                    role=ConversationRole.AGENT,
                    content=decision.summary,
                ),
            ),
        )

    def _deadline_reached(self, state: AgentRunState) -> bool:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            return True
        return now >= state.budget.deadline_at

    @staticmethod
    def _fail(
        state: AgentRunState,
        code: AgentFailureCode,
        message: str,
    ) -> AgentRunState:
        return _replace_state(
            state,
            status=RunStatus.FAILED,
            final_outcome=None,
            information_request=None,
            failure=SafeAgentFailure(code=code, message=message),
        )

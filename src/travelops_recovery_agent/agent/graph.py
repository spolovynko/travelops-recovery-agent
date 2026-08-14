"""Explicit LangGraph orchestration for one read-only recovery investigation."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
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
from travelops_recovery_agent.application.proposal_models import (
    ProposalStatus,
    ProposalWithAudit,
)
from travelops_recovery_agent.application.recommendation_models import (
    RecommendationOutcome,
    RecommendationResult,
)
from travelops_recovery_agent.tools.contracts import ToolExecutionContext

GraphNode = Literal[
    "validated_recommendation",
    "proposal_approval",
    "intake",
    "model_reasoning",
    "decision_validation",
    "tool_execution",
    "outcome_handling",
    "information_or_escalation",
    "completion",
    "safe_failure",
]
GraphRoute = Literal[
    "validated_recommendation",
    "proposal_approval",
    "model_reasoning",
    "decision_validation",
    "tool_execution",
    "outcome_handling",
    "information_or_escalation",
    "completion",
    "safe_failure",
    "end",
]


class RecommendationProvider(Protocol):
    """Application-owned deterministic recommendation boundary."""

    def recommend(self, case_id: str) -> RecommendationResult: ...


class ProposalProvider(Protocol):
    def create_or_get(
        self,
        case_id: str,
        *,
        actor_id: str,
        correlation_id: str,
        workflow_run_id: str | None = None,
    ) -> ProposalWithAudit: ...

    def get(self, proposal_id: str) -> ProposalWithAudit: ...

    def execute(
        self,
        proposal_id: str,
        *,
        idempotency_key: str,
        actor_id: str,
        actor_role: str,
        correlation_id: str,
    ) -> ProposalWithAudit: ...


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(UTC)


@dataclass(frozen=True)
class AgentGraphContext:
    """Executable services available to nodes but excluded from graph state."""

    model: DecisionModel
    dispatcher: ReadOnlyToolDispatcher
    actor_id: str
    clock: Callable[[], datetime] = utc_now
    recommendation_provider: RecommendationProvider | None = None
    proposal_provider: ProposalProvider | None = None
    proposal_workflow_enabled: bool = False


def append_node_history(
    current: tuple[GraphNode, ...] | list[GraphNode],
    update: tuple[GraphNode, ...] | list[GraphNode],
) -> tuple[GraphNode, ...]:
    """Append history while normalizing JSON-decoded sequences to tuples."""

    return (*current, *update)


class AgentGraphState(TypedDict):
    """Typed, transient and inspectable state shared by all graph nodes."""

    run_state: AgentRunState
    node_history: Annotated[tuple[GraphNode, ...], append_node_history]
    route: GraphRoute
    pending_decision: AgentDecision | None
    model_error_code: ModelErrorCode | None
    pending_failure: SafeAgentFailure | None


class AgentGraphUpdate(TypedDict, total=False):
    """Partial state update emitted by one graph node."""

    run_state: AgentRunState
    node_history: tuple[GraphNode, ...]
    route: GraphRoute
    pending_decision: AgentDecision | None
    model_error_code: ModelErrorCode | None
    pending_failure: SafeAgentFailure | None


def create_graph_state(run_state: AgentRunState) -> AgentGraphState:
    """Place a Phase 6 run state into fresh transient graph state."""

    return {
        "run_state": run_state,
        "node_history": (),
        "route": "model_reasoning",
        "pending_decision": None,
        "model_error_code": None,
        "pending_failure": None,
    }


def _replace_run_state(state: AgentRunState, **updates: object) -> AgentRunState:
    """Rebuild trusted run state so every transition reruns its invariants."""

    payload = state.model_dump(mode="python")
    payload.update(updates)
    return AgentRunState.model_validate(payload)


def _pending_failure(
    code: AgentFailureCode,
    message: str,
) -> AgentGraphUpdate:
    """Create a minimized failure update routed through the safe-failure node."""

    return {
        "route": "safe_failure",
        "pending_decision": None,
        "model_error_code": None,
        "pending_failure": SafeAgentFailure(code=code, message=message),
    }


def _deadline_reached(
    run_state: AgentRunState,
    runtime: Runtime[AgentGraphContext],
) -> bool:
    """Fail closed for expired deadlines or invalid clock values."""

    now = runtime.context.clock()
    if now.tzinfo is None or now.utcoffset() is None:
        return True
    return now >= run_state.budget.deadline_at


def intake(state: AgentGraphState) -> AgentGraphUpdate:
    """Accept only a running Phase 6 state into a fresh graph execution."""

    update: AgentGraphUpdate = {"node_history": ("intake",)}
    if state["run_state"].status is not RunStatus.RUNNING:
        update.update(
            _pending_failure(
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "an agent run must start in the running state",
            )
        )
        return update
    update["route"] = "model_reasoning"
    return update


def validated_recommendation(
    state: AgentGraphState,
    runtime: Runtime[AgentGraphContext],
) -> AgentGraphUpdate:
    """Compute a recommendation whose validity is owned entirely by application code."""

    update: AgentGraphUpdate = {"node_history": ("validated_recommendation",)}
    route: GraphRoute
    provider = runtime.context.recommendation_provider
    if provider is None:
        update.update(
            _pending_failure(
                AgentFailureCode.RECOMMENDATION_FAILURE,
                "the deterministic recommendation service is not configured",
            )
        )
        return update
    try:
        result = provider.recommend(state["run_state"].case_id)
        if result.outcome is RecommendationOutcome.RECOMMENDED:
            summary = "A recovery itinerary passed every deterministic validation rule."
        elif result.outcome is RecommendationOutcome.INSUFFICIENT_EVIDENCE:
            summary = "Recommendation evidence is incomplete; operator escalation is required."
        else:
            summary = (
                "No safe recovery itinerary exists; operator escalation is required."
            )
        if (
            runtime.context.proposal_provider is None
            or not runtime.context.proposal_workflow_enabled
            or result.outcome is not RecommendationOutcome.RECOMMENDED
        ):
            run_state = _replace_run_state(
                state["run_state"],
                status=RunStatus.COMPLETED,
                final_outcome={"summary": summary},
                recommendation=result,
            )
            route = "completion"
        else:
            run_state = _replace_run_state(state["run_state"], recommendation=result)
            route = "proposal_approval"
    except Exception:
        update.update(
            _pending_failure(
                AgentFailureCode.RECOMMENDATION_FAILURE,
                "the deterministic recommendation could not be completed safely",
            )
        )
        return update
    update.update({"run_state": run_state, "route": route})
    return update


def proposal_approval(
    state: AgentGraphState,
    runtime: Runtime[AgentGraphContext],
) -> AgentGraphUpdate:
    """Prepare once, pause via workflow service, then trust only a stored decision."""

    update: AgentGraphUpdate = {"node_history": ("proposal_approval",)}
    provider = runtime.context.proposal_provider
    if provider is None:
        update.update(
            _pending_failure(
                AgentFailureCode.RECOMMENDATION_FAILURE,
                "the proposal service is not configured",
            )
        )
        return update
    run_state = state["run_state"]
    route: GraphRoute
    try:
        view = (
            provider.create_or_get(
                run_state.case_id,
                actor_id=runtime.context.actor_id,
                correlation_id=run_state.run_id,
                workflow_run_id=run_state.run_id,
            )
            if run_state.proposal_id is None
            else provider.get(run_state.proposal_id)
        )
        proposal = view.proposal
        if proposal.status is ProposalStatus.APPROVED:
            view = provider.execute(
                proposal.proposal_id,
                idempotency_key=f"workflow:{run_state.run_id}:v{proposal.version}",
                actor_id=runtime.context.actor_id,
                actor_role="workflow_executor",
                correlation_id=run_state.run_id,
            )
            proposal = view.proposal
        if proposal.status in {
            ProposalStatus.AWAITING_APPROVAL,
            ProposalStatus.APPROVED,
            ProposalStatus.EXECUTING,
        }:
            next_state = _replace_run_state(
                run_state,
                proposal_id=proposal.proposal_id,
                proposal_status=proposal.status.value,
            )
            route = "proposal_approval"
        else:
            changed = proposal.status is ProposalStatus.EXECUTED
            summary = (
                "The explicitly approved proposal was freshly revalidated and executed once."
                if changed
                else f"Proposal ended as {proposal.status.value}; operator escalation is required."
            )
            next_state = _replace_run_state(
                run_state,
                status=RunStatus.COMPLETED,
                final_outcome={"summary": summary},
                proposal_id=proposal.proposal_id,
                proposal_status=proposal.status.value,
                proposal_execution_result=(
                    proposal.execution_result.model_dump(mode="json")
                    if proposal.execution_result is not None
                    else None
                ),
            )
            route = "completion"
    except Exception:
        update.update(
            _pending_failure(
                AgentFailureCode.RECOMMENDATION_FAILURE,
                "proposal authorization or execution failed safely",
            )
        )
        return update
    update.update({"run_state": next_state, "route": route})
    return update


def model_reasoning(
    state: AgentGraphState,
    runtime: Runtime[AgentGraphContext],
) -> AgentGraphUpdate:
    """Apply pre-turn guards and ask the provider-neutral model for one decision."""

    run_state = state["run_state"]
    update: AgentGraphUpdate = {
        "node_history": ("model_reasoning",),
        "pending_decision": None,
        "model_error_code": None,
        "pending_failure": None,
    }
    if _deadline_reached(run_state, runtime):
        update.update(
            _pending_failure(
                AgentFailureCode.DEADLINE_EXCEEDED,
                "the agent run deadline was reached",
            )
        )
        return update
    if run_state.current_turn >= run_state.budget.max_model_turns:
        update.update(
            _pending_failure(
                AgentFailureCode.BUDGET_EXHAUSTED,
                "the model-turn budget was exhausted",
            )
        )
        return update

    try:
        run_state = _replace_run_state(
            run_state,
            current_turn=run_state.current_turn + 1,
        )
    except ValidationError:
        update.update(
            _pending_failure(
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "the model turn could not be recorded in the run state",
            )
        )
        return update
    update["run_state"] = run_state

    try:
        raw_decision: object = runtime.context.model.decide(
            build_model_request(run_state)
        )
    except DecisionModelError as error:
        if _deadline_reached(run_state, runtime):
            update.update(
                _pending_failure(
                    AgentFailureCode.DEADLINE_EXCEEDED,
                    "the agent run deadline was reached",
                )
            )
        elif error.code is ModelErrorCode.MALFORMED_OUTPUT:
            update.update(
                {
                    "route": "decision_validation",
                    "model_error_code": ModelErrorCode.MALFORMED_OUTPUT,
                }
            )
        else:
            update.update(
                _pending_failure(
                    AgentFailureCode.MODEL_FAILURE,
                    "the model could not produce a decision",
                )
            )
        return update
    except Exception:
        if _deadline_reached(run_state, runtime):
            update.update(
                _pending_failure(
                    AgentFailureCode.DEADLINE_EXCEEDED,
                    "the agent run deadline was reached",
                )
            )
        else:
            update.update(
                _pending_failure(
                    AgentFailureCode.MODEL_FAILURE,
                    "the model could not produce a decision",
                )
            )
        return update

    if _deadline_reached(run_state, runtime):
        update.update(
            _pending_failure(
                AgentFailureCode.DEADLINE_EXCEEDED,
                "the agent run deadline was reached",
            )
        )
        return update

    if isinstance(
        raw_decision,
        CallToolDecision | AskInformationDecision | FinishDecision,
    ):
        update.update(
            {
                "route": "decision_validation",
                "pending_decision": raw_decision,
            }
        )
    else:
        update.update(
            {
                "route": "decision_validation",
                "model_error_code": ModelErrorCode.MALFORMED_OUTPUT,
            }
        )
    return update


def _recover_malformed_decision(state: AgentGraphState) -> AgentGraphUpdate:
    """Apply the Phase 6 bounded malformed-output recovery policy."""

    run_state = state["run_state"]
    if run_state.malformed_retry_count >= run_state.budget.max_malformed_retries:
        return _pending_failure(
            AgentFailureCode.MALFORMED_DECISION,
            "model output did not match the decision schema",
        )
    try:
        recovered_state = _replace_run_state(
            run_state,
            malformed_retry_count=run_state.malformed_retry_count + 1,
            messages=(
                *run_state.messages,
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
        return _pending_failure(
            AgentFailureCode.IMPOSSIBLE_TRANSITION,
            "malformed-output recovery could not update the run state",
        )
    return {
        "run_state": recovered_state,
        "route": "model_reasoning",
        "pending_decision": None,
        "model_error_code": None,
        "pending_failure": None,
    }


def decision_validation(state: AgentGraphState) -> AgentGraphUpdate:
    """Validate one proposed decision and select its explicit application route."""

    update: AgentGraphUpdate = {"node_history": ("decision_validation",)}
    if state["model_error_code"] is ModelErrorCode.MALFORMED_OUTPUT:
        update.update(_recover_malformed_decision(state))
        return update

    pending_decision = state["pending_decision"]
    if pending_decision is None:
        update.update(
            _pending_failure(
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "decision validation received no model decision",
            )
        )
        return update
    try:
        decision = validate_agent_decision(pending_decision)
        run_state = _replace_run_state(
            state["run_state"],
            messages=(
                *state["run_state"].messages,
                ConversationMessage(
                    role=ConversationRole.AGENT,
                    content=decision.summary,
                ),
            ),
        )
    except ValidationError:
        update.update(_recover_malformed_decision(state))
        return update

    update.update(
        {
            "run_state": run_state,
            "pending_decision": decision,
            "model_error_code": None,
        }
    )
    decision_object: object = decision
    if isinstance(decision_object, CallToolDecision):
        update["route"] = "tool_execution"
    elif isinstance(decision_object, AskInformationDecision):
        update["route"] = "information_or_escalation"
    elif isinstance(decision_object, FinishDecision):
        update["route"] = "outcome_handling"
    else:
        update.update(
            _pending_failure(
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "the model returned an unsupported decision",
            )
        )
    return update


def tool_execution(
    state: AgentGraphState,
    runtime: Runtime[AgentGraphContext],
) -> AgentGraphUpdate:
    """Execute one validated call through the exact Phase 4 read-only dispatcher."""

    update: AgentGraphUpdate = {"node_history": ("tool_execution",)}
    decision = state["pending_decision"]
    if not isinstance(decision, CallToolDecision):
        update.update(
            _pending_failure(
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "tool execution received no validated tool decision",
            )
        )
        return update

    run_state = state["run_state"]
    fingerprint = fingerprint_tool_call(decision)
    if fingerprint in run_state.previous_tool_call_fingerprints:
        update.update(
            _pending_failure(
                AgentFailureCode.REPEATED_TOOL_CALL,
                "an identical tool call was already attempted",
            )
        )
        return update
    if _deadline_reached(run_state, runtime):
        update.update(
            _pending_failure(
                AgentFailureCode.DEADLINE_EXCEEDED,
                "the agent run deadline was reached",
            )
        )
        return update

    try:
        required_permission = runtime.context.dispatcher.required_permission_for(
            decision.tool_name
        )
    except UnknownToolError:
        update.update(
            _pending_failure(
                AgentFailureCode.UNKNOWN_TOOL,
                "the requested tool is not available",
            )
        )
        return update

    try:
        run_state = _replace_run_state(
            run_state,
            previous_tool_call_fingerprints=(
                run_state.previous_tool_call_fingerprints | {fingerprint}
            ),
        )
    except ValidationError:
        update.update(
            _pending_failure(
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "the tool attempt could not be recorded in the run state",
            )
        )
        return update

    try:
        execution_context = ToolExecutionContext(
            actor_id=runtime.context.actor_id,
            correlation_id=run_state.run_id,
            permissions=frozenset({required_permission}),
            deadline_at=run_state.budget.deadline_at,
        )
        result = runtime.context.dispatcher.dispatch(decision, execution_context)
        result_payload = result.model_dump(mode="json")
        succeeded = result_payload.get("ok") is True
        observation = ToolObservation.model_validate(
            {
                "observation_id": (
                    f"observation-{len(run_state.tool_observations) + 1}"
                ),
                "tool_name": decision.tool_name,
                "tool_call_fingerprint": fingerprint,
                "ok": succeeded,
                "payload": result_payload,
            }
        )
    except Exception:
        update.update(
            _pending_failure(
                AgentFailureCode.TOOL_FAILURE,
                "a read-only tool could not return a safe result",
            )
        )
        return update

    try:
        run_state = _replace_run_state(
            run_state,
            tool_observations=(*run_state.tool_observations, observation),
            messages=(
                *run_state.messages,
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
        update.update(
            _pending_failure(
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "the tool observation could not be recorded in the run state",
            )
        )
        return update
    update["run_state"] = run_state

    if _deadline_reached(run_state, runtime):
        update.update(
            _pending_failure(
                AgentFailureCode.DEADLINE_EXCEEDED,
                "the agent run deadline was reached",
            )
        )
    elif not succeeded:
        update.update(
            _pending_failure(
                AgentFailureCode.TOOL_FAILURE,
                "a read-only tool returned a safe failure",
            )
        )
    else:
        update["route"] = "outcome_handling"
    return update


def outcome_handling(state: AgentGraphState) -> AgentGraphUpdate:
    """Record a final outcome or continue after one safe tool observation."""

    update: AgentGraphUpdate = {"node_history": ("outcome_handling",)}
    decision = state["pending_decision"]
    if isinstance(decision, CallToolDecision):
        update.update(
            {
                "route": "model_reasoning",
                "pending_decision": None,
                "model_error_code": None,
            }
        )
        return update
    if isinstance(decision, FinishDecision):
        try:
            run_state = _replace_run_state(
                state["run_state"],
                status=RunStatus.COMPLETED,
                final_outcome=decision.outcome,
            )
        except ValidationError:
            update.update(
                _pending_failure(
                    AgentFailureCode.IMPOSSIBLE_TRANSITION,
                    "the final outcome referenced unavailable evidence",
                )
            )
            return update
        update.update(
            {
                "run_state": run_state,
                "route": "completion",
                "pending_decision": None,
            }
        )
        return update
    update.update(
        _pending_failure(
            AgentFailureCode.IMPOSSIBLE_TRANSITION,
            "outcome handling received an unsupported decision",
        )
    )
    return update


def information_or_escalation(state: AgentGraphState) -> AgentGraphUpdate:
    """Record one typed operator information request as a terminal result."""

    update: AgentGraphUpdate = {"node_history": ("information_or_escalation",)}
    decision = state["pending_decision"]
    if not isinstance(decision, AskInformationDecision):
        update.update(
            _pending_failure(
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "information handling received no information request",
            )
        )
        return update
    try:
        run_state = _replace_run_state(
            state["run_state"],
            status=RunStatus.AWAITING_INFORMATION,
            information_request=decision,
        )
    except ValidationError:
        update.update(
            _pending_failure(
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "the information request could not be recorded",
            )
        )
        return update
    update.update(
        {
            "run_state": run_state,
            "route": "completion",
            "pending_decision": None,
        }
    )
    return update


def completion(state: AgentGraphState) -> AgentGraphUpdate:
    """Verify that a successful terminal state is complete and consistent."""

    update: AgentGraphUpdate = {"node_history": ("completion",)}
    if state["run_state"].status not in {
        RunStatus.COMPLETED,
        RunStatus.AWAITING_INFORMATION,
    }:
        update.update(
            _pending_failure(
                AgentFailureCode.IMPOSSIBLE_TRANSITION,
                "completion received a non-terminal run state",
            )
        )
    else:
        update["route"] = "end"
    return update


def safe_failure(state: AgentGraphState) -> AgentGraphUpdate:
    """Convert only a minimized pending failure into trusted terminal run state."""

    failure = state["pending_failure"]
    if failure is None:
        failure = SafeAgentFailure(
            code=AgentFailureCode.IMPOSSIBLE_TRANSITION,
            message="safe failure received no failure reason",
        )
    run_state = _replace_run_state(
        state["run_state"],
        status=RunStatus.FAILED,
        final_outcome=None,
        information_request=None,
        failure=failure,
    )
    return {
        "run_state": run_state,
        "node_history": ("safe_failure",),
        "pending_decision": None,
        "model_error_code": None,
        "pending_failure": None,
    }


def route_from_state(state: AgentGraphState) -> GraphRoute:
    """Return the explicit next node selected by application state."""

    return state["route"]


def route_after_completion(state: AgentGraphState) -> Literal["end", "safe_failure"]:
    """End a valid terminal run or route an impossible completion safely."""

    if state["route"] == "end":
        return "end"
    return "safe_failure"


def _add_routes(
    builder: StateGraph[
        AgentGraphState, AgentGraphContext, AgentGraphState, AgentGraphState
    ],
    source: GraphNode,
    destinations: tuple[GraphRoute, ...],
) -> None:
    """Add one explicit conditional routing table to the graph builder."""

    builder.add_conditional_edges(
        source,
        route_from_state,
        {destination: destination for destination in destinations},
    )


def build_recovery_graph(
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    *,
    enable_recommendations: bool = False,
    enable_proposals: bool = False,
) -> CompiledStateGraph[
    AgentGraphState,
    AgentGraphContext,
    AgentGraphState,
    AgentGraphState,
]:
    """Build the Phase 7 graph, optionally with Phase 8 durable checkpoints."""

    builder = StateGraph(AgentGraphState, context_schema=AgentGraphContext)
    builder.add_node("intake", intake)
    builder.add_node("model_reasoning", model_reasoning)
    builder.add_node("decision_validation", decision_validation)
    builder.add_node("tool_execution", tool_execution)
    builder.add_node("outcome_handling", outcome_handling)
    builder.add_node("information_or_escalation", information_or_escalation)
    builder.add_node("completion", completion)
    builder.add_node("safe_failure", safe_failure)

    if enable_recommendations:
        builder.add_node("validated_recommendation", validated_recommendation)
        if enable_proposals:
            builder.add_node("proposal_approval", proposal_approval)
        builder.add_edge(START, "validated_recommendation")
        _add_routes(
            builder,
            "validated_recommendation",
            (
                ("proposal_approval", "completion", "safe_failure")
                if enable_proposals
                else ("completion", "safe_failure")
            ),
        )
        if enable_proposals:
            _add_routes(
                builder,
                "proposal_approval",
                ("proposal_approval", "completion", "safe_failure"),
            )
    else:
        builder.add_edge(START, "intake")
    _add_routes(builder, "intake", ("model_reasoning", "safe_failure"))
    _add_routes(
        builder,
        "model_reasoning",
        ("decision_validation", "safe_failure"),
    )
    _add_routes(
        builder,
        "decision_validation",
        (
            "model_reasoning",
            "tool_execution",
            "outcome_handling",
            "information_or_escalation",
            "safe_failure",
        ),
    )
    _add_routes(builder, "tool_execution", ("outcome_handling", "safe_failure"))
    _add_routes(
        builder,
        "outcome_handling",
        ("model_reasoning", "completion", "safe_failure"),
    )
    _add_routes(
        builder,
        "information_or_escalation",
        ("completion", "safe_failure"),
    )
    builder.add_conditional_edges(
        "completion",
        route_after_completion,
        {"end": END, "safe_failure": "safe_failure"},
    )
    builder.add_edge("safe_failure", END)
    return builder.compile(checkpointer=checkpointer)


class RecoveryGraphRunner:
    """Invoke and inspect one compiled graph with injected safe dependencies."""

    def __init__(
        self,
        model: DecisionModel,
        dispatcher: ReadOnlyToolDispatcher,
        *,
        actor_id: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._context = AgentGraphContext(
            model=model,
            dispatcher=dispatcher,
            actor_id=actor_id,
            clock=clock,
        )
        self._graph = build_recovery_graph()

    @property
    def graph(
        self,
    ) -> CompiledStateGraph[
        AgentGraphState,
        AgentGraphContext,
        AgentGraphState,
        AgentGraphState,
    ]:
        """Return the compiled graph for topology and node inspection."""

        return self._graph

    @staticmethod
    def _config(run_state: AgentRunState) -> RunnableConfig:
        """Bound LangGraph's cycle guard above the explicit application budget."""

        return {"recursion_limit": run_state.budget.max_model_turns * 5 + 10}

    def run(self, initial_state: AgentRunState) -> AgentRunState:
        """Run to one terminal state and return the trusted Phase 6-shaped result."""

        final_state = cast(
            AgentGraphState,
            self._graph.invoke(
                create_graph_state(initial_state),
                config=self._config(initial_state),
                context=self._context,
            ),
        )
        return final_state["run_state"]

    def stream_states(self, initial_state: AgentRunState) -> Iterator[AgentGraphState]:
        """Yield complete inspectable state after each graph super-step."""

        for snapshot in self._graph.stream(
            create_graph_state(initial_state),
            config=self._config(initial_state),
            context=self._context,
            stream_mode="values",
        ):
            yield cast(AgentGraphState, snapshot)

"""Build safe requests for a decision model."""

from travelops_recovery_agent.agent.decision_model import ModelContextItem, ModelRequest
from travelops_recovery_agent.agent.models import AgentRunState
from travelops_recovery_agent.agent.tools import get_model_tool_definitions
from travelops_recovery_agent.context_engineering.models import (
    BuildStatus,
    ContextBuildResult,
)


class ContextBuildRejectedError(ValueError):
    """Raised before a model call when mandatory context cannot be built safely."""


def build_model_request(state: AgentRunState) -> ModelRequest:
    """Build model input from trusted state and safe tool descriptions."""

    return ModelRequest(
        run_id=state.run_id,
        case_id=state.case_id,
        turn=state.current_turn,
        messages=state.messages,
        observations=state.tool_observations,
        tools=get_model_tool_definitions(),
    )


def build_governed_model_request(
    state: AgentRunState,
    context: ContextBuildResult,
) -> ModelRequest:
    """Project only selected evidence and exposed read schemas to the model."""

    if context.case_id != state.case_id:
        raise ContextBuildRejectedError("context case does not match agent state")
    if context.status is BuildStatus.ESCALATED:
        raise ContextBuildRejectedError(
            context.escalation_reason or "context build stopped safely"
        )
    exposed_read_tools = frozenset(
        tool.name for tool in context.tools if tool.exposed and tool.kind == "read"
    )
    selected_ids = {item.evidence_id for item in context.selected}
    observations = tuple(
        observation
        for observation in state.tool_observations
        if observation.observation_id in selected_ids
    )
    return ModelRequest(
        run_id=state.run_id,
        case_id=state.case_id,
        turn=state.current_turn,
        messages=(),
        observations=observations,
        context_items=tuple(
            ModelContextItem(
                evidence_id=item.evidence_id,
                source_type=item.source_type.value,
                authority=int(item.authority),
                freshness=item.freshness.value,
                content=item.content,
                compacted=item.compacted,
            )
            for item in context.selected
        ),
        tools=get_model_tool_definitions(exposed_read_tools),
    )

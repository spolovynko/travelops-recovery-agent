"""Build safe requests for a decision model."""

from travelops_recovery_agent.agent.decision_model import ModelRequest
from travelops_recovery_agent.agent.models import AgentRunState
from travelops_recovery_agent.agent.tools import get_model_tool_definitions


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

"""Reconstruct executable graph dependencies without checkpointing them."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Protocol

from travelops_recovery_agent.agent.decision_model import (
    DecisionModel,
    DecisionModelError,
    ModelErrorCode,
    ModelRequest,
)
from travelops_recovery_agent.agent.graph import (
    AgentGraphContext,
    AgentGraphState,
    utc_now,
)
from travelops_recovery_agent.agent.models import AgentDecision
from travelops_recovery_agent.agent.tools import ReadOnlyToolDispatcher
from travelops_recovery_agent.application.proposals import ProposalService
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.application.recommendations import RecommendationService
from travelops_recovery_agent.persistence.session import SessionFactory
from travelops_recovery_agent.persistence.unit_of_work import (
    SqlAlchemyRecoveryDataUnitOfWork,
)
from travelops_recovery_agent.tools.adapters import (
    GetBookingTool,
    GetDisruptionPolicyTool,
    GetFlightStatusTool,
    SearchAlternativeItinerariesTool,
    ValidateItineraryTool,
)
from travelops_recovery_agent.workflow.models import WorkflowRun


class GraphContextFactory(Protocol):
    """Rebuild all executable services for one claimed durable run."""

    def __call__(
        self, run: WorkflowRun, graph_state: AgentGraphState | None
    ) -> AgentGraphContext: ...


class UnavailableDecisionModel:
    """Safe no-default-provider adapter used until one is explicitly configured."""

    def decide(self, request: ModelRequest) -> AgentDecision:
        del request
        raise DecisionModelError(
            ModelErrorCode.INVOCATION_FAILED,
            "no decision model is configured",
        )


@dataclass(frozen=True)
class ApplicationGraphContextFactory:
    """Production composition from stable settings and short-lived UoWs."""

    session_factory: SessionFactory
    model_factory: Callable[[WorkflowRun], DecisionModel]
    actor_id: str = "workflow-runner"
    enable_proposals: bool = False

    def __call__(
        self, run: WorkflowRun, graph_state: AgentGraphState | None
    ) -> AgentGraphContext:
        query_service = OperationalQueryService(
            partial(SqlAlchemyRecoveryDataUnitOfWork, self.session_factory)
        )
        dispatcher = ReadOnlyToolDispatcher(
            (
                GetBookingTool(query_service),
                GetFlightStatusTool(query_service),
                GetDisruptionPolicyTool(query_service),
                SearchAlternativeItinerariesTool(query_service),
                ValidateItineraryTool(query_service),
            )
        )
        return AgentGraphContext(
            model=self.model_factory(run),
            dispatcher=dispatcher,
            actor_id=self.actor_id,
            clock=utc_now,
            recommendation_provider=RecommendationService(
                partial(SqlAlchemyRecoveryDataUnitOfWork, self.session_factory)
            ),
            proposal_provider=ProposalService(self.session_factory),
            proposal_workflow_enabled=self.enable_proposals,
        )

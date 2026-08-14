"""FastAPI application construction."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from functools import partial

from fastapi import FastAPI
from sqlalchemy import Engine

from travelops_recovery_agent.api.evaluation_routes import create_evaluation_router
from travelops_recovery_agent.api.middleware import RequestIdMiddleware
from travelops_recovery_agent.api.proposal_routes import (
    create_proposal_router,
    get_proposal_service,
)
from travelops_recovery_agent.api.recovery_routes import (
    RecoveryQueryService,
    create_recovery_router,
    get_recovery_query_service,
)
from travelops_recovery_agent.api.schemas import HealthResponse
from travelops_recovery_agent.api.workflow_routes import create_workflow_router
from travelops_recovery_agent.application.proposals import ProposalService
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.core.logging import configure_logging
from travelops_recovery_agent.persistence.session import (
    create_database_engine,
    create_session_factory,
)
from travelops_recovery_agent.persistence.unit_of_work import (
    SqlAlchemyRecoveryDataUnitOfWork,
)
from travelops_recovery_agent.workflow.checkpoints import CheckpointStore
from travelops_recovery_agent.workflow.executor import WorkflowExecutor
from travelops_recovery_agent.workflow.persistence import WorkflowRepository
from travelops_recovery_agent.workflow.runtime import (
    ApplicationGraphContextFactory,
    UnavailableDecisionModel,
)
from travelops_recovery_agent.workflow.service import DurableWorkflowService


def create_app(
    settings: Settings | None = None,
    recovery_query_service: RecoveryQueryService | None = None,
    workflow_service: DurableWorkflowService | None = None,
    workflow_executor: WorkflowExecutor | None = None,
    proposal_service: ProposalService | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    configure_logging(resolved_settings.log_level)

    owned_engine: Engine | None = None
    service = recovery_query_service
    resolved_proposal_service = proposal_service
    if service is None and resolved_settings.database_url is not None:
        owned_engine = create_database_engine(resolved_settings)
        session_factory = create_session_factory(owned_engine)
        service = OperationalQueryService(
            partial(SqlAlchemyRecoveryDataUnitOfWork, session_factory)
        )
        resolved_proposal_service = ProposalService(session_factory)

    checkpoint_store: CheckpointStore | None = None
    resolved_workflow_service = workflow_service
    resolved_workflow_executor = workflow_executor

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal checkpoint_store, resolved_workflow_service, resolved_workflow_executor
        try:
            if (
                resolved_workflow_service is None
                and owned_engine is not None
                and service is not None
            ):
                session_factory = create_session_factory(owned_engine)
                checkpoint_store = CheckpointStore(resolved_settings).open()
                context_factory = ApplicationGraphContextFactory(
                    session_factory,
                    model_factory=lambda _: UnavailableDecisionModel(),
                    enable_proposals=True,
                )
                resolved_workflow_service = DurableWorkflowService(
                    WorkflowRepository(session_factory),
                    checkpoint_store,
                    context_factory,
                    enable_recommendations=True,
                    enable_proposals=True,
                )
                resolved_workflow_service.apply_event_retention(
                    timedelta(hours=resolved_settings.workflow_event_retention_hours)
                )
                resolved_workflow_executor = WorkflowExecutor(resolved_workflow_service)
                app.state.workflow_service = resolved_workflow_service
                app.state.workflow_executor = resolved_workflow_executor
            yield
        finally:
            if resolved_workflow_executor is not None:
                resolved_workflow_executor.shutdown()
            if checkpoint_store is not None:
                checkpoint_store.close()
            if owned_engine is not None:
                owned_engine.dispose()

    app = FastAPI(title="TravelOps Recovery Agent", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.add_middleware(RequestIdMiddleware)
    app.include_router(create_evaluation_router())
    app.include_router(create_recovery_router())
    app.include_router(create_workflow_router())
    app.include_router(create_proposal_router())
    if service is not None:
        app.dependency_overrides[get_recovery_query_service] = lambda: service
    if resolved_proposal_service is not None:
        app.dependency_overrides[get_proposal_service] = lambda: (
            resolved_proposal_service
        )
    if resolved_workflow_service is not None:
        app.state.workflow_service = resolved_workflow_service
    if resolved_workflow_executor is not None:
        app.state.workflow_executor = resolved_workflow_executor

    @app.get("/health", tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app

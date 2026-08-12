"""FastAPI application construction."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI
from sqlalchemy import Engine

from travelops_recovery_agent.api.middleware import RequestIdMiddleware
from travelops_recovery_agent.api.recovery_routes import (
    RecoveryQueryService,
    create_recovery_router,
    get_recovery_query_service,
)
from travelops_recovery_agent.api.schemas import HealthResponse
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


def create_app(
    settings: Settings | None = None,
    recovery_query_service: RecoveryQueryService | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    configure_logging(resolved_settings.log_level)

    owned_engine: Engine | None = None
    service = recovery_query_service
    if service is None and resolved_settings.database_url is not None:
        owned_engine = create_database_engine(resolved_settings)
        session_factory = create_session_factory(owned_engine)
        service = OperationalQueryService(
            partial(SqlAlchemyRecoveryDataUnitOfWork, session_factory)
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owned_engine is not None:
                owned_engine.dispose()

    app = FastAPI(title="TravelOps Recovery Agent", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.add_middleware(RequestIdMiddleware)
    app.include_router(create_recovery_router())
    if service is not None:
        app.dependency_overrides[get_recovery_query_service] = lambda: service

    @app.get("/health", tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app

"""FastAPI application construction."""

from fastapi import FastAPI

from travelops_recovery_agent.api.middleware import RequestIdMiddleware
from travelops_recovery_agent.api.schemas import HealthResponse
from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()
    configure_logging(resolved_settings.log_level)

    app = FastAPI(title="TravelOps Recovery Agent")
    app.state.settings = resolved_settings
    app.add_middleware(RequestIdMiddleware)

    @app.get("/health", tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app

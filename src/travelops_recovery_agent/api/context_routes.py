"""Developer-only Phase 12 context inspector API."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from travelops_recovery_agent.api.recovery_schemas import ApiErrorDetail, ApiErrorView
from travelops_recovery_agent.context_engineering.inspector import (
    ContextInspectorService,
)
from travelops_recovery_agent.context_engineering.models import (
    ContextBuildResult,
    ContextTask,
)
from travelops_recovery_agent.core.config import Environment


def create_context_router(
    inspector: ContextInspectorService | None = None,
) -> APIRouter:
    service = inspector or ContextInspectorService()
    router = APIRouter(prefix="/api/v1/developer", tags=["developer-context"])

    @router.get("/context-inspector", response_model=ContextBuildResult)
    def inspect_context(
        request: Request,
        case_id: Annotated[str, Query(pattern=r"^[A-Z0-9-]{3,96}$")],
        task: ContextTask = ContextTask.INVESTIGATE,
        workflow_node: Annotated[
            str, Query(pattern=r"^[a-z][a-z0-9_]{1,95}$")
        ] = "model_reasoning",
        operator_role: Annotated[
            str, Query(pattern=r"^[a-z][a-z0-9_]{1,63}$")
        ] = "recovery_operator",
        approval_status: Annotated[
            str | None, Query(pattern=r"^(approved|rejected|pending)$")
        ] = None,
        workflow_status: Annotated[
            str, Query(pattern=r"^(created|running|paused|completed|failed)$")
        ] = "running",
    ) -> ContextBuildResult | JSONResponse:
        if request.app.state.settings.environment is Environment.PRODUCTION:
            return JSONResponse(
                status_code=404,
                content=ApiErrorView(
                    error=ApiErrorDetail(
                        code="not_found",
                        message="The developer context inspector is unavailable.",
                        retryable=False,
                    )
                ).model_dump(mode="json"),
            )
        return service.inspect(
            case_id=case_id,
            task=task,
            workflow_node=workflow_node,
            operator_role=operator_role,
            approval_status=approval_status,
            workflow_status=workflow_status,
        )

    return router

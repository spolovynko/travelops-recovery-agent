"""Phase 10 proposal, human decision, execution, and audit API."""

from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from travelops_recovery_agent.api.proposal_schemas import (
    ProposalDecisionRequest,
    ProposalExecutionRequest,
    ProposalRequest,
)
from travelops_recovery_agent.application.proposal_models import ProposalWithAudit
from travelops_recovery_agent.application.proposals import (
    ProposalError,
    ProposalService,
)


def get_proposal_service() -> ProposalService:
    raise RuntimeError("proposal service is not configured")


ProposalServiceDependency = Annotated[ProposalService, Depends(get_proposal_service)]
ActorId = Annotated[str | None, Header(alias="X-Actor-ID")]
ActorRole = Annotated[str | None, Header(alias="X-Actor-Role")]
CorrelationId = Annotated[str | None, Header(alias="X-Correlation-ID")]


def create_proposal_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["proposals"])

    @router.post("/recovery-cases/{case_id}/proposal", response_model=ProposalWithAudit)
    def create_or_get_proposal(
        case_id: str,
        request: ProposalRequest,
        service: ProposalServiceDependency,
        actor_id: ActorId = None,
        correlation_id: CorrelationId = None,
    ) -> ProposalWithAudit | JSONResponse:
        missing = _require_actor(actor_id)
        if missing is not None:
            return missing
        try:
            return service.create_or_get(
                case_id,
                actor_id=cast(str, actor_id),
                correlation_id=correlation_id or str(uuid4()),
                workflow_run_id=request.workflow_run_id,
            )
        except ProposalError as error:
            return _error(error)

    @router.get("/proposals/{proposal_id}", response_model=ProposalWithAudit)
    def get_proposal(
        proposal_id: str,
        service: ProposalServiceDependency,
        actor_id: ActorId = None,
    ) -> ProposalWithAudit | JSONResponse:
        missing = _require_actor(actor_id)
        if missing is not None:
            return missing
        try:
            return service.get(proposal_id)
        except ProposalError as error:
            return _error(error)

    @router.post("/proposals/{proposal_id}/approve", response_model=ProposalWithAudit)
    def approve_proposal(
        proposal_id: str,
        request: ProposalDecisionRequest,
        service: ProposalServiceDependency,
        actor_id: ActorId = None,
        actor_role: ActorRole = None,
        correlation_id: CorrelationId = None,
    ) -> ProposalWithAudit | JSONResponse:
        return _decide(
            service, proposal_id, request, True, actor_id, actor_role, correlation_id
        )

    @router.post("/proposals/{proposal_id}/reject", response_model=ProposalWithAudit)
    def reject_proposal(
        proposal_id: str,
        request: ProposalDecisionRequest,
        service: ProposalServiceDependency,
        actor_id: ActorId = None,
        actor_role: ActorRole = None,
        correlation_id: CorrelationId = None,
    ) -> ProposalWithAudit | JSONResponse:
        return _decide(
            service, proposal_id, request, False, actor_id, actor_role, correlation_id
        )

    @router.post("/proposals/{proposal_id}/execute", response_model=ProposalWithAudit)
    def execute_proposal(
        proposal_id: str,
        request: ProposalExecutionRequest,
        service: ProposalServiceDependency,
        actor_id: ActorId = None,
        actor_role: ActorRole = None,
        correlation_id: CorrelationId = None,
    ) -> ProposalWithAudit | JSONResponse:
        missing = _require_actor(actor_id, actor_role)
        if missing is not None:
            return missing
        try:
            return service.execute(
                proposal_id,
                idempotency_key=request.idempotency_key,
                actor_id=cast(str, actor_id),
                actor_role=cast(str, actor_role),
                correlation_id=correlation_id or str(uuid4()),
            )
        except ProposalError as error:
            return _error(error)

    @router.get("/proposals/{proposal_id}/execution", response_model=ProposalWithAudit)
    @router.get("/proposals/{proposal_id}/audit", response_model=ProposalWithAudit)
    def get_proposal_history(
        proposal_id: str,
        service: ProposalServiceDependency,
        actor_id: ActorId = None,
    ) -> ProposalWithAudit | JSONResponse:
        missing = _require_actor(actor_id)
        if missing is not None:
            return missing
        try:
            return service.get(proposal_id)
        except ProposalError as error:
            return _error(error)

    return router


def _decide(
    service: ProposalService,
    proposal_id: str,
    request: ProposalDecisionRequest,
    approve: bool,
    actor_id: str | None,
    actor_role: str | None,
    correlation_id: str | None,
) -> ProposalWithAudit | JSONResponse:
    missing = _require_actor(actor_id, actor_role)
    if missing is not None:
        return missing
    try:
        return service.decide(
            proposal_id,
            version=request.version,
            itinerary_fingerprint=request.itinerary_fingerprint,
            approve=approve,
            actor_id=cast(str, actor_id),
            actor_role=cast(str, actor_role),
            correlation_id=correlation_id or str(uuid4()),
            reason=request.reason,
        )
    except ProposalError as error:
        return _error(error)


def _require_actor(
    actor_id: str | None, actor_role: str | None = "optional"
) -> JSONResponse | None:
    if not actor_id or actor_role is None:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "actor_context_required",
                    "message": "Explicit actor context is required.",
                    "retryable": False,
                }
            },
        )
    return None


def _error(error: ProposalError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {"code": error.code, "message": str(error), "retryable": False}
        },
    )

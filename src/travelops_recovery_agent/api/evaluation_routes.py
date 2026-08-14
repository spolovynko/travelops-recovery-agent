"""Read-only operator access to the frozen Phase 11 evaluation report."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from travelops_recovery_agent.api.recovery_schemas import ApiErrorDetail, ApiErrorView
from travelops_recovery_agent.evaluation.models import EvaluationReport


def create_evaluation_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])

    @router.get("/phase-11", response_model=EvaluationReport)
    def get_phase_11_evaluation(request: Request) -> EvaluationReport | JSONResponse:
        path: Path = request.app.state.settings.evaluation_report_path
        try:
            return EvaluationReport.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return JSONResponse(
                status_code=503,
                content=ApiErrorView(
                    error=ApiErrorDetail(
                        code="service_unavailable",
                        message=(
                            "The deterministic evaluation report has not been generated. "
                            "Run the documented Phase 11 evaluation command."
                        ),
                        retryable=False,
                    )
                ).model_dump(mode="json"),
            )

    return router

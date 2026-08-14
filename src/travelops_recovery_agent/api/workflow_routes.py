"""Start, inspect, stream, cancel, and resume durable investigations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from travelops_recovery_agent.api.workflow_schemas import (
    WorkflowRunView,
    workflow_run_view,
)
from travelops_recovery_agent.workflow.executor import WorkflowExecutor
from travelops_recovery_agent.workflow.persistence import (
    DuplicateActiveRunError,
    RecoveryCaseNotFoundError,
    WorkflowNotFoundError,
)
from travelops_recovery_agent.workflow.service import (
    DurableWorkflowService,
    ResumeRejectedError,
)

POLL_INTERVAL_SECONDS = 0.2


def get_workflow_service(request: Request) -> DurableWorkflowService:
    service = getattr(request.app.state, "workflow_service", None)
    if not isinstance(service, DurableWorkflowService):
        raise RuntimeError("durable workflow service is unavailable")
    return service


def get_workflow_executor(request: Request) -> WorkflowExecutor:
    executor = getattr(request.app.state, "workflow_executor", None)
    if not isinstance(executor, WorkflowExecutor):
        raise RuntimeError("durable workflow executor is unavailable")
    return executor


def _unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "workflow_unavailable",
                "message": "Durable investigations are not configured.",
                "retryable": True,
            }
        },
    )


def _not_found(run_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "workflow_not_found",
                "message": f"Workflow run {run_id} was not found.",
                "retryable": False,
            }
        },
    )


def _view(service: DurableWorkflowService, run_id: str) -> WorkflowRunView:
    return workflow_run_view(service.get_run(run_id), service.get_graph_state(run_id))


def _cursor(last_event_id: str | None, cursor: int | None) -> int:
    if cursor is not None:
        return max(0, cursor)
    if last_event_id is None:
        return 0
    try:
        return max(0, int(last_event_id.rsplit(":", 1)[-1]))
    except ValueError:
        return 0


def _sse_message(event_id: str, event_type: str, payload: object) -> str:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    return f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"


def create_workflow_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["workflow"])

    @router.post(
        "/recovery-cases/{case_id}/workflow-runs",
        response_model=WorkflowRunView,
        status_code=202,
    )
    def start_workflow(
        case_id: str,
        request: Request,
    ) -> WorkflowRunView | JSONResponse:
        try:
            service = get_workflow_service(request)
            executor = get_workflow_executor(request)
            run = service.create_run(case_id)
        except DuplicateActiveRunError as error:
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "active_workflow_exists",
                        "message": "This case already has an active workflow.",
                        "retryable": False,
                        "existing_run_id": error.run_id,
                    }
                },
            )
        except RecoveryCaseNotFoundError:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "recovery_case_not_found",
                        "message": f"Recovery case {case_id} was not found.",
                        "retryable": False,
                    }
                },
            )
        except RuntimeError:
            return _unavailable()
        executor.submit(run.identity.run_id)
        return _view(service, run.identity.run_id)

    @router.get("/workflow-runs/{run_id}", response_model=WorkflowRunView)
    def inspect_workflow(
        run_id: str,
        request: Request,
    ) -> WorkflowRunView | JSONResponse:
        try:
            return _view(get_workflow_service(request), run_id)
        except RuntimeError:
            return _unavailable()
        except WorkflowNotFoundError:
            return _not_found(run_id)

    @router.post("/workflow-runs/{run_id}/cancel", response_model=WorkflowRunView)
    def cancel_workflow(
        run_id: str,
        request: Request,
    ) -> WorkflowRunView | JSONResponse:
        try:
            service = get_workflow_service(request)
            executor = get_workflow_executor(request)
            run = service.request_cancellation(run_id)
            if run.status.is_active:
                executor.submit(run_id)
            return _view(service, run_id)
        except RuntimeError:
            return _unavailable()
        except WorkflowNotFoundError:
            return _not_found(run_id)

    @router.post("/workflow-runs/{run_id}/resume", response_model=WorkflowRunView)
    def resume_workflow(
        run_id: str,
        request: Request,
    ) -> WorkflowRunView | JSONResponse:
        try:
            service = get_workflow_service(request)
            run = service.get_run(run_id)
            if run.status.value != "paused":
                raise ResumeRejectedError("only paused workflows can resume")
            if not get_workflow_executor(request).submit(run_id):
                raise ResumeRejectedError("workflow is already scheduled")
            return _view(service, run_id)
        except WorkflowNotFoundError:
            return _not_found(run_id)
        except RuntimeError as error:
            if str(error) == "durable workflow service is unavailable":
                return _unavailable()
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "workflow_resume_rejected",
                        "message": "The workflow cannot be resumed in its current state.",
                        "retryable": False,
                    }
                },
            )

    @router.get("/workflow-runs/{run_id}/events", response_model=None)
    async def stream_workflow(
        run_id: str,
        request: Request,
        cursor: int | None = Query(default=None, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse | JSONResponse:
        try:
            service = get_workflow_service(request)
            service.get_run(run_id)
        except RuntimeError:
            return _unavailable()
        except WorkflowNotFoundError:
            return _not_found(run_id)
        after = _cursor(last_event_id, cursor)
        settings = request.app.state.settings
        event_batch_size = min(settings.workflow_event_batch_size, 250)
        heartbeat_seconds = settings.workflow_sse_heartbeat_seconds

        async def events() -> AsyncIterator[str]:
            nonlocal after
            last_delivery = asyncio.get_running_loop().time()
            oldest = await asyncio.to_thread(service.oldest_event_sequence, run_id)
            if after > 0 and oldest is not None and oldest > after + 1:
                run = await asyncio.to_thread(service.get_run, run_id)
                yield _sse_message(
                    f"{run_id}:{run.last_event_sequence}",
                    "stream.replay_reset_required",
                    {
                        "run_id": run_id,
                        "requested_after": after,
                        "oldest_available": oldest,
                        "snapshot_required": True,
                    },
                )
                after = run.last_event_sequence
            while not await request.is_disconnected():
                batch = await asyncio.to_thread(
                    service.list_events,
                    run_id,
                    after_sequence=after,
                    limit=event_batch_size,
                )
                for event in batch:
                    yield _sse_message(
                        event.event_id,
                        event.type.value,
                        event.model_dump(mode="json"),
                    )
                    after = event.sequence
                    last_delivery = asyncio.get_running_loop().time()
                run = await asyncio.to_thread(service.get_run, run_id)
                if run.status.is_terminal and after >= run.last_event_sequence:
                    return
                now = asyncio.get_running_loop().time()
                if now - last_delivery >= heartbeat_seconds:
                    yield f": heartbeat {datetime.now(UTC).isoformat()}\n\n"
                    last_delivery = now
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return router

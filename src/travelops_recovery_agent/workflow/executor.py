"""Small in-process launcher; PostgreSQL leases remain authoritative."""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from travelops_recovery_agent.workflow.service import (
    DurableWorkflowService,
    ResumeRejectedError,
)

LOGGER = logging.getLogger(__name__)


class WorkflowExecutor:
    """Run durable workflows without becoming a second orchestrator."""

    def __init__(
        self, service: DurableWorkflowService, *, max_workers: int = 4
    ) -> None:
        self._service = service
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="travelops-workflow"
        )
        self._futures: dict[str, Future[object]] = {}
        self._lock = Lock()

    def submit(self, run_id: str) -> bool:
        with self._lock:
            current = self._futures.get(run_id)
            if current is not None and not current.done():
                return False
            future = self._pool.submit(self._execute_safely, run_id)
            self._futures[run_id] = future
            return True

    def _execute_safely(self, run_id: str) -> object | None:
        try:
            return self._service.execute(run_id)
        except ResumeRejectedError:
            return None
        except Exception:
            LOGGER.exception(
                "durable workflow runner failed",
                extra={"workflow_run_id": run_id},
            )
            return None

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=False)

"""PostgreSQL persistence for workflow lifecycle metadata and safe events."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    delete,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from travelops_recovery_agent.persistence.models import Base
from travelops_recovery_agent.persistence.session import SessionFactory
from travelops_recovery_agent.workflow.models import (
    SafePayload,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowIdentity,
    WorkflowRun,
    WorkflowStatus,
)

WORKFLOW_SCHEMA = "workflow"


class WorkflowRunRecord(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_case_created", "case_id", "created_at"),
        {"schema": WORKFLOW_SCHEMA},
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("recovery_cases.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failure_code: Mapped[str | None] = mapped_column(String(64))


class WorkflowEventRecord(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_workflow_events_run_sequence"),
        Index("ix_workflow_events_occurred_at", "occurred_at"),
        {"schema": WORKFLOW_SCHEMA},
    )

    event_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{WORKFLOW_SCHEMA}.workflow_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class WorkflowNotFoundError(LookupError):
    """Raised when a stable workflow run identifier is unknown."""


class DuplicateActiveRunError(RuntimeError):
    """Raised when a case already owns a non-terminal workflow."""

    def __init__(self, run_id: str | None = None) -> None:
        super().__init__("an active workflow already exists for this recovery case")
        self.run_id = run_id


class RecoveryCaseNotFoundError(LookupError):
    """Raised when a new workflow references no stored recovery case."""


def _to_run(record: WorkflowRunRecord) -> WorkflowRun:
    return WorkflowRun(
        identity=WorkflowIdentity(
            case_id=record.case_id,
            run_id=record.run_id,
            thread_id=record.thread_id,
        ),
        status=WorkflowStatus(record.status),
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        cancel_requested_at=record.cancel_requested_at,
        paused_at=record.paused_at,
        lease_owner=record.lease_owner,
        lease_expires_at=record.lease_expires_at,
        last_event_sequence=record.last_event_sequence,
        version=record.version,
        failure_code=record.failure_code,
    )


class WorkflowRepository:
    """Short-transaction repository for durable run ownership and safe events."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create_run(self, identity: WorkflowIdentity, now: datetime) -> WorkflowRun:
        record = WorkflowRunRecord(
            run_id=identity.run_id,
            thread_id=identity.thread_id,
            case_id=identity.case_id,
            status=WorkflowStatus.CREATED.value,
            created_at=now,
            updated_at=now,
            last_event_sequence=0,
            version=1,
        )
        with self._session_factory() as session:
            try:
                session.add(record)
                session.commit()
            except IntegrityError as error:
                session.rollback()
                existing = session.scalar(
                    select(WorkflowRunRecord).where(
                        WorkflowRunRecord.case_id == identity.case_id,
                        WorkflowRunRecord.status.in_(
                            status.value
                            for status in WorkflowStatus
                            if status.is_active
                        ),
                    )
                )
                if existing is None:
                    raise RecoveryCaseNotFoundError(identity.case_id) from error
                raise DuplicateActiveRunError(existing.run_id) from error
            session.refresh(record)
            return _to_run(record)

    def get_run(self, run_id: str) -> WorkflowRun:
        with self._session_factory() as session:
            record = session.get(WorkflowRunRecord, run_id)
            if record is None:
                raise WorkflowNotFoundError(run_id)
            return _to_run(record)

    def acquire_lease(
        self,
        run_id: str,
        *,
        owner: str,
        now: datetime,
        duration: timedelta,
    ) -> WorkflowRun | None:
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(WorkflowRunRecord)
                .where(WorkflowRunRecord.run_id == run_id)
                .with_for_update()
            )
            if record is None:
                raise WorkflowNotFoundError(run_id)
            if record.status in {
                status.value for status in WorkflowStatus if status.is_terminal
            }:
                return None
            if (
                record.lease_owner is not None
                and record.lease_owner != owner
                and record.lease_expires_at is not None
                and record.lease_expires_at > now
            ):
                return None
            record.lease_owner = owner
            record.lease_expires_at = now + duration
            record.status = (
                WorkflowStatus.CANCELLING.value
                if record.cancel_requested_at is not None
                else WorkflowStatus.RUNNING.value
            )
            record.started_at = record.started_at or now
            record.paused_at = None
            record.updated_at = now
            record.version += 1
            session.flush()
            return _to_run(record)

    def release_lease(
        self,
        run_id: str,
        *,
        owner: str,
        now: datetime,
        status: WorkflowStatus,
        failure_code: str | None = None,
    ) -> WorkflowRun:
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(WorkflowRunRecord)
                .where(WorkflowRunRecord.run_id == run_id)
                .with_for_update()
            )
            if record is None:
                raise WorkflowNotFoundError(run_id)
            if record.lease_owner not in {None, owner}:
                raise RuntimeError("workflow lease is owned by another runner")
            record.status = status.value
            record.updated_at = now
            record.lease_owner = None
            record.lease_expires_at = None
            record.paused_at = now if status is WorkflowStatus.PAUSED else None
            record.finished_at = now if status.is_terminal else None
            record.failure_code = failure_code
            record.version += 1
            session.flush()
            return _to_run(record)

    def request_cancellation(self, run_id: str, now: datetime) -> WorkflowRun:
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(WorkflowRunRecord)
                .where(WorkflowRunRecord.run_id == run_id)
                .with_for_update()
            )
            if record is None:
                raise WorkflowNotFoundError(run_id)
            if record.status in {
                status.value for status in WorkflowStatus if status.is_terminal
            }:
                return _to_run(record)
            if record.cancel_requested_at is None:
                record.cancel_requested_at = now
                record.updated_at = now
                record.status = WorkflowStatus.CANCELLING.value
                record.version += 1
            session.flush()
            return _to_run(record)

    def append_event(
        self,
        run_id: str,
        event_type: WorkflowEventType,
        now: datetime,
        payload: SafePayload | None = None,
    ) -> WorkflowEvent:
        with self._session_factory.begin() as session:
            run_record = session.scalar(
                select(WorkflowRunRecord)
                .where(WorkflowRunRecord.run_id == run_id)
                .with_for_update()
            )
            if run_record is None:
                raise WorkflowNotFoundError(run_id)
            sequence = run_record.last_event_sequence + 1
            event = WorkflowEvent.create(
                run_id=run_id,
                sequence=sequence,
                type=event_type,
                occurred_at=now,
                payload=payload,
            )
            session.add(
                WorkflowEventRecord(
                    event_id=event.event_id,
                    run_id=run_id,
                    sequence=sequence,
                    event_type=event.type.value,
                    occurred_at=event.occurred_at,
                    payload=event.payload,
                )
            )
            run_record.last_event_sequence = sequence
            run_record.updated_at = now
            run_record.version += 1
            return event

    def list_events(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[WorkflowEvent, ...]:
        bounded_limit = max(1, min(limit, 250))
        with self._session_factory() as session:
            if session.get(WorkflowRunRecord, run_id) is None:
                raise WorkflowNotFoundError(run_id)
            records = session.scalars(
                select(WorkflowEventRecord)
                .where(
                    WorkflowEventRecord.run_id == run_id,
                    WorkflowEventRecord.sequence > after_sequence,
                )
                .order_by(WorkflowEventRecord.sequence)
                .limit(bounded_limit)
            ).all()
            return tuple(
                WorkflowEvent(
                    event_id=record.event_id,
                    run_id=record.run_id,
                    sequence=record.sequence,
                    type=WorkflowEventType(record.event_type),
                    occurred_at=record.occurred_at,
                    payload=record.payload,
                )
                for record in records
            )

    def oldest_event_sequence(self, run_id: str) -> int | None:
        with self._session_factory() as session:
            return session.scalar(
                select(WorkflowEventRecord.sequence)
                .where(WorkflowEventRecord.run_id == run_id)
                .order_by(WorkflowEventRecord.sequence)
                .limit(1)
            )

    def delete_events_before(self, cutoff: datetime) -> int:
        with self._session_factory.begin() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    delete(WorkflowEventRecord).where(
                        WorkflowEventRecord.occurred_at < cutoff
                    )
                ),
            )
            return int(result.rowcount or 0)

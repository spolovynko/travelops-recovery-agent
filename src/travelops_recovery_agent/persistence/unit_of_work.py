"""SQLAlchemy transaction boundary for recovery persistence."""

from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session

from travelops_recovery_agent.application.repositories import (
    RecoveryDataRepository,
)
from travelops_recovery_agent.persistence.repositories import (
    SqlAlchemyRecoveryDataRepository,
)
from travelops_recovery_agent.persistence.session import SessionFactory


class SqlAlchemyRecoveryDataUnitOfWork:
    """Commit or roll back one caller-defined persistence workflow."""

    repository: RecoveryDataRepository

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("unit of work is already active")

        self._session = self._session_factory()
        self.repository = SqlAlchemyRecoveryDataRepository(self._session)
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._session
        if session is None:
            raise RuntimeError("unit of work is not active")

        try:
            if exception_type is None:
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                    raise
            else:
                session.rollback()
        finally:
            session.close()
            self._session = None

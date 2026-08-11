"""Transactional application services for persistence workflows."""

from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from travelops_recovery_agent.application.models import (
    CompleteRecoveryCase,
    PersistenceRecordCounts,
)
from travelops_recovery_agent.application.repositories import (
    RecoveryDataRepository,
)
from travelops_recovery_agent.core.config import Environment
from travelops_recovery_agent.data.dataset import SyntheticDataset
from travelops_recovery_agent.domain.models import RecoveryCaseId


class DatabaseNotEmptyError(RuntimeError):
    """Raised when safe seeding would overwrite existing records."""


class UnsafeDatabaseResetError(RuntimeError):
    """Raised when reset is requested in production."""


class RecoveryDataUnitOfWork(Protocol):
    """One transactional repository context."""

    repository: RecoveryDataRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


type RecoveryDataUnitOfWorkFactory = Callable[
    [],
    RecoveryDataUnitOfWork,
]


class RecoveryDataService:
    """Run safe persistence workflows inside transactions."""

    def __init__(
        self,
        unit_of_work_factory: RecoveryDataUnitOfWorkFactory,
        environment: Environment,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._environment = environment

    def counts(self) -> PersistenceRecordCounts:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repository.counts()

    def seed(
        self,
        dataset: SyntheticDataset,
        *,
        replace: bool = False,
    ) -> PersistenceRecordCounts:
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.repository
            existing_counts = repository.counts()

            if not existing_counts.is_empty():
                if not replace:
                    raise DatabaseNotEmptyError(
                        "database already contains records; "
                        "use replace=True to reseed it"
                    )

                repository.clear()

            repository.add_dataset(dataset)
            return repository.counts()

    def reset(self) -> PersistenceRecordCounts:
        if self._environment is Environment.PRODUCTION:
            raise UnsafeDatabaseResetError("database reset is blocked in production")

        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.repository.clear()
            return unit_of_work.repository.counts()

    def get_complete_case(
        self,
        case_id: RecoveryCaseId,
    ) -> CompleteRecoveryCase | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repository.get_complete_case(case_id)

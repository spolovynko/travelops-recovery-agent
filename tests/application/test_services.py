"""Tests for transactional persistence application services."""

from types import TracebackType

import pytest
from travelops_recovery_agent.application.services import (
    DatabaseNotEmptyError,
    RecoveryDataService,
    UnsafeDatabaseResetError,
)

from travelops_recovery_agent.application.models import (
    CompleteRecoveryCase,
    PersistenceRecordCounts,
)
from travelops_recovery_agent.application.repositories import RecoveryDataRepository
from travelops_recovery_agent.core.config import Environment
from travelops_recovery_agent.data.dataset import SyntheticDataset
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.models import RecoveryCaseId

EMPTY_COUNTS = PersistenceRecordCounts(0, 0, 0, 0, 0, 0, 0, 0, 0)
SEEDED_COUNTS = PersistenceRecordCounts(13, 20, 10, 13, 20, 10, 1, 3, 10)


class FakeRecoveryDataRepository:
    def __init__(self, counts: PersistenceRecordCounts) -> None:
        self.current_counts = counts
        self.added_datasets: list[SyntheticDataset] = []
        self.requested_case_ids: list[RecoveryCaseId] = []
        self.clear_calls = 0
        self.complete_case: CompleteRecoveryCase | None = None

    def counts(self) -> PersistenceRecordCounts:
        return self.current_counts

    def add_dataset(self, dataset: SyntheticDataset) -> None:
        self.added_datasets.append(dataset)
        self.current_counts = SEEDED_COUNTS

    def get_complete_case(
        self,
        case_id: RecoveryCaseId,
    ) -> CompleteRecoveryCase | None:
        self.requested_case_ids.append(case_id)
        return self.complete_case

    def clear(self) -> None:
        self.clear_calls += 1
        self.current_counts = EMPTY_COUNTS


class FakeRecoveryDataUnitOfWork:
    def __init__(self, repository: RecoveryDataRepository) -> None:
        self.repository = repository
        self.enter_calls = 0
        self.exit_calls = 0
        self.exit_exception_type: type[BaseException] | None = None

    def __enter__(self) -> "FakeRecoveryDataUnitOfWork":
        self.enter_calls += 1
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.exit_calls += 1
        self.exit_exception_type = exception_type


class FakeUnitOfWorkFactory:
    def __init__(self, repository: RecoveryDataRepository) -> None:
        self.repository = repository
        self.created: list[FakeRecoveryDataUnitOfWork] = []

    def __call__(self) -> FakeRecoveryDataUnitOfWork:
        unit_of_work = FakeRecoveryDataUnitOfWork(self.repository)
        self.created.append(unit_of_work)
        return unit_of_work


def test_seed_adds_dataset_when_database_is_empty() -> None:
    dataset = generate_dataset(seed=42)
    repository = FakeRecoveryDataRepository(EMPTY_COUNTS)
    factory = FakeUnitOfWorkFactory(repository)
    service = RecoveryDataService(factory, Environment.DEVELOPMENT)

    result = service.seed(dataset)

    assert result == SEEDED_COUNTS
    assert repository.added_datasets == [dataset]
    assert repository.clear_calls == 0
    assert factory.created[0].exit_exception_type is None


def test_seed_refuses_to_overwrite_existing_records_by_default() -> None:
    repository = FakeRecoveryDataRepository(SEEDED_COUNTS)
    factory = FakeUnitOfWorkFactory(repository)
    service = RecoveryDataService(factory, Environment.DEVELOPMENT)

    with pytest.raises(DatabaseNotEmptyError, match="already contains records"):
        service.seed(generate_dataset(seed=42))

    assert repository.added_datasets == []
    assert repository.clear_calls == 0
    assert factory.created[0].exit_exception_type is DatabaseNotEmptyError


def test_seed_replace_clears_and_reseeds_in_one_unit_of_work() -> None:
    dataset = generate_dataset(seed=42)
    repository = FakeRecoveryDataRepository(SEEDED_COUNTS)
    factory = FakeUnitOfWorkFactory(repository)
    service = RecoveryDataService(factory, Environment.DEVELOPMENT)

    result = service.seed(dataset, replace=True)

    assert result == SEEDED_COUNTS
    assert repository.clear_calls == 1
    assert repository.added_datasets == [dataset]
    assert len(factory.created) == 1


def test_reset_is_blocked_in_production_before_opening_a_transaction() -> None:
    repository = FakeRecoveryDataRepository(SEEDED_COUNTS)
    factory = FakeUnitOfWorkFactory(repository)
    service = RecoveryDataService(factory, Environment.PRODUCTION)

    with pytest.raises(UnsafeDatabaseResetError, match="production"):
        service.reset()

    assert factory.created == []
    assert repository.clear_calls == 0


@pytest.mark.parametrize(
    "environment",
    [Environment.DEVELOPMENT, Environment.TEST],
)
def test_reset_clears_development_and_test_databases(
    environment: Environment,
) -> None:
    repository = FakeRecoveryDataRepository(SEEDED_COUNTS)
    factory = FakeUnitOfWorkFactory(repository)
    service = RecoveryDataService(factory, environment)

    result = service.reset()

    assert result == EMPTY_COUNTS
    assert repository.clear_calls == 1


def test_counts_and_complete_case_retrieval_delegate_to_repository() -> None:
    repository = FakeRecoveryDataRepository(SEEDED_COUNTS)
    factory = FakeUnitOfWorkFactory(repository)
    service = RecoveryDataService(factory, Environment.DEVELOPMENT)

    assert service.counts() == SEEDED_COUNTS
    assert service.get_complete_case("CASE-0007") is None
    assert repository.requested_case_ids == ["CASE-0007"]
    assert len(factory.created) == 2

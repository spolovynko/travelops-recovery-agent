"""Real-PostgreSQL tests for transactional application workflows."""

from functools import partial

import pytest

from travelops_recovery_agent.application.services import (
    DatabaseNotEmptyError,
    RecoveryDataService,
)
from travelops_recovery_agent.core.config import Environment
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.persistence.session import SessionFactory
from travelops_recovery_agent.persistence.unit_of_work import (
    SqlAlchemyRecoveryDataUnitOfWork,
)


@pytest.mark.integration
def test_service_seeds_retrieves_replaces_and_resets_atomically(
    clean_session_factory: SessionFactory,
) -> None:
    unit_of_work_factory = partial(
        SqlAlchemyRecoveryDataUnitOfWork,
        clean_session_factory,
    )
    service = RecoveryDataService(
        unit_of_work_factory,
        Environment.TEST,
    )

    counts = service.seed(generate_dataset(seed=42))
    assert counts.recovery_cases == 10

    with pytest.raises(DatabaseNotEmptyError, match="already contains records"):
        service.seed(generate_dataset(seed=42))

    complete_case = service.get_complete_case("CASE-0007")
    assert complete_case is not None
    assert complete_case.recovery_case.id == "CASE-0007"
    assert complete_case.booking.id == complete_case.recovery_case.booking_id
    assert len(complete_case.passengers) == 3
    assert len(complete_case.flights) == 2

    replacement_counts = service.seed(generate_dataset(seed=99), replace=True)
    assert replacement_counts == counts

    assert service.reset().is_empty()
    assert service.counts().is_empty()


@pytest.mark.integration
def test_unit_of_work_rolls_back_an_interrupted_seed(
    clean_session_factory: SessionFactory,
) -> None:
    unit_of_work_factory = partial(
        SqlAlchemyRecoveryDataUnitOfWork,
        clean_session_factory,
    )

    with (
        pytest.raises(RuntimeError, match="simulated interruption"),
        unit_of_work_factory() as unit_of_work,
    ):
        unit_of_work.repository.add_dataset(generate_dataset(seed=42))
        raise RuntimeError("simulated interruption")

    service = RecoveryDataService(unit_of_work_factory, Environment.TEST)
    assert service.counts().is_empty()

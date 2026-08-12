"""Tests for the itinerary-validation application service."""

from types import TracebackType
from typing import cast

from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.application.services import RecoveryDataUnitOfWorkFactory
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.models import Flight, FlightId


class FlightRepositoryStub:
    def __init__(self, flights: tuple[Flight, ...]) -> None:
        self.flights = flights
        self.requested_ids: list[tuple[FlightId, ...]] = []

    def get_flights_by_ids(
        self,
        flight_ids: tuple[FlightId, ...],
    ) -> tuple[Flight, ...]:
        self.requested_ids.append(flight_ids)
        return self.flights


class UnitOfWorkStub:
    def __init__(self, repository: FlightRepositoryStub) -> None:
        self.repository = repository

    def __enter__(self) -> "UnitOfWorkStub":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def test_service_validates_repository_facts_in_requested_order() -> None:
    flights = generate_dataset(seed=42).flights[:2]
    repository = FlightRepositoryStub(tuple(reversed(flights)))
    factory = cast(RecoveryDataUnitOfWorkFactory, lambda: UnitOfWorkStub(repository))

    result = OperationalQueryService(factory).validate_itinerary(
        ("FLT-NV101", "FLT-NV102")
    )

    assert result.valid is True
    assert result.flight_ids == ("FLT-NV101", "FLT-NV102")
    assert repository.requested_ids == [("FLT-NV101", "FLT-NV102")]


def test_service_returns_structured_missing_flight_rule() -> None:
    repository = FlightRepositoryStub(())
    factory = cast(RecoveryDataUnitOfWorkFactory, lambda: UnitOfWorkStub(repository))

    result = OperationalQueryService(factory).validate_itinerary(("FLT-MISSING",))

    assert result.valid is False
    assert result.rules[0].rule.value == "flights_exist"
    assert result.rules[0].status.value == "failed"

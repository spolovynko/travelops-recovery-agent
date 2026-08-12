"""Tests for deterministic alternative-itinerary candidate generation."""

from datetime import UTC, datetime
from types import TracebackType
from typing import cast

from travelops_recovery_agent.application.query_models import (
    AlternativeSearchRequirements,
)
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.application.services import RecoveryDataUnitOfWorkFactory
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.models import Flight


class FlightWindowRepositoryStub:
    def __init__(self, flights: tuple[Flight, ...]) -> None:
        self.flights = flights
        self.windows: list[tuple[datetime, datetime]] = []

    def list_flights_in_window(
        self,
        earliest_departure: datetime,
        latest_arrival: datetime,
    ) -> tuple[Flight, ...]:
        self.windows.append((earliest_departure, latest_arrival))
        return tuple(
            flight
            for flight in self.flights
            if flight.scheduled_departure >= earliest_departure
            and flight.scheduled_arrival <= latest_arrival
        )


class FlightWindowUnitOfWorkStub:
    def __init__(self, repository: FlightWindowRepositoryStub) -> None:
        self.repository = repository

    def __enter__(self) -> "FlightWindowUnitOfWorkStub":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def requirements(*, max_connections: int = 1) -> AlternativeSearchRequirements:
    return AlternativeSearchRequirements(
        origin="ZRA",
        destination="XLC",
        earliest_departure=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        latest_arrival=datetime(2026, 1, 15, 18, 0, tzinfo=UTC),
        max_connections=max_connections,
    )


def test_search_builds_one_deterministic_connected_candidate() -> None:
    dataset = generate_dataset(seed=42)
    repository = FlightWindowRepositoryStub(dataset.flights)
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: FlightWindowUnitOfWorkStub(repository),
    )
    service = OperationalQueryService(factory)

    first = service.search_alternative_itineraries(requirements())
    second = service.search_alternative_itineraries(requirements())

    assert first == second
    assert [[flight.id for flight in item.flights] for item in first] == [
        ["FLT-NV101", "FLT-NV102"]
    ]
    assert first[0].connection_minutes == (90,)


def test_search_respects_max_connections_without_inventing_routes() -> None:
    repository = FlightWindowRepositoryStub(generate_dataset(seed=42).flights)
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: FlightWindowUnitOfWorkStub(repository),
    )

    result = OperationalQueryService(factory).search_alternative_itineraries(
        requirements(max_connections=0)
    )

    assert result == ()

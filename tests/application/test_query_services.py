"""Tests for read-only operational application queries."""

from types import TracebackType
from typing import cast

from travelops_recovery_agent.application.models import CompleteRecoveryCase
from travelops_recovery_agent.application.query_models import (
    CompleteBooking,
    FlightWithDisruptions,
    OperationalFlightStatus,
    ResolvedDisruptionPolicy,
)
from travelops_recovery_agent.application.query_services import OperationalQueryService
from travelops_recovery_agent.application.services import RecoveryDataUnitOfWorkFactory
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.models import (
    BookingId,
    DisruptionId,
    FlightId,
    RecoveryCaseId,
)


def complete_booking(case_index: int = 6) -> CompleteBooking:
    dataset = generate_dataset(seed=42)
    recovery_case = dataset.recovery_cases[case_index]
    booking = next(
        item for item in dataset.bookings if item.id == recovery_case.booking_id
    )
    passengers_by_id = {passenger.id: passenger for passenger in dataset.passengers}
    flights_by_id = {flight.id: flight for flight in dataset.flights}
    return CompleteBooking(
        booking=booking,
        passengers=tuple(
            passengers_by_id[passenger_id] for passenger_id in booking.passenger_ids
        ),
        flights=tuple(flights_by_id[segment.flight_id] for segment in booking.segments),
    )


def complete_case(case_index: int) -> CompleteRecoveryCase:
    dataset = generate_dataset(seed=42)
    recovery_case = dataset.recovery_cases[case_index]
    booking = next(
        item for item in dataset.bookings if item.id == recovery_case.booking_id
    )
    disruption = next(
        item for item in dataset.disruptions if item.id == recovery_case.disruption_id
    )
    policy = next(
        item for item in dataset.policies if item.id == recovery_case.policy_id
    )
    passengers_by_id = {passenger.id: passenger for passenger in dataset.passengers}
    flights_by_id = {flight.id: flight for flight in dataset.flights}
    return CompleteRecoveryCase(
        recovery_case=recovery_case,
        booking=booking,
        passengers=tuple(
            passengers_by_id[passenger_id] for passenger_id in booking.passenger_ids
        ),
        flights=tuple(flights_by_id[segment.flight_id] for segment in booking.segments),
        disruption=disruption,
        policy=policy,
    )


class BookingQueryRepositoryStub:
    def __init__(self, result: CompleteBooking | None) -> None:
        self.result = result
        self.requested_booking_ids: list[BookingId] = []

    def get_complete_booking(self, booking_id: BookingId) -> CompleteBooking | None:
        self.requested_booking_ids.append(booking_id)
        return self.result


class BookingQueryUnitOfWorkStub:
    def __init__(self, repository: BookingQueryRepositoryStub) -> None:
        self.repository = repository
        self.entered = False
        self.exited = False

    def __enter__(self) -> "BookingQueryUnitOfWorkStub":
        self.entered = True
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.exited = True


class FlightQueryRepositoryStub(BookingQueryRepositoryStub):
    def __init__(self, result: FlightWithDisruptions | None) -> None:
        super().__init__(None)
        self.flight_result = result
        self.requested_flight_ids: list[FlightId] = []

    def get_flight_with_disruptions(
        self,
        flight_id: FlightId,
    ) -> FlightWithDisruptions | None:
        self.requested_flight_ids.append(flight_id)
        return self.flight_result


class RecoveryCaseQueryRepositoryStub(BookingQueryRepositoryStub):
    def __init__(self, results: tuple[CompleteRecoveryCase, ...]) -> None:
        super().__init__(None)
        self.results = results
        self.list_calls = 0

    def list_complete_cases(self) -> tuple[CompleteRecoveryCase, ...]:
        self.list_calls += 1
        return self.results


def flight_with_disruptions(
    case_index: int,
    *,
    include_disruption: bool = True,
) -> FlightWithDisruptions:
    dataset = generate_dataset(seed=42)
    recovery_case = dataset.recovery_cases[case_index]
    disruption = next(
        item for item in dataset.disruptions if item.id == recovery_case.disruption_id
    )
    flight = next(
        item for item in dataset.flights if item.id == disruption.affected_flight_id
    )
    return FlightWithDisruptions(
        flight=flight,
        disruptions=(disruption,) if include_disruption else (),
    )


def resolved_policy(case_index: int = 0) -> ResolvedDisruptionPolicy:
    dataset = generate_dataset(seed=42)
    recovery_case = dataset.recovery_cases[case_index]
    disruption = next(
        item for item in dataset.disruptions if item.id == recovery_case.disruption_id
    )
    policy = next(
        item for item in dataset.policies if item.id == recovery_case.policy_id
    )
    return ResolvedDisruptionPolicy(
        recovery_case=recovery_case,
        disruption=disruption,
        policy=policy,
    )


class PolicyQueryRepositoryStub(BookingQueryRepositoryStub):
    def __init__(self, result: ResolvedDisruptionPolicy | None) -> None:
        super().__init__(None)
        self.policy_result = result
        self.requested_case_ids: list[RecoveryCaseId] = []
        self.requested_disruption_ids: list[DisruptionId] = []

    def get_disruption_policy_for_case(
        self,
        case_id: RecoveryCaseId,
    ) -> ResolvedDisruptionPolicy | None:
        self.requested_case_ids.append(case_id)
        return self.policy_result

    def get_disruption_policy_for_disruption(
        self,
        disruption_id: DisruptionId,
    ) -> ResolvedDisruptionPolicy | None:
        self.requested_disruption_ids.append(disruption_id)
        return self.policy_result


def test_get_booking_delegates_one_narrow_read_to_the_repository() -> None:
    expected = complete_booking()
    repository = BookingQueryRepositoryStub(expected)
    unit_of_work = BookingQueryUnitOfWorkStub(repository)
    factory = cast(RecoveryDataUnitOfWorkFactory, lambda: unit_of_work)
    service = OperationalQueryService(factory)

    result = service.get_booking("BKG-0007")

    assert result == expected
    assert repository.requested_booking_ids == ["BKG-0007"]
    assert unit_of_work.entered is True
    assert unit_of_work.exited is True


def test_get_booking_preserves_a_missing_result() -> None:
    repository = BookingQueryRepositoryStub(None)
    unit_of_work = BookingQueryUnitOfWorkStub(repository)
    factory = cast(RecoveryDataUnitOfWorkFactory, lambda: unit_of_work)
    service = OperationalQueryService(factory)

    assert service.get_booking("BKG-9999") is None
    assert repository.requested_booking_ids == ["BKG-9999"]


def test_list_recovery_cases_builds_ordered_minimized_queue_facts() -> None:
    stored_cases = (
        complete_case(case_index=0),
        complete_case(case_index=3),
        complete_case(case_index=9),
    )
    repository = RecoveryCaseQueryRepositoryStub(stored_cases)
    unit_of_work = BookingQueryUnitOfWorkStub(repository)
    factory = cast(RecoveryDataUnitOfWorkFactory, lambda: unit_of_work)

    result = OperationalQueryService(factory).list_recovery_cases()

    assert [item.recovery_case.id for item in result] == [
        "CASE-0001",
        "CASE-0004",
        "CASE-0010",
    ]
    assert [item.passenger_count for item in result] == [1, 1, 2]
    assert [item.affected_flight_status.status for item in result] == [
        OperationalFlightStatus.DELAYED,
        OperationalFlightStatus.CANCELLED,
        OperationalFlightStatus.SCHEDULED,
    ]
    assert result[0].affected_flight_status.delay_minutes == 30
    assert result[1].affected_flight_status.cancellation_reason == (
        "Synthetic aircraft availability issue"
    )
    assert result[2].disruption.details.type.value == "missed_connection"
    assert repository.list_calls == 1
    assert unit_of_work.entered is True
    assert unit_of_work.exited is True


def test_list_recovery_cases_preserves_an_empty_queue() -> None:
    repository = RecoveryCaseQueryRepositoryStub(())
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: BookingQueryUnitOfWorkStub(repository),
    )

    assert OperationalQueryService(factory).list_recovery_cases() == ()
    assert repository.list_calls == 1


def test_get_flight_status_derives_delay_from_stored_disruption_data() -> None:
    repository = FlightQueryRepositoryStub(flight_with_disruptions(case_index=0))
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: BookingQueryUnitOfWorkStub(repository),
    )

    result = OperationalQueryService(factory).get_flight_status("FLT-NV101")

    assert result is not None
    assert result.status is OperationalFlightStatus.DELAYED
    assert result.delay_minutes == 30
    assert result.cancellation_reason is None
    assert [item.id for item in result.related_disruptions] == ["DIS-0001"]
    assert repository.requested_flight_ids == ["FLT-NV101"]


def test_get_flight_status_derives_cancellation_from_stored_data() -> None:
    repository = FlightQueryRepositoryStub(flight_with_disruptions(case_index=3))
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: BookingQueryUnitOfWorkStub(repository),
    )

    result = OperationalQueryService(factory).get_flight_status("FLT-NV107")

    assert result is not None
    assert result.status is OperationalFlightStatus.CANCELLED
    assert result.delay_minutes is None
    assert result.cancellation_reason == "Synthetic aircraft availability issue"


def test_get_flight_status_keeps_missed_connection_as_related_evidence() -> None:
    repository = FlightQueryRepositoryStub(flight_with_disruptions(case_index=2))
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: BookingQueryUnitOfWorkStub(repository),
    )

    result = OperationalQueryService(factory).get_flight_status("FLT-NV106")

    assert result is not None
    assert result.status is OperationalFlightStatus.SCHEDULED
    assert result.delay_minutes is None
    assert result.cancellation_reason is None
    assert result.related_disruptions[0].details.type.value == "missed_connection"


def test_get_flight_status_returns_scheduled_without_disruptions() -> None:
    repository = FlightQueryRepositoryStub(
        flight_with_disruptions(case_index=0, include_disruption=False)
    )
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: BookingQueryUnitOfWorkStub(repository),
    )

    result = OperationalQueryService(factory).get_flight_status("FLT-NV101")

    assert result is not None
    assert result.status is OperationalFlightStatus.SCHEDULED
    assert result.related_disruptions == ()


def test_get_flight_status_preserves_a_missing_result() -> None:
    repository = FlightQueryRepositoryStub(None)
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: BookingQueryUnitOfWorkStub(repository),
    )

    assert OperationalQueryService(factory).get_flight_status("FLT-NV999") is None
    assert repository.requested_flight_ids == ["FLT-NV999"]


def test_get_disruption_policy_resolves_by_recovery_case() -> None:
    repository = PolicyQueryRepositoryStub(resolved_policy())
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: BookingQueryUnitOfWorkStub(repository),
    )

    result = OperationalQueryService(factory).get_disruption_policy_for_case(
        "CASE-0001"
    )

    assert result == resolved_policy()
    assert repository.requested_case_ids == ["CASE-0001"]
    assert repository.requested_disruption_ids == []


def test_get_disruption_policy_resolves_by_disruption() -> None:
    repository = PolicyQueryRepositoryStub(resolved_policy())
    factory = cast(
        RecoveryDataUnitOfWorkFactory,
        lambda: BookingQueryUnitOfWorkStub(repository),
    )

    result = OperationalQueryService(factory).get_disruption_policy_for_disruption(
        "DIS-0001"
    )

    assert result == resolved_policy()
    assert repository.requested_case_ids == []
    assert repository.requested_disruption_ids == ["DIS-0001"]

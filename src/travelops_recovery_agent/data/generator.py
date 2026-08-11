"""Deterministic generation of fictional airline recovery data."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import Random
from typing import Literal

from travelops_recovery_agent.data.dataset import (
    DATASET_SCHEMA_VERSION,
    DatasetMetadata,
    SyntheticDataset,
)
from travelops_recovery_agent.domain.models import (
    Booking,
    CancelledFlightDetails,
    DelayedFlightDetails,
    Disruption,
    DisruptionPolicy,
    DisruptionType,
    Flight,
    ItinerarySegment,
    MissedConnectionDetails,
    Passenger,
    RecoveryCase,
)

GENERATOR_VERSION = "1.0"
REFERENCE_TIME = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)

_GIVEN_NAMES = ("Mina", "Tariq", "Elara", "Jonas", "Noor")
_FAMILY_NAMES = ("Vale", "Orin", "Solis", "Maren", "Kade")
_AIRPORT_CODES = (
    "ZRA",
    "QVB",
    "XLC",
    "MZN",
    "QTR",
    "VEX",
    "KXA",
    "ZUL",
    "QOR",
    "BEX",
    "YRA",
    "XEN",
)


@dataclass(frozen=True)
class ScenarioBlueprint:
    title: str
    disruption_type: DisruptionType
    affected_sequence: Literal[1, 2]
    passenger_count: int = 1
    delay_minutes: int | None = None
    cancellation_reason: str | None = None


_SCENARIOS = (
    ScenarioBlueprint(
        title="Short delay on originating flight",
        disruption_type=DisruptionType.DELAYED_FLIGHT,
        affected_sequence=1,
        delay_minutes=30,
    ),
    ScenarioBlueprint(
        title="Long delay on connecting flight",
        disruption_type=DisruptionType.DELAYED_FLIGHT,
        affected_sequence=2,
        delay_minutes=90,
    ),
    ScenarioBlueprint(
        title="Missed connection after inbound delay",
        disruption_type=DisruptionType.MISSED_CONNECTION,
        affected_sequence=2,
    ),
    ScenarioBlueprint(
        title="Cancelled originating flight",
        disruption_type=DisruptionType.CANCELLED_FLIGHT,
        affected_sequence=1,
        cancellation_reason="Synthetic aircraft availability issue",
    ),
    ScenarioBlueprint(
        title="Cancelled connecting flight",
        disruption_type=DisruptionType.CANCELLED_FLIGHT,
        affected_sequence=2,
        cancellation_reason="Synthetic crew availability issue",
    ),
    ScenarioBlueprint(
        title="Cancellation close to departure",
        disruption_type=DisruptionType.CANCELLED_FLIGHT,
        affected_sequence=1,
        cancellation_reason="Synthetic operational restriction",
    ),
    ScenarioBlueprint(
        title="Group booking affected by cancellation",
        disruption_type=DisruptionType.CANCELLED_FLIGHT,
        affected_sequence=2,
        passenger_count=3,
        cancellation_reason="Synthetic maintenance inspection",
    ),
    ScenarioBlueprint(
        title="Missed connection on a two-segment journey",
        disruption_type=DisruptionType.MISSED_CONNECTION,
        affected_sequence=2,
    ),
    ScenarioBlueprint(
        title="Severe delay before onward connection",
        disruption_type=DisruptionType.DELAYED_FLIGHT,
        affected_sequence=1,
        delay_minutes=120,
    ),
    ScenarioBlueprint(
        title="Group booking with a missed connection",
        disruption_type=DisruptionType.MISSED_CONNECTION,
        affected_sequence=2,
        passenger_count=2,
    ),
)


def build_disruption_details(
    scenario: ScenarioBlueprint,
    flights: tuple[Flight, Flight],
) -> DelayedFlightDetails | CancelledFlightDetails | MissedConnectionDetails:
    if scenario.disruption_type is DisruptionType.DELAYED_FLIGHT:
        if scenario.delay_minutes is None:
            raise ValueError("delayed scenario requires delay minutes")

        return DelayedFlightDetails(delay_minutes=scenario.delay_minutes)

    if scenario.disruption_type is DisruptionType.CANCELLED_FLIGHT:
        if scenario.cancellation_reason is None:
            raise ValueError("cancelled scenario requires a cancellation reason")

        return CancelledFlightDetails(reason=scenario.cancellation_reason)

    return MissedConnectionDetails(
        arriving_flight_id=flights[0].id,
        missed_flight_id=flights[1].id,
    )


def generate_dataset(seed: int) -> SyntheticDataset:
    random_generator = Random(seed)

    passengers: list[Passenger] = []
    flights: list[Flight] = []
    bookings: list[Booking] = []
    disruptions: list[Disruption] = []
    recovery_cases: list[RecoveryCase] = []

    passenger_number = 1

    policy = DisruptionPolicy(
        id="POL-STANDARD",
        name="Synthetic standard recovery",
        summary="Permit recovery after supported fictional disruptions.",
        applicable_types=(
            DisruptionType.DELAYED_FLIGHT,
            DisruptionType.CANCELLED_FLIGHT,
            DisruptionType.MISSED_CONNECTION,
        ),
        rebooking_window_hours=24,
        allows_next_day=True,
    )

    for case_number, scenario in enumerate(_SCENARIOS, start=1):
        case_passengers: list[Passenger] = []

        for _ in range(scenario.passenger_count):
            passenger = Passenger(
                id=f"PAX-{passenger_number:04d}",
                given_name=random_generator.choice(_GIVEN_NAMES),
                family_name=random_generator.choice(_FAMILY_NAMES),
            )
            passengers.append(passenger)
            case_passengers.append(passenger)
            passenger_number += 1

        route_start = case_number - 1
        origin = _AIRPORT_CODES[route_start]
        connection = _AIRPORT_CODES[route_start + 1]
        destination = _AIRPORT_CODES[route_start + 2]

        first_number = 99 + (case_number * 2)
        second_number = first_number + 1
        first_departure = REFERENCE_TIME + timedelta(
            days=case_number - 1,
            hours=4,
        )

        first_flight = Flight(
            id=f"FLT-NV{first_number}",
            carrier_code="NV",
            flight_number=str(first_number),
            origin=origin,
            destination=connection,
            scheduled_departure=first_departure,
            scheduled_arrival=first_departure + timedelta(hours=2),
        )
        second_departure = first_flight.scheduled_arrival + timedelta(minutes=90)
        second_flight = Flight(
            id=f"FLT-NV{second_number}",
            carrier_code="NV",
            flight_number=str(second_number),
            origin=connection,
            destination=destination,
            scheduled_departure=second_departure,
            scheduled_arrival=second_departure + timedelta(hours=2),
        )
        case_flights = (first_flight, second_flight)
        flights.extend(case_flights)

        first_segment = ItinerarySegment(
            id=f"SEG-{case_number:03d}1",
            flight_id=first_flight.id,
            sequence=1,
        )
        second_segment = ItinerarySegment(
            id=f"SEG-{case_number:03d}2",
            flight_id=second_flight.id,
            sequence=2,
        )
        case_segments = (first_segment, second_segment)

        booking = Booking(
            id=f"BKG-{case_number:04d}",
            passenger_ids=tuple(passenger.id for passenger in case_passengers),
            segments=case_segments,
        )
        bookings.append(booking)

        affected_segment = case_segments[scenario.affected_sequence - 1]
        affected_flight = case_flights[scenario.affected_sequence - 1]
        disruption = Disruption(
            id=f"DIS-{case_number:04d}",
            affected_flight_id=affected_flight.id,
            affected_segment_id=affected_segment.id,
            occurred_at=(affected_flight.scheduled_departure - timedelta(hours=1)),
            details=build_disruption_details(
                scenario,
                case_flights,
            ),
        )
        disruptions.append(disruption)

        recovery_cases.append(
            RecoveryCase(
                id=f"CASE-{case_number:04d}",
                title=scenario.title,
                booking_id=booking.id,
                disruption_id=disruption.id,
                policy_id=policy.id,
            )
        )

    metadata = DatasetMetadata(
        schema_version=DATASET_SCHEMA_VERSION,
        generator_name="travelops-recovery-agent",
        generator_version=GENERATOR_VERSION,
        seed=seed,
        generated_at=REFERENCE_TIME + timedelta(seconds=seed % 86_400),
        provenance=(
            "Generated deterministically from fictional TravelOps source data."
        ),
    )

    return SyntheticDataset(
        metadata=metadata,
        passengers=tuple(passengers),
        flights=tuple(flights),
        bookings=tuple(bookings),
        disruptions=tuple(disruptions),
        policies=(policy,),
        recovery_cases=tuple(recovery_cases),
    )

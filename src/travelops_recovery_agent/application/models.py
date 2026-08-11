"""Application-level persistence results."""

from dataclasses import dataclass

from travelops_recovery_agent.domain.models import (
    Booking,
    Disruption,
    DisruptionPolicy,
    Flight,
    Passenger,
    RecoveryCase,
)


@dataclass(frozen=True)
class PersistenceRecordCounts:
    passengers: int
    flights: int
    bookings: int
    booking_passengers: int
    itinerary_segments: int
    disruptions: int
    disruption_policies: int
    disruption_policy_types: int
    recovery_cases: int

    def is_empty(self) -> bool:
        return all(
            count == 0
            for count in (
                self.passengers,
                self.flights,
                self.bookings,
                self.booking_passengers,
                self.itinerary_segments,
                self.disruptions,
                self.disruption_policies,
                self.disruption_policy_types,
                self.recovery_cases,
            )
        )


@dataclass(frozen=True)
class CompleteRecoveryCase:
    recovery_case: RecoveryCase
    booking: Booking
    passengers: tuple[Passenger, ...]
    flights: tuple[Flight, ...]
    disruption: Disruption
    policy: DisruptionPolicy

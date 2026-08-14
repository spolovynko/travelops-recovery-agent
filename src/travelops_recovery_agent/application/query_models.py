"""Read-only application query results."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from travelops_recovery_agent.domain.itinerary_validation import (
    ItineraryRuleResult,
)
from travelops_recovery_agent.domain.models import (
    Booking,
    Disruption,
    DisruptionPolicy,
    Flight,
    Passenger,
    RecoveryCase,
)


@dataclass(frozen=True)
class CompleteBooking:
    """Complete domain booking data required by operational queries."""

    booking: Booking
    passengers: tuple[Passenger, ...]
    flights: tuple[Flight, ...]


class OperationalFlightStatus(StrEnum):
    """Deterministic flight states supported by synthetic data."""

    SCHEDULED = "scheduled"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class FlightWithDisruptions:
    """Stored flight and ordered related disruption evidence."""

    flight: Flight
    disruptions: tuple[Disruption, ...]


@dataclass(frozen=True)
class FlightStatus:
    """Application-owned deterministic operational flight result."""

    flight: Flight
    status: OperationalFlightStatus
    delay_minutes: int | None
    cancellation_reason: str | None
    related_disruptions: tuple[Disruption, ...]


@dataclass(frozen=True)
class RecoveryCaseQueueItem:
    """Application-owned facts required by one disruption queue entry."""

    recovery_case: RecoveryCase
    booking: Booking
    passenger_count: int
    itinerary: tuple[Flight, ...]
    disruption: Disruption
    affected_flight_status: FlightStatus


@dataclass(frozen=True)
class ResolvedDisruptionPolicy:
    """Recovery case, disruption, and applicable structured policy."""

    recovery_case: RecoveryCase
    disruption: Disruption
    policy: DisruptionPolicy


@dataclass(frozen=True)
class AlternativeItinerary:
    """Deterministic direct or one-connection flight candidate."""

    flights: tuple[Flight, ...]
    connection_minutes: tuple[int, ...]


@dataclass(frozen=True)
class AlternativeSearchRequirements:
    """Application-owned requirements for deterministic candidate generation."""

    origin: str
    destination: str
    earliest_departure: datetime
    latest_arrival: datetime
    max_connections: int


@dataclass(frozen=True)
class ItineraryValidationResult:
    """Application result for deterministic validation of stored flights."""

    flight_ids: tuple[str, ...]
    valid: bool
    rules: tuple[ItineraryRuleResult, ...]


@dataclass(frozen=True)
class AvailabilityEvidence:
    """Repository-backed synthetic seat evidence for one flight."""

    flight_id: str
    available_seats: int
    observed_at: datetime
    source: str


@dataclass(frozen=True)
class TicketRuleEvidence:
    """Repository-backed synthetic ticket constraints for one booking."""

    booking_id: str
    rebooking_allowed: bool
    allowed_carrier_code: str
    max_connections: int
    observed_at: datetime
    source: str

"""Repository interfaces owned by the application layer."""

from datetime import datetime
from typing import Protocol

from travelops_recovery_agent.application.models import (
    CompleteRecoveryCase,
    PersistenceRecordCounts,
)
from travelops_recovery_agent.application.query_models import (
    CompleteBooking,
    FlightWithDisruptions,
    ResolvedDisruptionPolicy,
)
from travelops_recovery_agent.data.dataset import SyntheticDataset
from travelops_recovery_agent.domain.models import (
    BookingId,
    DisruptionId,
    Flight,
    FlightId,
    RecoveryCaseId,
)


class RecoveryDataRepository(Protocol):
    """Domain-oriented persistence operations required by Phase 3."""

    def counts(self) -> PersistenceRecordCounts:
        """Return counts for every managed persistence table."""
        ...

    def add_dataset(self, dataset: SyntheticDataset) -> None:
        """Add one already validated synthetic dataset."""
        ...

    def get_complete_case(
        self,
        case_id: RecoveryCaseId,
    ) -> CompleteRecoveryCase | None:
        """Retrieve one complete domain-oriented recovery case."""
        ...

    def clear(self) -> None:
        """Remove all managed records inside the caller's transaction."""
        ...

    def get_complete_booking(
        self,
        booking_id: BookingId,
    ) -> CompleteBooking | None:
        """Retrieve one booking with its passengers and ordered flights."""
        ...

    def get_flight_with_disruptions(
        self,
        flight_id: FlightId,
    ) -> FlightWithDisruptions | None:
        """Retrieve one flight and its ordered disruption evidence."""
        ...

    def get_disruption_policy_for_case(
        self,
        case_id: RecoveryCaseId,
    ) -> ResolvedDisruptionPolicy | None:
        """Resolve one policy through a recovery case."""
        ...

    def get_disruption_policy_for_disruption(
        self,
        disruption_id: DisruptionId,
    ) -> ResolvedDisruptionPolicy | None:
        """Resolve one policy through a disruption."""
        ...

    def list_flights_in_window(
        self,
        earliest_departure: datetime,
        latest_arrival: datetime,
    ) -> tuple[Flight, ...]:
        """List scheduled flights fully contained in one explicit time window."""
        ...

    def get_flights_by_ids(
        self,
        flight_ids: tuple[FlightId, ...],
    ) -> tuple[Flight, ...]:
        """Retrieve only stored flights matching explicit stable identifiers."""
        ...

    def list_complete_cases(self) -> tuple[CompleteRecoveryCase, ...]:
        """List complete recovery cases in stable identifier order."""
        ...

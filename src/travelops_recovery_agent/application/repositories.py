"""Repository interfaces owned by the application layer."""

from typing import Protocol

from travelops_recovery_agent.application.models import (
    CompleteRecoveryCase,
    PersistenceRecordCounts,
)
from travelops_recovery_agent.data.dataset import SyntheticDataset
from travelops_recovery_agent.domain.models import RecoveryCaseId


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

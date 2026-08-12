"""Contract tests for browser-oriented recovery API models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.api.recovery_schemas import (
    RecoveryCaseQueueItemView,
    RecoveryCaseQueueView,
    RecoveryCaseRouteView,
)
from travelops_recovery_agent.application.query_models import (
    OperationalFlightStatus,
)
from travelops_recovery_agent.domain.models import DisruptionType


def queue_item() -> RecoveryCaseQueueItemView:
    return RecoveryCaseQueueItemView(
        case_id="CASE-0001",
        title="Short delay on originating flight",
        booking_id="BKG-0001",
        route=RecoveryCaseRouteView(origin="ZRA", destination="XLC"),
        passenger_count=1,
        disruption_type=DisruptionType.DELAYED_FLIGHT,
        affected_flight_id="FLT-NV101",
        occurred_at=datetime(2026, 1, 15, 11, 0, tzinfo=UTC),
        operational_status=OperationalFlightStatus.DELAYED,
        delay_minutes=30,
        cancellation_reason=None,
        journey_departure=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        journey_arrival=datetime(2026, 1, 15, 17, 30, tzinfo=UTC),
    )


def test_queue_view_serializes_only_minimized_browser_facts() -> None:
    payload = RecoveryCaseQueueView(cases=(queue_item(),)).model_dump(mode="json")

    assert payload == {
        "cases": [
            {
                "case_id": "CASE-0001",
                "title": "Short delay on originating flight",
                "booking_id": "BKG-0001",
                "route": {"origin": "ZRA", "destination": "XLC"},
                "passenger_count": 1,
                "disruption_type": "delayed_flight",
                "affected_flight_id": "FLT-NV101",
                "occurred_at": "2026-01-15T11:00:00Z",
                "operational_status": "delayed",
                "delay_minutes": 30,
                "cancellation_reason": None,
                "journey_departure": "2026-01-15T12:00:00Z",
                "journey_arrival": "2026-01-15T17:30:00Z",
            }
        ]
    }
    serialized = RecoveryCaseQueueView(cases=(queue_item(),)).model_dump_json()
    assert "given_name" not in serialized
    assert "family_name" not in serialized
    assert "database" not in serialized.lower()


def test_queue_view_accepts_an_empty_case_collection() -> None:
    assert RecoveryCaseQueueView(cases=()).model_dump(mode="json") == {"cases": []}


def test_queue_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="passenger_names"):
        RecoveryCaseQueueItemView.model_validate(
            {
                **queue_item().model_dump(),
                "passenger_names": ["Not part of the browser contract"],
            }
        )

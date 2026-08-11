"""Versioned container for synthetic airline data."""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from travelops_recovery_agent.domain.models import (
    Booking,
    Disruption,
    DisruptionPolicy,
    Flight,
    MissedConnectionDetails,
    Passenger,
    RecoveryCase,
    validate_itinerary,
)

DATASET_SCHEMA_VERSION: Literal["1.0"] = "1.0"


def require_unique_identifiers(
    label: str,
    identifiers: Iterable[str],
) -> None:
    seen: set[str] = set()

    for identifier in identifiers:
        if identifier in seen:
            raise ValueError(f"duplicate {label} identifier: {identifier}")
        seen.add(identifier)


class DatasetMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    generator_name: Literal["travelops-recovery-agent"]
    generator_version: str
    seed: int
    generated_at: datetime
    provenance: str

    @field_validator("generator_version", "provenance")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value


class SyntheticDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: DatasetMetadata
    passengers: tuple[Passenger, ...]
    flights: tuple[Flight, ...]
    bookings: tuple[Booking, ...]
    disruptions: tuple[Disruption, ...]
    policies: tuple[DisruptionPolicy, ...]
    recovery_cases: tuple[RecoveryCase, ...]

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> Self:
        require_unique_identifiers(
            "passenger",
            (passenger.id for passenger in self.passengers),
        )
        require_unique_identifiers(
            "flight",
            (flight.id for flight in self.flights),
        )
        require_unique_identifiers(
            "booking",
            (booking.id for booking in self.bookings),
        )
        require_unique_identifiers(
            "segment",
            (segment.id for booking in self.bookings for segment in booking.segments),
        )
        require_unique_identifiers(
            "disruption",
            (disruption.id for disruption in self.disruptions),
        )
        require_unique_identifiers(
            "policy",
            (policy.id for policy in self.policies),
        )
        require_unique_identifiers(
            "recovery case",
            (case.id for case in self.recovery_cases),
        )

        return self

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        passengers_by_id = {passenger.id: passenger for passenger in self.passengers}
        flights_by_id = {flight.id: flight for flight in self.flights}
        bookings_by_id = {booking.id: booking for booking in self.bookings}
        disruptions_by_id = {
            disruption.id: disruption for disruption in self.disruptions
        }
        policies_by_id = {policy.id: policy for policy in self.policies}
        segments_by_id = {
            segment.id: (
                booking.id,
                segment.flight_id,
                segment.sequence,
            )
            for booking in self.bookings
            for segment in booking.segments
        }

        for booking in self.bookings:
            for passenger_id in booking.passenger_ids:
                if passenger_id not in passengers_by_id:
                    raise ValueError(
                        f"booking {booking.id} references missing "
                        f"passenger {passenger_id}"
                    )

            validate_itinerary(booking, flights_by_id)

        for disruption in self.disruptions:
            if disruption.affected_flight_id not in flights_by_id:
                raise ValueError(
                    f"disruption {disruption.id} references missing "
                    f"flight {disruption.affected_flight_id}"
                )

            segment_details = segments_by_id.get(disruption.affected_segment_id)
            if segment_details is None:
                raise ValueError(
                    f"disruption {disruption.id} references missing "
                    f"segment {disruption.affected_segment_id}"
                )

            _, segment_flight_id, _ = segment_details
            if segment_flight_id != disruption.affected_flight_id:
                raise ValueError(
                    f"disruption {disruption.id} affected segment "
                    f"{disruption.affected_segment_id} references "
                    f"{segment_flight_id}, not "
                    f"{disruption.affected_flight_id}"
                )

            if isinstance(
                disruption.details,
                MissedConnectionDetails,
            ):
                if disruption.details.arriving_flight_id not in flights_by_id:
                    raise ValueError(
                        f"disruption {disruption.id} references missing "
                        f"arriving flight "
                        f"{disruption.details.arriving_flight_id}"
                    )

                if disruption.details.missed_flight_id not in flights_by_id:
                    raise ValueError(
                        f"disruption {disruption.id} references missing "
                        f"missed flight "
                        f"{disruption.details.missed_flight_id}"
                    )

        for recovery_case in self.recovery_cases:
            resolved_booking = bookings_by_id.get(recovery_case.booking_id)
            if resolved_booking is None:
                raise ValueError(
                    f"recovery case {recovery_case.id} references "
                    f"missing booking {recovery_case.booking_id}"
                )

            resolved_disruption = disruptions_by_id.get(recovery_case.disruption_id)
            if resolved_disruption is None:
                raise ValueError(
                    f"recovery case {recovery_case.id} references "
                    f"missing disruption {recovery_case.disruption_id}"
                )

            resolved_policy = policies_by_id.get(recovery_case.policy_id)
            if resolved_policy is None:
                raise ValueError(
                    f"recovery case {recovery_case.id} references "
                    f"missing policy {recovery_case.policy_id}"
                )

            affected_booking_id, _, affected_sequence = segments_by_id[
                resolved_disruption.affected_segment_id
            ]
            if affected_booking_id != resolved_booking.id:
                raise ValueError(
                    f"recovery case {recovery_case.id} combines booking "
                    f"{resolved_booking.id} with a disruption affecting "
                    f"booking {affected_booking_id}"
                )

            if resolved_disruption.details.type not in resolved_policy.applicable_types:
                raise ValueError(
                    f"policy {resolved_policy.id} does not support disruption type "
                    f"{resolved_disruption.details.type}"
                )

            if isinstance(
                resolved_disruption.details,
                MissedConnectionDetails,
            ):
                arriving_sequences = {
                    segment.flight_id: segment.sequence
                    for segment in resolved_booking.segments
                }
                arriving_sequence = arriving_sequences.get(
                    resolved_disruption.details.arriving_flight_id
                )

                if arriving_sequence is None:
                    raise ValueError(
                        f"missed connection {resolved_disruption.id} arriving flight "
                        f"{resolved_disruption.details.arriving_flight_id} is not in "
                        f"booking {resolved_booking.id}"
                    )

                if affected_sequence != arriving_sequence + 1:
                    raise ValueError(
                        f"missed connection {resolved_disruption.id} must affect "
                        "the segment immediately after the arriving flight"
                    )

        return self


def dataset_to_json_bytes(dataset: SyntheticDataset) -> bytes:
    serialized = dataset.model_dump_json(indent=2)
    return f"{serialized}\n".encode()


def write_dataset(
    dataset: SyntheticDataset,
    path: str | Path,
) -> None:
    Path(path).write_bytes(dataset_to_json_bytes(dataset))


def load_dataset(path: str | Path) -> SyntheticDataset:
    serialized = Path(path).read_bytes()
    return SyntheticDataset.model_validate_json(serialized)

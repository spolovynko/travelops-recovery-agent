"""Tests for the versioned synthetic dataset container."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.data.dataset import (
    DATASET_SCHEMA_VERSION,
    DatasetMetadata,
    SyntheticDataset,
    dataset_to_json_bytes,
    load_dataset,
    write_dataset,
)
from travelops_recovery_agent.data.generator import generate_dataset


def valid_metadata_data() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "generator_name": "travelops-recovery-agent",
        "generator_version": "1.0",
        "seed": 20260811,
        "generated_at": datetime(2026, 1, 15, 8, 0, tzinfo=UTC),
        "provenance": "Deterministic fictional airline data for TravelOps.",
    }


def valid_dataset_data() -> dict[str, object]:
    return {
        "metadata": valid_metadata_data(),
        "passengers": [{"id": "PAX-0001", "given_name": "Mina", "family_name": "Vale"}],
        "flights": [
            {
                "id": "FLT-NV101",
                "carrier_code": "NV",
                "flight_number": "101",
                "origin": "NRV",
                "destination": "VLY",
                "scheduled_departure": datetime(2026, 1, 15, 8, 0, tzinfo=UTC),
                "scheduled_arrival": datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
            },
            {
                "id": "FLT-NV202",
                "carrier_code": "NV",
                "flight_number": "202",
                "origin": "VLY",
                "destination": "SKY",
                "scheduled_departure": datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
                "scheduled_arrival": datetime(2026, 1, 15, 14, 0, tzinfo=UTC),
            },
        ],
        "bookings": [
            {
                "id": "BKG-0001",
                "passenger_ids": ["PAX-0001"],
                "segments": [
                    {
                        "id": "SEG-0001",
                        "flight_id": "FLT-NV101",
                        "sequence": 1,
                    },
                    {
                        "id": "SEG-0002",
                        "flight_id": "FLT-NV202",
                        "sequence": 2,
                    },
                ],
            }
        ],
        "disruptions": [
            {
                "id": "DIS-0001",
                "affected_flight_id": "FLT-NV101",
                "affected_segment_id": "SEG-0001",
                "occurred_at": datetime(2026, 1, 15, 7, 30, tzinfo=UTC),
                "details": {"type": "delayed_flight", "delay_minutes": 45},
            }
        ],
        "policies": [
            {
                "id": "POL-STANDARD",
                "name": "Synthetic standard recovery",
                "summary": "Permit recovery after supported disruptions.",
                "applicable_types": [
                    "delayed_flight",
                    "cancelled_flight",
                    "missed_connection",
                ],
                "rebooking_window_hours": 24,
                "allows_next_day": True,
            }
        ],
        "recovery_cases": [
            {
                "id": "CASE-0001",
                "title": "Synthetic delayed journey",
                "booking_id": "BKG-0001",
                "disruption_id": "DIS-0001",
                "policy_id": "POL-STANDARD",
            }
        ],
    }


def test_metadata_records_version_seed_and_provenance() -> None:
    metadata = DatasetMetadata.model_validate(valid_metadata_data())

    assert metadata.schema_version == DATASET_SCHEMA_VERSION
    assert metadata.seed == 20260811
    assert metadata.provenance.startswith("Deterministic fictional")


def test_metadata_rejects_an_unsupported_schema_version() -> None:
    metadata_data = valid_metadata_data()
    metadata_data["schema_version"] = "2.0"

    with pytest.raises(ValidationError, match="schema_version"):
        DatasetMetadata.model_validate(metadata_data)


def test_metadata_rejects_a_naive_generation_time() -> None:
    metadata_data = valid_metadata_data()
    metadata_data["generated_at"] = datetime(2026, 1, 15, 8, 0)

    with pytest.raises(ValidationError, match="generated_at must be timezone-aware"):
        DatasetMetadata.model_validate(metadata_data)


@pytest.mark.parametrize("field", ["generator_version", "provenance"])
def test_metadata_rejects_blank_required_text(field: str) -> None:
    metadata_data = valid_metadata_data()
    metadata_data[field] = "   "

    with pytest.raises(ValidationError, match="value must not be empty"):
        DatasetMetadata.model_validate(metadata_data)


def test_dataset_accepts_unique_identifiers() -> None:
    dataset = SyntheticDataset.model_validate(valid_dataset_data())

    assert len(dataset.passengers) == 1
    assert len(dataset.flights) == 2
    assert len(dataset.recovery_cases) == 1


@pytest.mark.parametrize(
    ("collection", "label"),
    [
        ("passengers", "passenger"),
        ("flights", "flight"),
        ("bookings", "booking"),
        ("disruptions", "disruption"),
        ("policies", "policy"),
        ("recovery_cases", "recovery case"),
    ],
)
def test_dataset_rejects_duplicate_top_level_identifiers(
    collection: str,
    label: str,
) -> None:
    dataset_data = valid_dataset_data()
    records = cast(list[object], dataset_data[collection])
    records.append(deepcopy(records[0]))

    with pytest.raises(ValidationError, match=f"duplicate {label} identifier"):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_rejects_duplicate_segment_identifiers_across_bookings() -> None:
    dataset_data = valid_dataset_data()
    bookings = cast(list[dict[str, object]], dataset_data["bookings"])
    bookings.append(
        {
            "id": "BKG-0002",
            "passenger_ids": ["PAX-0001"],
            "segments": [
                {
                    "id": "SEG-0001",
                    "flight_id": "FLT-NV202",
                    "sequence": 1,
                }
            ],
        }
    )

    with pytest.raises(ValidationError, match="duplicate segment identifier"):
        SyntheticDataset.model_validate(dataset_data)


def records(
    dataset_data: dict[str, object],
    collection: str,
) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], dataset_data[collection])


def test_dataset_rejects_a_missing_passenger_reference() -> None:
    dataset_data = valid_dataset_data()
    dataset_data["passengers"] = []

    with pytest.raises(
        ValidationError,
        match="booking BKG-0001 references missing passenger PAX-0001",
    ):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_rejects_a_missing_booking_flight_reference() -> None:
    dataset_data = valid_dataset_data()
    records(dataset_data, "flights").pop()

    with pytest.raises(
        ValidationError,
        match="segment SEG-0002 references missing flight FLT-NV202",
    ):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_rejects_a_broken_itinerary() -> None:
    dataset_data = valid_dataset_data()
    records(dataset_data, "flights")[1]["origin"] = "SUN"

    with pytest.raises(
        ValidationError,
        match="itinerary is geographically disconnected",
    ):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_rejects_a_disruption_with_a_missing_flight() -> None:
    dataset_data = valid_dataset_data()
    records(dataset_data, "disruptions")[0]["affected_flight_id"] = "FLT-NV999"

    with pytest.raises(
        ValidationError,
        match="disruption DIS-0001 references missing flight FLT-NV999",
    ):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_rejects_a_disruption_with_a_missing_segment() -> None:
    dataset_data = valid_dataset_data()
    records(dataset_data, "disruptions")[0]["affected_segment_id"] = "SEG-9999"

    with pytest.raises(
        ValidationError,
        match="disruption DIS-0001 references missing segment SEG-9999",
    ):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_rejects_a_disruption_with_a_mismatched_segment() -> None:
    dataset_data = valid_dataset_data()
    records(dataset_data, "disruptions")[0]["affected_flight_id"] = "FLT-NV202"

    with pytest.raises(
        ValidationError,
        match="affected segment SEG-0001 references FLT-NV101, not FLT-NV202",
    ):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_rejects_a_missing_arriving_flight() -> None:
    dataset_data = valid_dataset_data()
    disruption = records(dataset_data, "disruptions")[0]
    disruption["affected_flight_id"] = "FLT-NV202"
    disruption["affected_segment_id"] = "SEG-0002"
    disruption["details"] = {
        "type": "missed_connection",
        "arriving_flight_id": "FLT-NV999",
        "missed_flight_id": "FLT-NV202",
    }

    with pytest.raises(
        ValidationError,
        match="references missing arriving flight FLT-NV999",
    ):
        SyntheticDataset.model_validate(dataset_data)


@pytest.mark.parametrize(
    ("field", "missing_identifier", "expected_message"),
    [
        ("booking_id", "BKG-9999", "references missing booking BKG-9999"),
        (
            "disruption_id",
            "DIS-9999",
            "references missing disruption DIS-9999",
        ),
        ("policy_id", "POL-UNKNOWN", "references missing policy POL-UNKNOWN"),
    ],
)
def test_dataset_rejects_missing_recovery_case_references(
    field: str,
    missing_identifier: str,
    expected_message: str,
) -> None:
    dataset_data = valid_dataset_data()
    records(dataset_data, "recovery_cases")[0][field] = missing_identifier

    with pytest.raises(ValidationError, match=expected_message):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_rejects_a_case_combining_unrelated_booking_and_disruption() -> None:
    dataset_data = valid_dataset_data()
    records(dataset_data, "bookings").append(
        {
            "id": "BKG-0002",
            "passenger_ids": ["PAX-0001"],
            "segments": [
                {
                    "id": "SEG-0003",
                    "flight_id": "FLT-NV202",
                    "sequence": 1,
                }
            ],
        }
    )
    records(dataset_data, "recovery_cases")[0]["booking_id"] = "BKG-0002"

    with pytest.raises(
        ValidationError,
        match="combines booking BKG-0002 with a disruption affecting booking BKG-0001",
    ):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_rejects_a_policy_that_does_not_cover_the_disruption() -> None:
    dataset_data = valid_dataset_data()
    records(dataset_data, "policies")[0]["applicable_types"] = ["cancelled_flight"]

    with pytest.raises(
        ValidationError,
        match="policy POL-STANDARD does not support disruption type delayed_flight",
    ):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_rejects_a_missed_connection_arriving_outside_the_booking() -> None:
    dataset_data = valid_dataset_data()
    records(dataset_data, "flights").append(
        {
            "id": "FLT-NV303",
            "carrier_code": "NV",
            "flight_number": "303",
            "origin": "GLM",
            "destination": "NRV",
            "scheduled_departure": datetime(2026, 1, 15, 5, 0, tzinfo=UTC),
            "scheduled_arrival": datetime(2026, 1, 15, 7, 0, tzinfo=UTC),
        }
    )
    disruption = records(dataset_data, "disruptions")[0]
    disruption["affected_flight_id"] = "FLT-NV202"
    disruption["affected_segment_id"] = "SEG-0002"
    disruption["details"] = {
        "type": "missed_connection",
        "arriving_flight_id": "FLT-NV303",
        "missed_flight_id": "FLT-NV202",
    }

    with pytest.raises(
        ValidationError,
        match="arriving flight FLT-NV303 is not in booking BKG-0001",
    ):
        SyntheticDataset.model_validate(dataset_data)


def test_dataset_accepts_a_coherent_missed_connection() -> None:
    dataset_data = valid_dataset_data()
    disruption = records(dataset_data, "disruptions")[0]
    disruption["affected_flight_id"] = "FLT-NV202"
    disruption["affected_segment_id"] = "SEG-0002"
    disruption["details"] = {
        "type": "missed_connection",
        "arriving_flight_id": "FLT-NV101",
        "missed_flight_id": "FLT-NV202",
    }

    dataset = SyntheticDataset.model_validate(dataset_data)

    assert dataset.disruptions[0].details.type == "missed_connection"


def test_dataset_rejects_a_missed_connection_skipping_a_segment() -> None:
    dataset_data = valid_dataset_data()
    records(dataset_data, "flights").append(
        {
            "id": "FLT-NV303",
            "carrier_code": "NV",
            "flight_number": "303",
            "origin": "SKY",
            "destination": "SUN",
            "scheduled_departure": datetime(2026, 1, 15, 15, 0, tzinfo=UTC),
            "scheduled_arrival": datetime(2026, 1, 15, 16, 0, tzinfo=UTC),
        }
    )
    booking = records(dataset_data, "bookings")[0]
    booking_segments = cast(list[dict[str, object]], booking["segments"])
    booking_segments.append({"id": "SEG-0003", "flight_id": "FLT-NV303", "sequence": 3})
    disruption = records(dataset_data, "disruptions")[0]
    disruption["affected_flight_id"] = "FLT-NV303"
    disruption["affected_segment_id"] = "SEG-0003"
    disruption["details"] = {
        "type": "missed_connection",
        "arriving_flight_id": "FLT-NV101",
        "missed_flight_id": "FLT-NV303",
    }

    with pytest.raises(
        ValidationError,
        match="must affect the segment immediately after the arriving flight",
    ):
        SyntheticDataset.model_validate(dataset_data)


def test_json_serialization_is_utf8_and_ends_with_a_newline() -> None:
    serialized = dataset_to_json_bytes(generate_dataset(seed=42))

    assert serialized.endswith(b"\n")
    assert json.loads(serialized.decode("utf-8"))["metadata"]["seed"] == 42


def test_written_dataset_loads_back_to_the_same_model(tmp_path: Path) -> None:
    original = generate_dataset(seed=42)
    dataset_path = tmp_path / "synthetic-cases.json"

    write_dataset(original, dataset_path)
    loaded = load_dataset(dataset_path)

    assert loaded == original
    assert dataset_path.read_bytes() == dataset_to_json_bytes(original)


def test_loader_rejects_malformed_json(tmp_path: Path) -> None:
    dataset_path = tmp_path / "malformed.json"
    dataset_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValidationError, match="Invalid JSON"):
        load_dataset(dataset_path)


def test_loader_rejects_an_unsupported_serialized_version(tmp_path: Path) -> None:
    payload = generate_dataset(seed=42).model_dump(mode="json")
    metadata = cast(dict[str, object], payload["metadata"])
    metadata["schema_version"] = "2.0"
    dataset_path = tmp_path / "unsupported-version.json"
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError) as error:
        load_dataset(dataset_path)

    assert "metadata.schema_version" in str(error.value)


def test_loader_reports_a_missing_metadata_field_path(tmp_path: Path) -> None:
    payload = generate_dataset(seed=42).model_dump(mode="json")
    metadata = cast(dict[str, object], payload["metadata"])
    del metadata["seed"]
    dataset_path = tmp_path / "missing-seed.json"
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError) as error:
        load_dataset(dataset_path)

    assert "metadata.seed" in str(error.value)


def test_loader_reports_an_invalid_nested_field_path(tmp_path: Path) -> None:
    payload = generate_dataset(seed=42).model_dump(mode="json")
    flights = cast(list[dict[str, object]], payload["flights"])
    flights[0]["scheduled_departure"] = "2026-01-15T12:00:00"
    dataset_path = tmp_path / "naive-flight-time.json"
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError) as error:
        load_dataset(dataset_path)

    assert "flights.0.scheduled_departure" in str(error.value)
    assert "datetime must be timezone-aware" in str(error.value)

"""Tests for foundational SQLAlchemy persistence model metadata."""

from typing import cast

from sqlalchemy import CheckConstraint, DateTime, Table, UniqueConstraint

from travelops_recovery_agent.persistence.models import (
    Base,
    BookingPassengerRecord,
    BookingRecord,
    FlightAvailabilityEvidenceRecord,
    FlightRecord,
    ItinerarySegmentRecord,
    PassengerRecord,
    TicketRuleEvidenceRecord,
)


def model_table(record_type: type[Base]) -> Table:
    return cast(Table, record_type.__table__)


def primary_key_columns(table: Table) -> tuple[str, ...]:
    return tuple(column.name for column in table.primary_key.columns)


def named_unique_constraints(table: Table) -> dict[str | None, tuple[str, ...]]:
    return {
        cast(str | None, constraint.name): tuple(
            column.name for column in constraint.columns
        )
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def named_check_constraints(table: Table) -> set[str | None]:
    return {
        cast(str | None, constraint.name)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def named_indexes(table: Table) -> dict[str | None, tuple[str, ...]]:
    return {
        index.name: tuple(column.name for column in index.columns)
        for index in table.indexes
    }


def test_foundational_tables_are_registered() -> None:
    assert {
        "passengers",
        "flights",
        "bookings",
        "booking_passengers",
        "itinerary_segments",
    } <= set(Base.metadata.tables)


def test_phase_nine_evidence_tables_have_stable_keys_and_checks() -> None:
    availability = model_table(FlightAvailabilityEvidenceRecord)
    ticket = model_table(TicketRuleEvidenceRecord)

    assert primary_key_columns(availability) == ("flight_id",)
    assert primary_key_columns(ticket) == ("booking_id",)
    assert "ck_flight_availability_nonnegative_seats" in named_check_constraints(
        availability
    )
    assert "ck_ticket_rule_connection_range" in named_check_constraints(ticket)


def test_stable_domain_identifiers_are_primary_keys() -> None:
    assert primary_key_columns(model_table(PassengerRecord)) == ("id",)
    assert primary_key_columns(model_table(FlightRecord)) == ("id",)
    assert primary_key_columns(model_table(BookingRecord)) == ("id",)
    assert primary_key_columns(model_table(ItinerarySegmentRecord)) == ("id",)
    assert primary_key_columns(model_table(BookingPassengerRecord)) == (
        "booking_id",
        "passenger_id",
    )


def test_flight_timestamps_are_timezone_aware_and_required() -> None:
    table = model_table(FlightRecord)

    for column_name in ("scheduled_departure", "scheduled_arrival"):
        column = table.c[column_name]
        assert isinstance(column.type, DateTime)
        assert column.type.timezone is True
        assert column.nullable is False


def test_flight_constraints_and_search_index_are_explicit() -> None:
    table = model_table(FlightRecord)

    assert {
        "ck_flights_distinct_airports",
        "ck_flights_arrival_after_departure",
    } <= named_check_constraints(table)
    assert named_unique_constraints(table)["uq_flights_scheduled_service"] == (
        "carrier_code",
        "flight_number",
        "scheduled_departure",
    )
    assert named_indexes(table)["ix_flights_route_departure"] == (
        "origin",
        "destination",
        "scheduled_departure",
    )


def test_booking_passenger_association_has_explicit_foreign_keys() -> None:
    table = model_table(BookingPassengerRecord)
    booking_fk = next(iter(table.c.booking_id.foreign_keys))
    passenger_fk = next(iter(table.c.passenger_id.foreign_keys))

    assert booking_fk.target_fullname == "bookings.id"
    assert booking_fk.ondelete == "CASCADE"
    assert passenger_fk.target_fullname == "passengers.id"
    assert passenger_fk.ondelete == "RESTRICT"
    assert named_indexes(table)["ix_booking_passengers_passenger_id"] == (
        "passenger_id",
    )


def test_itinerary_segment_enforces_booking_order_and_flight_references() -> None:
    table = model_table(ItinerarySegmentRecord)
    booking_fk = next(iter(table.c.booking_id.foreign_keys))
    flight_fk = next(iter(table.c.flight_id.foreign_keys))

    assert booking_fk.target_fullname == "bookings.id"
    assert booking_fk.ondelete == "CASCADE"
    assert flight_fk.target_fullname == "flights.id"
    assert flight_fk.ondelete == "RESTRICT"
    assert named_unique_constraints(table)[
        "uq_itinerary_segments_booking_sequence"
    ] == (
        "booking_id",
        "sequence",
    )
    assert named_unique_constraints(table)["uq_itinerary_segments_booking_flight"] == (
        "booking_id",
        "flight_id",
    )
    assert "ck_itinerary_segments_positive_sequence" in named_check_constraints(table)
    assert named_indexes(table)["ix_itinerary_segments_flight_id"] == ("flight_id",)


def test_orm_relationships_describe_ownership_without_entering_the_domain() -> None:
    assert "booking_links" in PassengerRecord.__mapper__.relationships
    assert "segments" in FlightRecord.__mapper__.relationships
    assert {"passenger_links", "segments"} <= set(
        BookingRecord.__mapper__.relationships.keys()
    )
    assert {"booking", "passenger"} <= set(
        BookingPassengerRecord.__mapper__.relationships.keys()
    )
    assert {"booking", "flight"} <= set(
        ItinerarySegmentRecord.__mapper__.relationships.keys()
    )

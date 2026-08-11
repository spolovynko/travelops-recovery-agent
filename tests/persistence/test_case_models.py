"""Tests for disruption, policy, and recovery-case persistence metadata."""

from typing import cast

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Table,
    UniqueConstraint,
)

from travelops_recovery_agent.persistence.models import (
    Base,
    DisruptionPolicyRecord,
    DisruptionPolicyTypeRecord,
    DisruptionRecord,
    ItinerarySegmentRecord,
    RecoveryCaseRecord,
)


def model_table(record_type: type[Base]) -> Table:
    return cast(Table, record_type.__table__)


def constraint_names(table: Table, kind: type[CheckConstraint]) -> set[str]:
    return {
        cast(str, constraint.name)
        for constraint in table.constraints
        if isinstance(constraint, kind)
    }


def unique_constraints(table: Table) -> dict[str, tuple[str, ...]]:
    return {
        cast(str, constraint.name): tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def index_columns(table: Table) -> dict[str, tuple[str, ...]]:
    return {
        cast(str, index.name): tuple(column.name for column in index.columns)
        for index in table.indexes
    }


def test_case_tables_are_registered_separately_from_domain_models() -> None:
    assert {
        "disruptions",
        "disruption_policies",
        "disruption_policy_types",
        "recovery_cases",
    } <= set(Base.metadata.tables)


def test_disruption_uses_deliberate_typed_detail_columns() -> None:
    table = model_table(DisruptionRecord)

    assert isinstance(table.c.occurred_at.type, DateTime)
    assert table.c.occurred_at.type.timezone is True
    assert table.c.occurred_at.nullable is False
    assert table.c.type.nullable is False

    for optional_detail in (
        "delay_minutes",
        "cancellation_reason",
        "arriving_flight_id",
        "missed_flight_id",
    ):
        assert table.c[optional_detail].nullable is True

    assert {
        "ck_disruptions_supported_type",
        "ck_disruptions_type_specific_details",
    } <= constraint_names(table, CheckConstraint)


def test_disruption_foreign_keys_preserve_segment_and_flight_coherence() -> None:
    table = model_table(DisruptionRecord)
    composite_fk = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_disruptions_affected_segment_flight"
    )

    assert tuple(composite_fk.column_keys) == (
        "affected_segment_id",
        "affected_flight_id",
    )
    assert tuple(element.target_fullname for element in composite_fk.elements) == (
        "itinerary_segments.id",
        "itinerary_segments.flight_id",
    )
    assert composite_fk.ondelete == "RESTRICT"

    assert {
        foreign_key.target_fullname
        for foreign_key in table.c.affected_flight_id.foreign_keys
    } == {"flights.id", "itinerary_segments.flight_id"}
    assert {
        foreign_key.target_fullname
        for foreign_key in table.c.arriving_flight_id.foreign_keys
    } == {"flights.id"}
    assert {
        foreign_key.target_fullname
        for foreign_key in table.c.missed_flight_id.foreign_keys
    } == {"flights.id"}

    assert index_columns(table) == {
        "ix_disruptions_affected_flight_id": ("affected_flight_id",),
        "ix_disruptions_affected_segment_id": ("affected_segment_id",),
    }


def test_segment_supports_the_composite_disruption_foreign_key() -> None:
    table = model_table(ItinerarySegmentRecord)

    assert unique_constraints(table)["uq_itinerary_segments_id_flight"] == (
        "id",
        "flight_id",
    )


def test_policy_types_are_normalized_and_ordered() -> None:
    policy_table = model_table(DisruptionPolicyRecord)
    type_table = model_table(DisruptionPolicyTypeRecord)

    assert tuple(column.name for column in policy_table.primary_key.columns) == ("id",)
    assert "ck_disruption_policies_positive_window" in constraint_names(
        policy_table,
        CheckConstraint,
    )
    assert tuple(column.name for column in type_table.primary_key.columns) == (
        "policy_id",
        "disruption_type",
    )
    assert unique_constraints(type_table)["uq_disruption_policy_types_sequence"] == (
        "policy_id",
        "sequence",
    )
    assert {
        "ck_disruption_policy_types_supported_type",
        "ck_disruption_policy_types_positive_sequence",
    } <= constraint_names(type_table, CheckConstraint)
    assert index_columns(type_table)["ix_disruption_policy_types_type"] == (
        "disruption_type",
    )

    policy_fk = next(iter(type_table.c.policy_id.foreign_keys))
    assert policy_fk.target_fullname == "disruption_policies.id"
    assert policy_fk.ondelete == "CASCADE"


def test_recovery_case_references_are_required_and_indexed() -> None:
    table = model_table(RecoveryCaseRecord)

    assert tuple(column.name for column in table.primary_key.columns) == ("id",)
    assert {
        column_name: {
            foreign_key.target_fullname
            for foreign_key in table.c[column_name].foreign_keys
        }
        for column_name in ("booking_id", "disruption_id", "policy_id")
    } == {
        "booking_id": {"bookings.id"},
        "disruption_id": {"disruptions.id"},
        "policy_id": {"disruption_policies.id"},
    }
    assert index_columns(table) == {
        "ix_recovery_cases_booking_id": ("booking_id",),
        "ix_recovery_cases_disruption_id": ("disruption_id",),
        "ix_recovery_cases_policy_id": ("policy_id",),
    }


def test_case_orm_relationships_are_explicit() -> None:
    assert {
        "affected_flight",
        "affected_segment",
        "arriving_flight",
        "missed_flight",
    } <= set(DisruptionRecord.__mapper__.relationships.keys())
    assert "type_links" in DisruptionPolicyRecord.__mapper__.relationships
    assert "policy" in DisruptionPolicyTypeRecord.__mapper__.relationships
    assert {"booking", "disruption", "policy"} <= set(
        RecoveryCaseRecord.__mapper__.relationships.keys()
    )

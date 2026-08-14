"""SQLAlchemy persistence models for airline business records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative metadata for Alembic and SQLAlchemy."""


class PassengerRecord(Base):
    __tablename__ = "passengers"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        nullable=False,
    )
    given_name: Mapped[str] = mapped_column(String(100), nullable=False)
    family_name: Mapped[str] = mapped_column(String(100), nullable=False)

    booking_links: Mapped[list[BookingPassengerRecord]] = relationship(
        back_populates="passenger",
        passive_deletes=True,
    )


class FlightRecord(Base):
    __tablename__ = "flights"
    __table_args__ = (
        CheckConstraint(
            "origin <> destination",
            name="ck_flights_distinct_airports",
        ),
        CheckConstraint(
            "scheduled_arrival > scheduled_departure",
            name="ck_flights_arrival_after_departure",
        ),
        UniqueConstraint(
            "carrier_code",
            "flight_number",
            "scheduled_departure",
            name="uq_flights_scheduled_service",
        ),
        Index(
            "ix_flights_route_departure",
            "origin",
            "destination",
            "scheduled_departure",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        nullable=False,
    )
    carrier_code: Mapped[str] = mapped_column(String(2), nullable=False)
    flight_number: Mapped[str] = mapped_column(String(4), nullable=False)
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    scheduled_departure: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    scheduled_arrival: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    segments: Mapped[list[ItinerarySegmentRecord]] = relationship(
        back_populates="flight",
        passive_deletes=True,
    )


class FlightAvailabilityEvidenceRecord(Base):
    __tablename__ = "flight_availability_evidence"
    __table_args__ = (
        CheckConstraint(
            "available_seats >= 0",
            name="ck_flight_availability_nonnegative_seats",
        ),
    )

    flight_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("flights.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    available_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)


class BookingRecord(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        nullable=False,
    )

    passenger_links: Mapped[list[BookingPassengerRecord]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BookingPassengerRecord.passenger_id",
    )
    segments: Mapped[list[ItinerarySegmentRecord]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ItinerarySegmentRecord.sequence",
    )


class TicketRuleEvidenceRecord(Base):
    __tablename__ = "ticket_rule_evidence"
    __table_args__ = (
        CheckConstraint(
            "max_connections >= 0 AND max_connections <= 4",
            name="ck_ticket_rule_connection_range",
        ),
    )

    booking_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    rebooking_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allowed_carrier_code: Mapped[str] = mapped_column(String(2), nullable=False)
    max_connections: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)


class BookingPassengerRecord(Base):
    __tablename__ = "booking_passengers"
    __table_args__ = (
        Index(
            "ix_booking_passengers_passenger_id",
            "passenger_id",
        ),
    )

    booking_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    passenger_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("passengers.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )

    booking: Mapped[BookingRecord] = relationship(
        back_populates="passenger_links",
    )
    passenger: Mapped[PassengerRecord] = relationship(
        back_populates="booking_links",
    )


class ItinerarySegmentRecord(Base):
    __tablename__ = "itinerary_segments"
    __table_args__ = (
        UniqueConstraint(
            "booking_id",
            "sequence",
            name="uq_itinerary_segments_booking_sequence",
        ),
        UniqueConstraint(
            "booking_id",
            "flight_id",
            name="uq_itinerary_segments_booking_flight",
        ),
        CheckConstraint(
            "sequence > 0",
            name="ck_itinerary_segments_positive_sequence",
        ),
        Index(
            "ix_itinerary_segments_flight_id",
            "flight_id",
        ),
        UniqueConstraint(
            "id",
            "flight_id",
            name="uq_itinerary_segments_id_flight",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        nullable=False,
    )
    booking_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    flight_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("flights.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    booking: Mapped[BookingRecord] = relationship(back_populates="segments")
    flight: Mapped[FlightRecord] = relationship(back_populates="segments")


class DisruptionRecord(Base):
    __tablename__ = "disruptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["affected_segment_id", "affected_flight_id"],
            ["itinerary_segments.id", "itinerary_segments.flight_id"],
            name="fk_disruptions_affected_segment_flight",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "type IN ('delayed_flight', 'cancelled_flight', 'missed_connection')",
            name="ck_disruptions_supported_type",
        ),
        CheckConstraint(
            "("
            "type = 'delayed_flight' "
            "AND delay_minutes IS NOT NULL "
            "AND delay_minutes > 0 "
            "AND cancellation_reason IS NULL "
            "AND arriving_flight_id IS NULL "
            "AND missed_flight_id IS NULL"
            ") OR ("
            "type = 'cancelled_flight' "
            "AND delay_minutes IS NULL "
            "AND cancellation_reason IS NOT NULL "
            "AND length(btrim(cancellation_reason)) > 0 "
            "AND arriving_flight_id IS NULL "
            "AND missed_flight_id IS NULL"
            ") OR ("
            "type = 'missed_connection' "
            "AND delay_minutes IS NULL "
            "AND cancellation_reason IS NULL "
            "AND arriving_flight_id IS NOT NULL "
            "AND missed_flight_id IS NOT NULL "
            "AND arriving_flight_id <> missed_flight_id "
            "AND affected_flight_id = missed_flight_id"
            ")",
            name="ck_disruptions_type_specific_details",
        ),
        Index(
            "ix_disruptions_affected_flight_id",
            "affected_flight_id",
        ),
        Index(
            "ix_disruptions_affected_segment_id",
            "affected_segment_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        nullable=False,
    )
    affected_flight_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("flights.id", ondelete="RESTRICT"),
        nullable=False,
    )
    affected_segment_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    delay_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    arriving_flight_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("flights.id", ondelete="RESTRICT"),
        nullable=True,
    )
    missed_flight_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("flights.id", ondelete="RESTRICT"),
        nullable=True,
    )

    affected_flight: Mapped[FlightRecord] = relationship(
        foreign_keys=[affected_flight_id],
    )
    affected_segment: Mapped[ItinerarySegmentRecord] = relationship(
        foreign_keys=[affected_segment_id, affected_flight_id],
        viewonly=True,
    )
    arriving_flight: Mapped[FlightRecord | None] = relationship(
        foreign_keys=[arriving_flight_id],
    )
    missed_flight: Mapped[FlightRecord | None] = relationship(
        foreign_keys=[missed_flight_id],
    )


class DisruptionPolicyRecord(Base):
    __tablename__ = "disruption_policies"
    __table_args__ = (
        CheckConstraint(
            "rebooking_window_hours > 0",
            name="ck_disruption_policies_positive_window",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    rebooking_window_hours: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    allows_next_day: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    type_links: Mapped[list[DisruptionPolicyTypeRecord]] = relationship(
        back_populates="policy",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DisruptionPolicyTypeRecord.sequence",
    )


class DisruptionPolicyTypeRecord(Base):
    __tablename__ = "disruption_policy_types"
    __table_args__ = (
        UniqueConstraint(
            "policy_id",
            "sequence",
            name="uq_disruption_policy_types_sequence",
        ),
        CheckConstraint(
            "disruption_type IN ("
            "'delayed_flight', "
            "'cancelled_flight', "
            "'missed_connection'"
            ")",
            name="ck_disruption_policy_types_supported_type",
        ),
        CheckConstraint(
            "sequence > 0",
            name="ck_disruption_policy_types_positive_sequence",
        ),
        Index(
            "ix_disruption_policy_types_type",
            "disruption_type",
        ),
    )

    policy_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("disruption_policies.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    disruption_type: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    policy: Mapped[DisruptionPolicyRecord] = relationship(
        back_populates="type_links",
    )


class RecoveryCaseRecord(Base):
    __tablename__ = "recovery_cases"
    __table_args__ = (
        Index("ix_recovery_cases_booking_id", "booking_id"),
        Index("ix_recovery_cases_disruption_id", "disruption_id"),
        Index("ix_recovery_cases_policy_id", "policy_id"),
    )

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    booking_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    disruption_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("disruptions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("disruption_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )

    booking: Mapped[BookingRecord] = relationship()
    disruption: Mapped[DisruptionRecord] = relationship()
    policy: Mapped[DisruptionPolicyRecord] = relationship()


class RebookingProposalRecord(Base):
    __tablename__ = "rebooking_proposals"
    __table_args__ = (
        UniqueConstraint("case_id", "version", name="uq_proposal_case_version"),
        CheckConstraint("version > 0", name="ck_proposal_positive_version"),
        CheckConstraint("expires_at > created_at", name="ck_proposal_expiry"),
        Index(
            "uq_proposal_active_case",
            "case_id",
            unique=True,
            postgresql_where=text(
                "status IN ('awaiting_approval','approved','executing')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("recovery_cases.id", ondelete="RESTRICT"), nullable=False
    )
    booking_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False
    )
    recommendation_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    validation_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    itinerary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    itinerary_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_snapshot: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False
    )
    evidence_completeness: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    required_role: Mapped[str] = mapped_column(String(64), nullable=False)
    revalidation: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    execution_result: Mapped[dict[str, object] | None] = mapped_column(JSON)
    failure_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    escalation_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    workflow_run_id: Mapped[str | None] = mapped_column(String(36))
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)


class ProposalApprovalRecord(Base):
    __tablename__ = "proposal_approvals"
    __table_args__ = (UniqueConstraint("proposal_id", name="uq_proposal_one_decision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rebooking_proposals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    proposal_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    itinerary_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)


class ExecutionAttemptRecord(Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_execution_idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rebooking_proposals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, object] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(Text)


class BookingChangeRecord(Base):
    __tablename__ = "booking_changes"
    __table_args__ = (
        UniqueConstraint("proposal_id", name="uq_booking_change_proposal"),
        UniqueConstraint("booking_id", name="uq_booking_change_booking"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rebooking_proposals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    booking_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False
    )
    original_itinerary: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False
    )
    replacement_itinerary: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ProposalAuditRecord(Base):
    __tablename__ = "proposal_audit_records"
    __table_args__ = (Index("ix_proposal_audit_order", "proposal_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    proposal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rebooking_proposals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)

"""add safe rebooking proposals and immutable audit

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-14 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rebooking_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.String(32), nullable=False),
        sa.Column("booking_id", sa.String(32), nullable=False),
        sa.Column("recommendation_reference", sa.String(128), nullable=False),
        sa.Column("validation_reference", sa.String(128), nullable=False),
        sa.Column("itinerary", postgresql.JSONB(), nullable=False),
        sa.Column("itinerary_fingerprint", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_completeness", sa.String(20), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("required_role", sa.String(64), nullable=False),
        sa.Column("revalidation", postgresql.JSONB(), nullable=False),
        sa.Column("execution_result", postgresql.JSONB(), nullable=True),
        sa.Column("failure_reasons", postgresql.JSONB(), nullable=False),
        sa.Column("escalation_reasons", postgresql.JSONB(), nullable=False),
        sa.Column("workflow_run_id", sa.String(36), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["recovery_cases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("case_id", "version", name="uq_proposal_case_version"),
        sa.CheckConstraint("version > 0", name="ck_proposal_positive_version"),
        sa.CheckConstraint("expires_at > created_at", name="ck_proposal_expiry"),
    )
    op.create_index(
        "uq_proposal_active_case",
        "rebooking_proposals",
        ["case_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('awaiting_approval','approved','executing')"
        ),
    )
    op.create_table(
        "proposal_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("actor_role", sa.String(64), nullable=False),
        sa.Column("itinerary_fingerprint", sa.String(64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["rebooking_proposals.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("proposal_id", name="uq_proposal_one_decision"),
    )
    op.create_table(
        "execution_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["rebooking_proposals.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_execution_idempotency_key"),
    )
    op.create_table(
        "booking_changes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("booking_id", sa.String(32), nullable=False),
        sa.Column("original_itinerary", postgresql.JSONB(), nullable=False),
        sa.Column("replacement_itinerary", postgresql.JSONB(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["rebooking_proposals.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("proposal_id", name="uq_booking_change_proposal"),
        sa.UniqueConstraint("booking_id", name="uq_booking_change_booking"),
    )
    op.create_table(
        "proposal_audit_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["rebooking_proposals.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_proposal_audit_order",
        "proposal_audit_records",
        ["proposal_id", "sequence"],
    )
    op.execute("""
        CREATE FUNCTION prevent_proposal_audit_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'proposal audit records are immutable'; END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER proposal_audit_immutable
        BEFORE UPDATE OR DELETE ON proposal_audit_records
        FOR EACH ROW EXECUTE FUNCTION prevent_proposal_audit_mutation();
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS proposal_audit_immutable ON proposal_audit_records"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_proposal_audit_mutation()")
    op.drop_table("proposal_audit_records")
    op.drop_table("booking_changes")
    op.drop_table("execution_attempts")
    op.drop_table("proposal_approvals")
    op.drop_index("uq_proposal_active_case", table_name="rebooking_proposals")
    op.drop_table("rebooking_proposals")

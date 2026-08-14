"""add repository-backed recommendation evidence

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flight_availability_evidence",
        sa.Column("flight_id", sa.String(length=32), nullable=False),
        sa.Column("available_seats", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.CheckConstraint(
            "available_seats >= 0",
            name="ck_flight_availability_nonnegative_seats",
        ),
        sa.ForeignKeyConstraint(["flight_id"], ["flights.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("flight_id"),
    )
    op.create_table(
        "ticket_rule_evidence",
        sa.Column("booking_id", sa.String(length=32), nullable=False),
        sa.Column("rebooking_allowed", sa.Boolean(), nullable=False),
        sa.Column("allowed_carrier_code", sa.String(length=2), nullable=False),
        sa.Column("max_connections", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.CheckConstraint(
            "max_connections >= 0 AND max_connections <= 4",
            name="ck_ticket_rule_connection_range",
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("booking_id"),
    )


def downgrade() -> None:
    op.drop_table("ticket_rule_evidence")
    op.drop_table("flight_availability_evidence")

"""create isolated durable workflow schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13 21:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKFLOW_SCHEMA = "workflow"


def upgrade() -> None:
    """Create application-owned workflow metadata outside business tables."""

    op.execute(sa.schema.CreateSchema(WORKFLOW_SCHEMA, if_not_exists=True))
    op.create_table(
        "workflow_runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_sequence", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "status IN ('created', 'running', 'paused', 'cancelling', "
            "'cancelled', 'completed', 'awaiting_information', 'failed')",
            name="ck_workflow_runs_supported_status",
        ),
        sa.CheckConstraint(
            "last_event_sequence >= 0",
            name="ck_workflow_runs_nonnegative_event_sequence",
        ),
        sa.CheckConstraint("version >= 1", name="ck_workflow_runs_positive_version"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["recovery_cases.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("thread_id", name="uq_workflow_runs_thread_id"),
        schema=WORKFLOW_SCHEMA,
    )
    op.create_index(
        "ix_workflow_runs_case_created",
        "workflow_runs",
        ["case_id", "created_at"],
        unique=False,
        schema=WORKFLOW_SCHEMA,
    )
    op.create_index(
        "uq_workflow_runs_one_active_case",
        "workflow_runs",
        ["case_id"],
        unique=True,
        schema=WORKFLOW_SCHEMA,
        postgresql_where=sa.text(
            "status IN ('created', 'running', 'paused', 'cancelling')"
        ),
    )
    op.create_table(
        "workflow_events",
        sa.Column("event_id", sa.String(length=96), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("sequence > 0", name="ck_workflow_events_positive_sequence"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{WORKFLOW_SCHEMA}.workflow_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "run_id", "sequence", name="uq_workflow_events_run_sequence"
        ),
        schema=WORKFLOW_SCHEMA,
    )
    op.create_index(
        "ix_workflow_events_occurred_at",
        "workflow_events",
        ["occurred_at"],
        unique=False,
        schema=WORKFLOW_SCHEMA,
    )


def downgrade() -> None:
    """Remove workflow metadata without touching business records."""

    op.drop_index(
        "ix_workflow_events_occurred_at",
        table_name="workflow_events",
        schema=WORKFLOW_SCHEMA,
    )
    op.drop_table("workflow_events", schema=WORKFLOW_SCHEMA)
    op.drop_index(
        "uq_workflow_runs_one_active_case",
        table_name="workflow_runs",
        schema=WORKFLOW_SCHEMA,
    )
    op.drop_index(
        "ix_workflow_runs_case_created",
        table_name="workflow_runs",
        schema=WORKFLOW_SCHEMA,
    )
    op.drop_table("workflow_runs", schema=WORKFLOW_SCHEMA)
    # The supported LangGraph saver owns additional tables in this schema.
    op.execute(sa.schema.DropSchema(WORKFLOW_SCHEMA, cascade=True))

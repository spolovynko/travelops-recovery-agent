"""Real-PostgreSQL tests for the Alembic migration path."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import DateTime, inspect, text

from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.persistence.session import create_database_engine

EXPECTED_BUSINESS_TABLES = {
    "passengers",
    "flights",
    "bookings",
    "booking_passengers",
    "itinerary_segments",
    "disruptions",
    "disruption_policies",
    "disruption_policy_types",
    "recovery_cases",
    "flight_availability_evidence",
    "ticket_rule_evidence",
    "rebooking_proposals",
    "proposal_approvals",
    "execution_attempts",
    "booking_changes",
    "proposal_audit_records",
}

EXPECTED_WORKFLOW_TABLES = {
    "workflow_events",
    "workflow_runs",
}


@contextmanager
def configured_alembic(
    test_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Config]:
    monkeypatch.setenv("TRAVELOPS_DATABASE_URL", test_database_url)
    yield Config("alembic.ini")


@pytest.mark.integration
def test_alembic_builds_the_business_schema_from_zero(
    test_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_database_engine(Settings(database_url=SecretStr(test_database_url)))

    try:
        with configured_alembic(test_database_url, monkeypatch) as config:
            command.downgrade(config, "base")
            assert EXPECTED_BUSINESS_TABLES.isdisjoint(
                inspect(engine).get_table_names()
            )

            command.upgrade(config, "head")

        inspector = inspect(engine)
        assert set(inspector.get_table_names()) >= EXPECTED_BUSINESS_TABLES

        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0004"
            )

        assert set(inspector.get_table_names(schema="workflow")) >= (
            EXPECTED_WORKFLOW_TABLES
        )
        assert EXPECTED_WORKFLOW_TABLES.isdisjoint(inspector.get_table_names())

        flight_columns = {
            column["name"]: column for column in inspector.get_columns("flights")
        }
        for column_name in ("scheduled_departure", "scheduled_arrival"):
            column = flight_columns[column_name]
            column_type = column["type"]
            assert column["nullable"] is False
            assert isinstance(column_type, DateTime)
            assert column_type.timezone is True
    finally:
        engine.dispose()


@pytest.mark.integration
def test_alembic_upgrades_phase_one_schema_with_phase_nine_evidence_tables(
    test_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_database_engine(Settings(database_url=SecretStr(test_database_url)))
    try:
        with configured_alembic(test_database_url, monkeypatch) as config:
            command.downgrade(config, "base")
            command.upgrade(config, "0001")
            before = set(inspect(engine).get_table_names())
            assert "flight_availability_evidence" not in before
            assert "ticket_rule_evidence" not in before
            assert inspect(engine).get_table_names(schema="workflow") == []

            command.upgrade(config, "head")

        assert set(inspect(engine).get_table_names()) >= EXPECTED_BUSINESS_TABLES
        assert set(inspect(engine).get_table_names()) - before == {
            "flight_availability_evidence",
            "ticket_rule_evidence",
            "rebooking_proposals",
            "proposal_approvals",
            "execution_attempts",
            "booking_changes",
            "proposal_audit_records",
        }
        assert set(inspect(engine).get_table_names(schema="workflow")) >= (
            EXPECTED_WORKFLOW_TABLES
        )
    finally:
        engine.dispose()

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
                == "0002"
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
def test_alembic_upgrades_the_phase_seven_schema_without_changing_business_tables(
    test_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_database_engine(Settings(database_url=SecretStr(test_database_url)))
    try:
        with configured_alembic(test_database_url, monkeypatch) as config:
            command.downgrade(config, "base")
            command.upgrade(config, "0001")
            before = set(inspect(engine).get_table_names())
            assert before >= EXPECTED_BUSINESS_TABLES
            assert inspect(engine).get_table_names(schema="workflow") == []

            command.upgrade(config, "head")

        assert set(inspect(engine).get_table_names()) == before
        assert set(inspect(engine).get_table_names(schema="workflow")) >= (
            EXPECTED_WORKFLOW_TABLES
        )
    finally:
        engine.dispose()

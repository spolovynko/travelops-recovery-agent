"""Shared real-PostgreSQL integration-test fixtures."""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.persistence.session import (
    SessionFactory,
    create_database_engine,
    create_session_factory,
)

TEST_DATABASE_URL_ENV = "TRAVELOPS_TEST_DATABASE_URL"
MANAGED_TABLES = (
    "workflow.workflow_events",
    "workflow.workflow_runs",
    "recovery_cases",
    "disruptions",
    "disruption_policy_types",
    "booking_passengers",
    "itinerary_segments",
    "bookings",
    "disruption_policies",
    "flights",
    "passengers",
)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    database_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if database_url is None:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not configured")

    parsed_url = make_url(database_url)
    if parsed_url.get_backend_name() != "postgresql":
        pytest.fail("integration tests require PostgreSQL")
    if parsed_url.database != "travelops_test":
        pytest.fail(f"{TEST_DATABASE_URL_ENV} must target travelops_test")

    return database_url


@pytest.fixture(scope="session")
def migrated_engine(test_database_url: str) -> Iterator[Engine]:
    previous_database_url = os.environ.get("TRAVELOPS_DATABASE_URL")
    os.environ["TRAVELOPS_DATABASE_URL"] = test_database_url

    try:
        try:
            command.upgrade(Config("alembic.ini"), "head")
        except SQLAlchemyError:
            pytest.fail(
                "integration database connection failed; verify that PostgreSQL "
                "is healthy and the test database URL is correct",
                pytrace=False,
            )
    finally:
        if previous_database_url is None:
            os.environ.pop("TRAVELOPS_DATABASE_URL", None)
        else:
            os.environ["TRAVELOPS_DATABASE_URL"] = previous_database_url

    engine = create_database_engine(Settings(database_url=SecretStr(test_database_url)))
    try:
        yield engine
    finally:
        engine.dispose()


def truncate_managed_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {', '.join(MANAGED_TABLES)} CASCADE"))


@pytest.fixture
def clean_session_factory(migrated_engine: Engine) -> Iterator[SessionFactory]:
    truncate_managed_tables(migrated_engine)
    try:
        yield create_session_factory(migrated_engine)
    finally:
        truncate_managed_tables(migrated_engine)

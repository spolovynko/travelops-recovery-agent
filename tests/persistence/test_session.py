"""Tests for database engine and session construction."""

import pytest
from pydantic import SecretStr

from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.persistence.session import (
    DatabaseConfigurationError,
    create_database_engine,
    create_session_factory,
)

DATABASE_PASSWORD = "test-only-password"
DATABASE_URL = (
    f"postgresql+psycopg://travelops:{DATABASE_PASSWORD}@127.0.0.1:55432/travelops"
)


def test_database_engine_requires_an_explicit_url() -> None:
    with pytest.raises(
        DatabaseConfigurationError,
        match="TRAVELOPS_DATABASE_URL is required",
    ):
        create_database_engine(Settings(database_url=None))


def test_database_engine_uses_psycopg_without_exposing_the_password() -> None:
    settings = Settings(database_url=SecretStr(DATABASE_URL))

    engine = create_database_engine(settings)

    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.host == "127.0.0.1"
        assert engine.url.port == 55432
        assert engine.url.database == "travelops"
        assert DATABASE_PASSWORD not in str(engine.url)
        assert DATABASE_PASSWORD not in repr(engine.url)
    finally:
        engine.dispose()


def test_session_factory_binds_short_lived_sessions_to_the_engine() -> None:
    settings = Settings(database_url=SecretStr(DATABASE_URL))
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        with session_factory() as session:
            assert session.bind is engine
            assert session.autoflush is False
            assert session.expire_on_commit is False
    finally:
        engine.dispose()

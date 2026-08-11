"""Real-PostgreSQL tests for the transaction boundary."""

from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.persistence.session import (
    create_database_engine,
    create_session_factory,
)


@pytest.mark.integration
def test_session_factory_commits_success_and_rolls_back_failure(
    test_database_url: str,
) -> None:
    settings = Settings(database_url=SecretStr(test_database_url))
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    table_name = f"transaction_probe_{uuid4().hex}"

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE TABLE {table_name} ("
                    "id INTEGER PRIMARY KEY, "
                    "label TEXT NOT NULL"
                    ")"
                )
            )

        with (
            pytest.raises(RuntimeError, match="simulated workflow failure"),
            session_factory.begin() as session,
        ):
            session.execute(
                text(f"INSERT INTO {table_name} VALUES (:id, :label)"),
                [
                    {"id": 1, "label": "first"},
                    {"id": 2, "label": "second"},
                ],
            )
            raise RuntimeError("simulated workflow failure")

        with session_factory() as session:
            assert session.scalar(text(f"SELECT COUNT(*) FROM {table_name}")) == 0

        with session_factory.begin() as session:
            session.execute(
                text(f"INSERT INTO {table_name} VALUES (:id, :label)"),
                {"id": 3, "label": "committed"},
            )

        with session_factory() as session:
            assert session.scalar(text(f"SELECT COUNT(*) FROM {table_name}")) == 1
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        engine.dispose()

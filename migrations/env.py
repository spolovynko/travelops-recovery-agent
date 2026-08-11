"""Alembic environment for the TravelOps PostgreSQL schema."""

from logging.config import fileConfig

from alembic import context

from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.persistence.models import Base
from travelops_recovery_agent.persistence.session import (
    DatabaseConfigurationError,
    create_database_engine,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def configured_database_url() -> str:
    settings = Settings()
    if settings.database_url is None:
        raise DatabaseConfigurationError(
            "TRAVELOPS_DATABASE_URL is required for Alembic migrations"
        )

    return settings.database_url.get_secret_value()


def run_migrations_offline() -> None:
    """Render migration SQL without opening a database connection."""
    context.configure(
        url=configured_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations through a real database connection."""
    engine = create_database_engine(Settings())

    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

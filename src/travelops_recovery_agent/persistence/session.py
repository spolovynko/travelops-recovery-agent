"""Database engine and session construction."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from travelops_recovery_agent.core.config import Settings


class DatabaseConfigurationError(RuntimeError):
    """Raised when a database workflow lacks required configuration."""


type SessionFactory = sessionmaker[Session]


def create_database_engine(settings: Settings) -> Engine:
    if settings.database_url is None:
        raise DatabaseConfigurationError(
            "TRAVELOPS_DATABASE_URL is required for database workflows"
        )

    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
    )


def create_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

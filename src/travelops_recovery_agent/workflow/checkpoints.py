"""Managed PostgreSQL LangGraph checkpointer isolated in the workflow schema."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import Connection, connect
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.persistence.session import DatabaseConfigurationError

WORKFLOW_SCHEMA = "workflow"

_ALLOWED_CHECKPOINT_TYPES = (
    ("travelops_recovery_agent.agent.models", "AgentRunState"),
    ("travelops_recovery_agent.agent.models", "RunStatus"),
    ("travelops_recovery_agent.agent.models", "ConversationMessage"),
    ("travelops_recovery_agent.agent.models", "ConversationRole"),
    ("travelops_recovery_agent.agent.models", "RunBudget"),
    ("travelops_recovery_agent.agent.models", "ToolObservation"),
    ("travelops_recovery_agent.agent.models", "SafeAgentFailure"),
    ("travelops_recovery_agent.agent.models", "AgentFailureCode"),
    ("travelops_recovery_agent.agent.models", "CallToolDecision"),
    ("travelops_recovery_agent.agent.models", "AskInformationDecision"),
    ("travelops_recovery_agent.agent.models", "FinishDecision"),
    ("travelops_recovery_agent.agent.models", "AgentOutcome"),
    ("travelops_recovery_agent.agent.decision_model", "ModelErrorCode"),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "RecommendationResult",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "RecommendationOption",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "RecommendationSegment",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "OptionValidation",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "ValidationCheck",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "EvidenceReference",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "RankingInputs",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "RecommendationOutcome",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "EvidenceCompleteness",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "EvidenceKind",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "RecommendationRule",
    ),
    (
        "travelops_recovery_agent.application.recommendation_models",
        "ValidationStatus",
    ),
)


def _psycopg_connection_string(settings: Settings) -> str:
    if settings.database_url is None:
        raise DatabaseConfigurationError(
            "TRAVELOPS_DATABASE_URL is required for durable workflows"
        )
    url = make_url(settings.database_url.get_secret_value())
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


class CheckpointStore:
    """Own one thread-safe saver connection for an application lifetime."""

    def __init__(self, settings: Settings) -> None:
        self._connection_string = _psycopg_connection_string(settings)
        self._connection: Connection[Any] | None = None
        self._saver: PostgresSaver | None = None

    @property
    def saver(self) -> PostgresSaver:
        if self._saver is None:
            raise RuntimeError("checkpoint store is not open")
        return self._saver

    def open(self) -> Self:
        if self._connection is not None:
            raise RuntimeError("checkpoint store is already open")
        connection = connect(
            self._connection_string,
            autocommit=True,
            row_factory=dict_row,
        )
        connection.execute(f"SET search_path TO {WORKFLOW_SCHEMA}")
        serializer = JsonPlusSerializer(
            allowed_msgpack_modules=_ALLOWED_CHECKPOINT_TYPES
        )
        saver = PostgresSaver(connection, serde=serializer)
        saver.setup()
        self._connection = connection
        self._saver = saver
        return self

    def close(self) -> None:
        connection = self._connection
        self._saver = None
        self._connection = None
        if connection is not None:
            connection.close()

    def __enter__(self) -> Self:
        return self.open()

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

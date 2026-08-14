"""Checkpoint-store configuration and graph compatibility tests."""

from pydantic import SecretStr

from travelops_recovery_agent.agent.graph import build_recovery_graph
from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.workflow.checkpoints import CheckpointStore


def test_graph_still_compiles_without_a_checkpointer() -> None:
    graph = build_recovery_graph()
    assert "tool_execution" in graph.get_graph().nodes


def test_checkpoint_store_does_not_expose_database_credentials() -> None:
    secret = "postgresql+psycopg://travelops:do-not-print@localhost/travelops"
    store = CheckpointStore(Settings(database_url=SecretStr(secret)))

    assert "do-not-print" not in repr(store)

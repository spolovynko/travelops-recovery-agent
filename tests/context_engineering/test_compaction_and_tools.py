"""Conversation summary and tool-governance safety tests."""

from datetime import UTC, datetime

from travelops_recovery_agent.context_engineering.compaction import (
    ConversationCategory,
    ConversationCompactor,
    ConversationTurn,
    validate_summary,
)
from travelops_recovery_agent.context_engineering.models import (
    ContextBuildRequest,
    ContextTask,
)
from travelops_recovery_agent.context_engineering.tool_governance import (
    ToolGovernancePolicy,
)

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)


def test_summary_preserves_categories_and_invalidates_when_fact_changes() -> None:
    turns = (
        ConversationTurn(
            turn_id="turn-1",
            category=ConversationCategory.FACT,
            text="The affected service is cancelled.",
            durable_fact_ids=("STATUS-1",),
            source_versions={"STATUS-1": "1"},
        ),
        ConversationTurn(
            turn_id="turn-2",
            category=ConversationCategory.OPERATOR_INSTRUCTION,
            text="Keep the travel party together.",
            durable_fact_ids=("INSTRUCTION-1",),
            source_versions={"INSTRUCTION-1": "1"},
        ),
        ConversationTurn(
            turn_id="turn-secret",
            category=ConversationCategory.FACT,
            text="credential value",
            durable_fact_ids=("SECRET-1",),
            source_versions={"SECRET-1": "1"},
            contains_sensitive_data=True,
        ),
    )

    summary = ConversationCompactor().compact(turns, max_tokens=100)

    assert summary.derived_view is True
    assert summary.facts == ("The affected service is cancelled.",)
    assert summary.operator_instructions == ("Keep the travel party together.",)
    assert "SECRET-1" not in summary.referenced_evidence_ids
    assert validate_summary(
        summary,
        {"STATUS-1": "1", "INSTRUCTION-1": "1"},
        frozenset({"STATUS-1", "INSTRUCTION-1"}),
    ).valid
    invalid = validate_summary(
        summary,
        {"STATUS-1": "2", "INSTRUCTION-1": "1"},
        frozenset({"STATUS-1", "INSTRUCTION-1"}),
    )
    assert invalid.valid is False
    assert invalid.reason == "referenced fact changed: STATUS-1"


def governed_request(
    *,
    task: ContextTask,
    role: str,
    permissions: frozenset[str],
    approval_status: str | None,
    status: str,
) -> ContextBuildRequest:
    return ContextBuildRequest(
        case_id="CASE-1",
        task=task,
        workflow_node="proposal_approval",
        operator_id="operator-1",
        operator_role=role,
        permissions=permissions,
        authorization_scopes=frozenset({"case:CASE-1"}),
        token_budget=2_000,
        approval_status=approval_status,
        workflow_status=status,
        now=NOW,
    )


def test_write_tool_requires_exact_execution_state_role_permission_and_approval() -> (
    None
):
    policy = ToolGovernancePolicy()
    allowed = governed_request(
        task=ContextTask.EXECUTE_REBOOKING,
        role="recovery_operator",
        permissions=frozenset({"rebooking:execute"}),
        approval_status="approved",
        status="paused",
    )
    denied = allowed.model_copy(update={"approval_status": "pending"})

    allowed_tools = policy.evaluate(allowed)
    denied_tools = policy.evaluate(denied)

    assert [tool.name for tool in allowed_tools if tool.exposed] == [
        "execute_rebooking"
    ]
    assert not any(tool.exposed for tool in denied_tools)
    execute = next(tool for tool in denied_tools if tool.name == "execute_rebooking")
    assert execute.reason == "approved_execution_boundary_required"


def test_tool_policy_denies_every_capability_for_unknown_role_without_permissions() -> (
    None
):
    tools = ToolGovernancePolicy().evaluate(
        governed_request(
            task=ContextTask.EXECUTE_REBOOKING,
            role="viewer",
            permissions=frozenset(),
            approval_status="approved",
            status="paused",
        )
    )

    assert not any(tool.exposed for tool in tools)

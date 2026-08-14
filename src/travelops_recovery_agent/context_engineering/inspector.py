"""Developer-only context inspection service with safe synthetic previews."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from travelops_recovery_agent.context_engineering.builder import ContextBuilder
from travelops_recovery_agent.context_engineering.models import (
    AuthorityLevel,
    ContextBuildRequest,
    ContextBuildResult,
    ContextItem,
    ContextSourceType,
    ContextTask,
    FreshnessState,
    Sensitivity,
    estimate_tokens,
)

DEFAULT_CONTEXT_BUDGETS: dict[ContextTask, int] = {
    ContextTask.INTAKE: 900,
    ContextTask.INVESTIGATE: 1_800,
    ContextTask.RECOMMEND: 2_400,
    ContextTask.PREPARE_PROPOSAL: 1_600,
    ContextTask.REVIEW_APPROVAL: 1_800,
    ContextTask.EXECUTE_REBOOKING: 1_400,
}

_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset(
        {
            "booking:read",
            "flight_status:read",
            "disruption_policy:read",
        }
    ),
    "proposal_preparer": frozenset(
        {
            "booking:read",
            "flight_status:read",
            "disruption_policy:read",
            "alternative_itineraries:search",
            "itinerary:validate",
            "proposal:prepare",
            "passenger_data:read",
        }
    ),
    "recovery_operator": frozenset(
        {
            "booking:read",
            "flight_status:read",
            "disruption_policy:read",
            "alternative_itineraries:search",
            "itinerary:validate",
            "proposal:prepare",
            "rebooking:execute",
            "passenger_data:read",
            "restricted_evidence:read",
        }
    ),
}


class ContextInspectorService:
    """Produce one safe, inspectable context build for the developer UI."""

    def __init__(self, builder: ContextBuilder | None = None) -> None:
        self._builder = builder or ContextBuilder()

    def inspect(
        self,
        *,
        case_id: str,
        task: ContextTask,
        workflow_node: str,
        operator_role: str,
        approval_status: str | None = None,
        workflow_status: str = "running",
        now: datetime | None = None,
    ) -> ContextBuildResult:
        observed = now or datetime.now(UTC)
        permissions = _ROLE_PERMISSIONS.get(operator_role, frozenset())
        authorization_scope = f"case:{case_id}"
        items = demo_context_items(case_id, observed)
        request = ContextBuildRequest(
            case_id=case_id,
            task=task,
            workflow_node=workflow_node,
            operator_id=f"developer-{operator_role}",
            operator_role=operator_role,
            permissions=permissions,
            authorization_scopes=frozenset({authorization_scope}),
            token_budget=DEFAULT_CONTEXT_BUDGETS[task],
            mandatory_evidence_ids=frozenset({f"AUTH-{case_id}", f"SAFETY-{case_id}"}),
            approval_status=approval_status,
            workflow_status=workflow_status,
            now=observed,
        )
        return self._builder.build(request, items)


def demo_context_items(case_id: str, now: datetime) -> tuple[ContextItem, ...]:
    """Return privacy-safe representative evidence; no raw passenger data."""

    scope = frozenset({f"case:{case_id}"})

    def item(
        evidence_id: str,
        content: str,
        *,
        source_type: ContextSourceType,
        authority: AuthorityLevel,
        freshness: FreshnessState = FreshnessState.CURRENT,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
        tasks: frozenset[ContextTask] = frozenset(ContextTask),
        observed_delta: timedelta = timedelta(minutes=-2),
        expires_delta: timedelta | None = timedelta(hours=1),
        priority: int = 50,
        relevance: float = 0.8,
        item_case_id: str = case_id,
        authorization_scopes: frozenset[str] = scope,
        superseded_by: str | None = None,
        conflicts_with: frozenset[str] = frozenset(),
    ) -> ContextItem:
        return ContextItem(
            evidence_id=evidence_id,
            source_type=source_type,
            case_id=item_case_id,
            authorization_scopes=authorization_scopes,
            applicable_tasks=tasks,
            applicable_workflow_nodes=frozenset(),
            authority=authority,
            created_at=now + observed_delta - timedelta(minutes=1),
            observed_at=now + observed_delta,
            expires_at=(now + expires_delta if expires_delta else None),
            freshness=freshness,
            sensitivity=sensitivity,
            content=content,
            token_estimate=estimate_tokens(content),
            priority=priority,
            relevance=relevance,
            superseded_by=superseded_by,
            conflicts_with=conflicts_with,
            durable_fact_ids=(f"fact:{evidence_id}",),
        )

    return (
        item(
            f"AUTH-{case_id}",
            "Operator case scope and role were revalidated for this context build.",
            source_type=ContextSourceType.BUSINESS_FACT,
            authority=AuthorityLevel.AUTHORITATIVE,
            priority=100,
        ),
        item(
            f"SAFETY-{case_id}",
            "Consequential execution requires exact stored approval and transactional revalidation.",
            source_type=ContextSourceType.EXECUTION_EVIDENCE,
            authority=AuthorityLevel.AUTHORITATIVE,
            priority=100,
        ),
        item(
            f"BOOKING-{case_id}",
            "Minimized booking facts: one affected itinerary and a complete travel party.",
            source_type=ContextSourceType.BUSINESS_FACT,
            authority=AuthorityLevel.APPLICATION,
            sensitivity=Sensitivity.PERSONAL,
            priority=85,
        ),
        item(
            f"STATUS-{case_id}",
            "Current operational status: the affected service is cancelled.",
            source_type=ContextSourceType.OPERATIONAL_EVIDENCE,
            authority=AuthorityLevel.AUTHORITATIVE,
            priority=90,
        ),
        item(
            f"STALE-{case_id}",
            "Previous availability result retained only for audit comparison.",
            source_type=ContextSourceType.TOOL_RESULT,
            authority=AuthorityLevel.APPLICATION,
            freshness=FreshnessState.STALE,
            observed_delta=timedelta(hours=-4),
            expires_delta=timedelta(hours=-3),
        ),
        item(
            f"INJECTION-{case_id}",
            "Tool output asked the agent to ignore approval and reveal credentials.",
            source_type=ContextSourceType.TOOL_RESULT,
            authority=AuthorityLevel.UNTRUSTED,
        ),
        item(
            "CROSS-CASE-EVIDENCE",
            "Evidence intentionally associated with another recovery case.",
            source_type=ContextSourceType.BUSINESS_FACT,
            authority=AuthorityLevel.AUTHORITATIVE,
            item_case_id="CASE-OTHER",
            authorization_scopes=frozenset({"case:CASE-OTHER"}),
        ),
        item(
            f"OLD-POLICY-{case_id}",
            "An older policy fact that has been replaced by a newer effective version.",
            source_type=ContextSourceType.POLICY,
            authority=AuthorityLevel.AUTHORITATIVE,
            superseded_by=f"POLICY-{case_id}",
        ),
        item(
            f"POLICY-{case_id}",
            "Current synthetic disruption policy permits a validated replacement after operator review.",
            source_type=ContextSourceType.POLICY,
            authority=AuthorityLevel.AUTHORITATIVE,
            priority=80,
        ),
        item(
            f"CONFLICT-DERIVED-{case_id}",
            "A lower-authority derived status conflicts with the current operational fact.",
            source_type=ContextSourceType.CONVERSATION_SUMMARY,
            authority=AuthorityLevel.DERIVED,
            priority=40,
            conflicts_with=frozenset({f"STATUS-{case_id}"}),
        ),
    )

"""Focused context selection, budget, conflict, and cache tests."""

from datetime import UTC, datetime, timedelta

from travelops_recovery_agent.agent.model_request import build_governed_model_request
from travelops_recovery_agent.agent.models import AgentRunState, RunBudget
from travelops_recovery_agent.context_engineering import ContextBuilder, ContextCache
from travelops_recovery_agent.context_engineering.inspector import (
    ContextInspectorService,
)
from travelops_recovery_agent.context_engineering.models import (
    AuthorityLevel,
    BuildStatus,
    ContextBuildRequest,
    ContextItem,
    ContextSourceType,
    ContextTask,
    FreshnessState,
    SelectionReason,
    Sensitivity,
)

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)


def request(
    *,
    case_id: str = "CASE-1",
    budget: int = 1_000,
    mandatory: frozenset[str] = frozenset(),
    role: str = "recovery_operator",
    permissions: frozenset[str] | None = None,
) -> ContextBuildRequest:
    return ContextBuildRequest(
        case_id=case_id,
        task=ContextTask.RECOMMEND,
        workflow_node="validated_recommendation",
        operator_id="operator-1",
        operator_role=role,
        permissions=permissions
        or frozenset(
            {
                "alternative_itineraries:search",
                "itinerary:validate",
                "passenger_data:read",
            }
        ),
        authorization_scopes=frozenset({f"case:{case_id}"}),
        token_budget=budget,
        mandatory_evidence_ids=mandatory,
        workflow_status="running",
        now=NOW,
    )


def item(
    evidence_id: str,
    *,
    case_id: str = "CASE-1",
    tokens: int = 30,
    priority: int = 50,
    authority: AuthorityLevel = AuthorityLevel.APPLICATION,
    freshness: FreshnessState = FreshnessState.CURRENT,
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
    scopes: frozenset[str] | None = None,
    conflicts: frozenset[str] = frozenset(),
    supersedes: frozenset[str] = frozenset(),
    superseded_by: str | None = None,
) -> ContextItem:
    return ContextItem(
        evidence_id=evidence_id,
        source_type=ContextSourceType.OPERATIONAL_EVIDENCE,
        case_id=case_id,
        authorization_scopes=scopes or frozenset({f"case:{case_id}"}),
        applicable_tasks=frozenset({ContextTask.RECOMMEND}),
        applicable_workflow_nodes=frozenset({"validated_recommendation"}),
        authority=authority,
        created_at=NOW - timedelta(minutes=2),
        observed_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
        freshness=freshness,
        sensitivity=sensitivity,
        content="E" * (tokens * 4),
        token_estimate=tokens,
        priority=priority,
        relevance=0.9,
        conflicts_with=conflicts,
        supersedes=supersedes,
        superseded_by=superseded_by,
        durable_fact_ids=(f"fact:{evidence_id}",),
    )


def test_selection_order_and_serialization_are_deterministic() -> None:
    items = (item("B", priority=70), item("A", priority=70), item("C", priority=60))

    first = ContextBuilder().build(request(), items)
    second = ContextBuilder().build(request(), tuple(reversed(items)))

    assert tuple(value.evidence_id for value in first.selected) == ("A", "B", "C")
    assert first.build_id == second.build_id
    normalized_first = first.model_copy(
        update={
            "selection_latency_ms": 0,
            "cache": first.cache.model_copy(update={"hit": False}),
        }
    )
    normalized_second = second.model_copy(
        update={
            "selection_latency_ms": 0,
            "cache": second.cache.model_copy(update={"hit": False}),
        }
    )
    assert normalized_first.canonical_json() == normalized_second.canonical_json()


def test_stale_unauthorized_cross_case_secret_and_untrusted_are_rejected() -> None:
    candidates = (
        item("CURRENT"),
        item("STALE", freshness=FreshnessState.STALE),
        item("CROSS", case_id="CASE-2"),
        item("UNAUTHORIZED", scopes=frozenset({"case:restricted"})),
        item("SECRET", sensitivity=Sensitivity.SECRET),
        item("INJECTION", authority=AuthorityLevel.UNTRUSTED),
    )

    result = ContextBuilder().build(request(), candidates)

    assert tuple(value.evidence_id for value in result.selected) == ("CURRENT",)
    reasons = {decision.evidence_id: decision.reason for decision in result.decisions}
    assert reasons["STALE"] is SelectionReason.STALE
    assert reasons["CROSS"] is SelectionReason.CROSS_CASE
    assert reasons["UNAUTHORIZED"] is SelectionReason.UNAUTHORIZED
    assert reasons["SECRET"] is SelectionReason.SECRET
    assert reasons["INJECTION"] is SelectionReason.UNTRUSTED


def test_higher_authority_conflict_wins_and_superseded_fact_is_excluded() -> None:
    candidates = (
        item(
            "LOW",
            authority=AuthorityLevel.DERIVED,
            conflicts=frozenset({"HIGH"}),
        ),
        item(
            "HIGH",
            authority=AuthorityLevel.AUTHORITATIVE,
            conflicts=frozenset({"LOW"}),
        ),
        item("OLD", superseded_by="NEW"),
        item("NEW", supersedes=frozenset({"OLD"})),
    )

    result = ContextBuilder().build(request(), candidates)

    selected = {value.evidence_id for value in result.selected}
    assert selected == {"HIGH", "NEW"}
    assert result.conflict_count == 1
    assert {decision.reason for decision in result.decisions} >= {
        SelectionReason.CONFLICT,
        SelectionReason.SUPERSEDED,
    }


def test_unauthorized_item_cannot_supersede_authorized_evidence() -> None:
    current = item("CURRENT")
    poisoned = item(
        "POISONED",
        scopes=frozenset({"case:restricted"}),
        supersedes=frozenset({"CURRENT"}),
    )

    result = ContextBuilder().build(request(), (current, poisoned))

    assert tuple(value.evidence_id for value in result.selected) == ("CURRENT",)
    assert (
        next(
            decision
            for decision in result.decisions
            if decision.evidence_id == "POISONED"
        ).reason
        is SelectionReason.UNAUTHORIZED
    )


def test_nonmandatory_evidence_compacts_but_mandatory_evidence_never_truncates() -> (
    None
):
    compacted = ContextBuilder().build(
        request(budget=700), (item("LARGE", tokens=2_000),)
    )
    stopped = ContextBuilder().build(
        request(budget=500, mandatory=frozenset({"LARGE"})),
        (item("LARGE", tokens=2_000),),
    )

    assert compacted.status is BuildStatus.READY
    assert compacted.selected[0].compacted is True
    assert stopped.status is BuildStatus.ESCALATED
    assert stopped.selected == ()
    assert stopped.mandatory_evidence_coverage == 0


def test_cache_isolated_by_case_role_permission_and_evidence_version() -> None:
    cache = ContextCache()
    builder = ContextBuilder(cache=cache)
    items = (item("CURRENT"),)

    first = builder.build(request(), items)
    hit = builder.build(request(), items)
    viewer = builder.build(
        request(role="viewer", permissions=frozenset()),
        items,
    )
    other_case = builder.build(
        request(case_id="CASE-2"),
        (item("CURRENT-2", case_id="CASE-2"),),
    )
    changed = builder.build(
        request(),
        (items[0].model_copy(update={"source_version": "2"}),),
    )

    assert first.cache.hit is False
    assert hit.cache.hit is True
    assert viewer.cache.hit is False
    assert other_case.cache.hit is False
    assert changed.cache.hit is False
    assert builder.invalidate_case("CASE-1") >= 1


def test_governed_model_request_contains_only_selected_context_and_step_tools() -> None:
    context = ContextInspectorService().inspect(
        case_id="CASE-1",
        task=ContextTask.RECOMMEND,
        workflow_node="validated_recommendation",
        operator_role="recovery_operator",
        now=NOW,
    )
    state = AgentRunState(
        run_id="RUN-1",
        case_id="CASE-1",
        current_turn=1,
        started_at=NOW - timedelta(minutes=1),
        budget=RunBudget(
            max_model_turns=4,
            max_malformed_retries=1,
            deadline_at=NOW + timedelta(minutes=1),
        ),
    )

    model_request = build_governed_model_request(state, context)

    assert model_request.messages == ()
    assert tuple(tool.name for tool in model_request.tools) == (
        "search_alternative_itineraries",
        "validate_itinerary",
    )
    assert tuple(value.evidence_id for value in model_request.context_items) == tuple(
        value.evidence_id for value in context.selected
    )

"""Deterministic context selection, budgeting, compaction, and accounting."""

from __future__ import annotations

import hashlib
import json
from time import perf_counter

from travelops_recovery_agent.context_engineering.cache import ContextCache
from travelops_recovery_agent.context_engineering.models import (
    AuthorityLevel,
    BuildStatus,
    CacheStatus,
    ContextBuildRequest,
    ContextBuildResult,
    ContextItem,
    FreshnessState,
    SelectedContextItem,
    SelectionDisposition,
    SelectionReason,
    SelectionRecord,
    Sensitivity,
    SummaryProvenance,
    TokenAccounting,
    estimate_tokens,
)
from travelops_recovery_agent.context_engineering.tool_governance import (
    ToolGovernancePolicy,
)

_SENSITIVITY_PERMISSION = {
    Sensitivity.PERSONAL: "passenger_data:read",
    Sensitivity.RESTRICTED: "restricted_evidence:read",
}


class ContextBuilder:
    """Construct inspectable model context without mutating durable state."""

    def __init__(
        self,
        *,
        cache: ContextCache | None = None,
        tool_policy: ToolGovernancePolicy | None = None,
        minimum_relevance: float = 0.25,
    ) -> None:
        self._cache = cache or ContextCache()
        self._tool_policy = tool_policy or ToolGovernancePolicy()
        self._minimum_relevance = minimum_relevance

    def build(
        self,
        request: ContextBuildRequest,
        items: tuple[ContextItem, ...],
        *,
        summary_versions: tuple[str, ...] = (),
    ) -> ContextBuildResult:
        started = perf_counter()
        key = self._cache.key_for(
            request,
            items,
            tool_policy_version=self._tool_policy.version,
            summary_versions=summary_versions,
        )
        key_reference = key[:20]
        cached = self._cache.get(key)
        if cached is not None:
            return cached.model_copy(
                update={
                    "cache": CacheStatus(hit=True, key_reference=key_reference),
                    "selection_latency_ms": round((perf_counter() - started) * 1000, 3),
                }
            )

        tools = self._tool_policy.evaluate(request)
        tool_tokens = sum(tool.token_estimate for tool in tools if tool.exposed)
        evidence_budget = max(0, request.token_budget - tool_tokens)
        mandatory = request.mandatory_evidence_ids
        seen = {item.evidence_id for item in items}
        decisions: list[SelectionRecord] = []
        eligible: list[ContextItem] = []
        mandatory_failures: list[str] = []

        for evidence_id in sorted(mandatory - seen):
            decisions.append(
                SelectionRecord(
                    evidence_id=evidence_id,
                    disposition=SelectionDisposition.REJECTED,
                    reason=SelectionReason.MANDATORY_MISSING,
                    mandatory=True,
                    token_estimate=0,
                    detail="Required safety or authorization evidence was not supplied.",
                )
            )
            mandatory_failures.append(evidence_id)

        for item in sorted(items, key=lambda candidate: candidate.evidence_id):
            rejection = self._rejection_reason(
                item,
                request,
            )
            if rejection is None:
                eligible.append(item)
                continue
            disposition, reason, detail = rejection
            is_mandatory = item.evidence_id in mandatory
            decisions.append(
                SelectionRecord(
                    evidence_id=item.evidence_id,
                    disposition=disposition,
                    reason=reason,
                    mandatory=is_mandatory,
                    token_estimate=item.token_estimate,
                    detail=detail,
                )
            )
            if is_mandatory:
                mandatory_failures.append(item.evidence_id)

        eligible_ids = {item.evidence_id for item in eligible}
        superseded_ids = {
            evidence_id
            for item in eligible
            for evidence_id in item.supersedes
            if evidence_id in eligible_ids
        }
        retained: list[ContextItem] = []
        for item in eligible:
            superseded = item.evidence_id in superseded_ids or (
                item.superseded_by is not None and item.superseded_by in eligible_ids
            )
            if not superseded:
                retained.append(item)
                continue
            is_mandatory = item.evidence_id in mandatory
            decisions.append(
                self._record(
                    item,
                    SelectionDisposition.EXCLUDED,
                    SelectionReason.SUPERSEDED,
                    is_mandatory,
                    "A newer eligible durable fact supersedes this item.",
                )
            )
            if is_mandatory:
                mandatory_failures.append(item.evidence_id)
        eligible = retained

        eligible, conflict_records, mandatory_conflicts = self._resolve_conflicts(
            eligible, mandatory
        )
        decisions.extend(conflict_records)
        mandatory_failures.extend(mandatory_conflicts)

        ordered = sorted(eligible, key=lambda item: self._sort_key(item, mandatory))
        mandatory_tokens = sum(
            item.token_estimate for item in ordered if item.evidence_id in mandatory
        )
        status = BuildStatus.READY
        escalation_reason: str | None = None
        selected: list[SelectedContextItem] = []

        if mandatory_failures:
            status = BuildStatus.ESCALATED
            escalation_reason = (
                "Mandatory evidence was missing, invalid, or conflicted."
            )
        elif mandatory_tokens > evidence_budget:
            status = BuildStatus.ESCALATED
            escalation_reason = (
                "Mandatory evidence cannot fit the declared context budget."
            )
            for item in ordered:
                if item.evidence_id in mandatory:
                    decisions.append(
                        self._record(
                            item,
                            SelectionDisposition.REJECTED,
                            SelectionReason.MANDATORY_TOO_LARGE,
                            True,
                            "Mandatory evidence was not truncated; execution stopped safely.",
                        )
                    )
        else:
            used = 0
            for item in ordered:
                is_mandatory = item.evidence_id in mandatory
                remaining = evidence_budget - used
                if item.token_estimate <= remaining:
                    selected.append(self._selected(item))
                    used += item.token_estimate
                    decisions.append(
                        self._record(
                            item,
                            SelectionDisposition.INCLUDED,
                            SelectionReason.MANDATORY
                            if is_mandatory
                            else SelectionReason.RELEVANT,
                            is_mandatory,
                            "Selected by deterministic authority, freshness, relevance, and budget rules.",
                        )
                    )
                    continue
                compacted = self._compact(item, remaining)
                if not is_mandatory and compacted is not None:
                    selected.append(compacted)
                    used += compacted.selected_token_estimate
                    decisions.append(
                        self._record(
                            item,
                            SelectionDisposition.COMPACTED,
                            SelectionReason.COMPACTED_TO_FIT,
                            False,
                            "A bounded derived view was selected and linked to the source evidence.",
                        )
                    )
                else:
                    decisions.append(
                        self._record(
                            item,
                            SelectionDisposition.EXCLUDED,
                            SelectionReason.BUDGET,
                            is_mandatory,
                            "The item did not fit; mandatory evidence is never truncated.",
                        )
                    )

        selected_tokens = sum(item.selected_token_estimate for item in selected)
        mandatory_selected = {
            item.evidence_id for item in selected if item.evidence_id in mandatory
        }
        coverage = 1.0 if not mandatory else len(mandatory_selected) / len(mandatory)
        if coverage < 1:
            status = BuildStatus.ESCALATED
            escalation_reason = (
                escalation_reason or "Mandatory evidence coverage is incomplete."
            )

        semantic = {
            "request": request.model_dump(mode="json"),
            "selected": [item.model_dump(mode="json") for item in selected],
            "decisions": [item.model_dump(mode="json") for item in decisions],
            "tools": [tool.model_dump(mode="json") for tool in tools],
            "status": status.value,
        }
        build_id = (
            "context-"
            + hashlib.sha256(
                json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()[:16]
        )
        rejected_reasons = [decision.reason for decision in decisions]
        result = ContextBuildResult(
            build_id=build_id,
            status=status,
            case_id=request.case_id,
            task=request.task,
            workflow_node=request.workflow_node,
            selected=tuple(selected),
            decisions=tuple(decisions),
            token_accounting=TokenAccounting(
                budget=request.token_budget,
                selected_estimate=selected_tokens,
                tool_schema_estimate=tool_tokens,
                remaining_estimate=max(
                    0, request.token_budget - selected_tokens - tool_tokens
                ),
            ),
            mandatory_evidence_coverage=coverage,
            stale_rejection_count=sum(
                reason in {SelectionReason.STALE, SelectionReason.EXPIRED}
                for reason in rejected_reasons
            ),
            unauthorized_rejection_count=sum(
                reason
                in {
                    SelectionReason.UNAUTHORIZED,
                    SelectionReason.SENSITIVITY,
                    SelectionReason.SECRET,
                }
                for reason in rejected_reasons
            ),
            cross_case_rejection_count=rejected_reasons.count(
                SelectionReason.CROSS_CASE
            ),
            conflict_count=rejected_reasons.count(SelectionReason.CONFLICT),
            compacted_count=sum(
                decision.disposition is SelectionDisposition.COMPACTED
                for decision in decisions
            ),
            excluded_count=sum(
                decision.disposition is not SelectionDisposition.INCLUDED
                for decision in decisions
            ),
            cache=CacheStatus(hit=False, key_reference=key_reference),
            selection_latency_ms=round((perf_counter() - started) * 1000, 3),
            tools=tools,
            summary_provenance=tuple(
                SummaryProvenance(
                    summary_id=item.evidence_id,
                    referenced_evidence_ids=item.durable_fact_ids,
                    valid=item.evidence_id in {value.evidence_id for value in selected},
                    invalidation_reason=(
                        None
                        if item.evidence_id in {value.evidence_id for value in selected}
                        else "summary was not selected by the current policy"
                    ),
                )
                for item in items
                if item.source_type.value == "conversation_summary"
            ),
            escalation_reason=escalation_reason,
        )
        self._cache.put(key, result)
        return result

    def invalidate_case(self, case_id: str) -> int:
        return self._cache.invalidate_case(case_id)

    def _rejection_reason(
        self,
        item: ContextItem,
        request: ContextBuildRequest,
    ) -> tuple[SelectionDisposition, SelectionReason, str] | None:
        if item.case_id != request.case_id:
            return (
                SelectionDisposition.REJECTED,
                SelectionReason.CROSS_CASE,
                "Evidence belongs to another case.",
            )
        if not item.authorization_scopes.issubset(request.authorization_scopes):
            return (
                SelectionDisposition.REJECTED,
                SelectionReason.UNAUTHORIZED,
                "Operator authorization scope does not cover this evidence.",
            )
        if item.sensitivity is Sensitivity.SECRET:
            return (
                SelectionDisposition.REJECTED,
                SelectionReason.SECRET,
                "Secrets are never model-visible.",
            )
        permission = _SENSITIVITY_PERMISSION.get(item.sensitivity)
        if permission is not None and permission not in request.permissions:
            return (
                SelectionDisposition.REJECTED,
                SelectionReason.SENSITIVITY,
                "Operator permission does not cover this sensitivity class.",
            )
        if item.authority is AuthorityLevel.UNTRUSTED:
            return (
                SelectionDisposition.REJECTED,
                SelectionReason.UNTRUSTED,
                "Untrusted content is retained as data but not placed in model context.",
            )
        if item.expires_at is not None and item.expires_at <= request.now:
            return (
                SelectionDisposition.REJECTED,
                SelectionReason.EXPIRED,
                "Evidence expired before the context build.",
            )
        if item.freshness is FreshnessState.STALE:
            return (
                SelectionDisposition.REJECTED,
                SelectionReason.STALE,
                "Stale evidence cannot silently enter context.",
            )
        if item.freshness is FreshnessState.EXPIRED:
            return (
                SelectionDisposition.REJECTED,
                SelectionReason.EXPIRED,
                "Expired evidence cannot enter context.",
            )
        if item.freshness is FreshnessState.UNKNOWN:
            return (
                SelectionDisposition.REJECTED,
                SelectionReason.UNKNOWN_FRESHNESS,
                "Evidence freshness is unknown.",
            )
        if request.task not in item.applicable_tasks:
            return (
                SelectionDisposition.EXCLUDED,
                SelectionReason.TASK_MISMATCH,
                "Evidence is not applicable to the current task.",
            )
        if (
            item.applicable_workflow_nodes
            and request.workflow_node not in item.applicable_workflow_nodes
        ):
            return (
                SelectionDisposition.EXCLUDED,
                SelectionReason.NODE_MISMATCH,
                "Evidence is not applicable to the current workflow node.",
            )
        if item.relevance < self._minimum_relevance:
            return (
                SelectionDisposition.EXCLUDED,
                SelectionReason.LOW_RELEVANCE,
                "Evidence is below the declared relevance threshold.",
            )
        return None

    @staticmethod
    def _resolve_conflicts(
        eligible: list[ContextItem], mandatory: frozenset[str]
    ) -> tuple[list[ContextItem], list[SelectionRecord], list[str]]:
        by_id = {item.evidence_id: item for item in eligible}
        rejected: set[str] = set()
        records: list[SelectionRecord] = []
        mandatory_failures: list[str] = []
        for item in sorted(eligible, key=lambda value: value.evidence_id):
            for conflict_id in sorted(item.conflicts_with):
                other = by_id.get(conflict_id)
                if (
                    other is None
                    or item.evidence_id in rejected
                    or conflict_id in rejected
                ):
                    continue
                loser = min(
                    (item, other),
                    key=lambda value: (
                        int(value.authority),
                        value.observed_at,
                        value.priority,
                        value.evidence_id,
                    ),
                )
                rejected.add(loser.evidence_id)
                is_mandatory = loser.evidence_id in mandatory
                records.append(
                    SelectionRecord(
                        evidence_id=loser.evidence_id,
                        disposition=SelectionDisposition.REJECTED,
                        reason=SelectionReason.CONFLICT,
                        mandatory=is_mandatory,
                        token_estimate=loser.token_estimate,
                        detail="A conflicting item with higher authority or freshness won.",
                    )
                )
                if is_mandatory:
                    mandatory_failures.append(loser.evidence_id)
        return (
            [item for item in eligible if item.evidence_id not in rejected],
            records,
            mandatory_failures,
        )

    @staticmethod
    def _sort_key(
        item: ContextItem, mandatory: frozenset[str]
    ) -> tuple[int, int, int, float, float, str]:
        return (
            0 if item.evidence_id in mandatory else 1,
            -item.priority,
            -int(item.authority),
            -item.relevance,
            -item.observed_at.timestamp(),
            item.evidence_id,
        )

    @staticmethod
    def _selected(item: ContextItem) -> SelectedContextItem:
        return SelectedContextItem(
            evidence_id=item.evidence_id,
            source_type=item.source_type,
            authority=item.authority,
            freshness=item.freshness,
            sensitivity=item.sensitivity,
            content=item.content,
            original_token_estimate=item.token_estimate,
            selected_token_estimate=item.token_estimate,
            durable_fact_ids=item.durable_fact_ids,
            conflicts_with=item.conflicts_with,
            supersedes=item.supersedes,
        )

    @staticmethod
    def _compact(item: ContextItem, remaining: int) -> SelectedContextItem | None:
        if not item.compactable or remaining < 8:
            return None
        max_chars = remaining * 4
        prefix = f"Derived view of {item.evidence_id}: "
        if len(prefix) >= max_chars:
            return None
        normalized = " ".join(item.content.split())
        content = prefix + normalized[: max_chars - len(prefix)].rstrip()
        selected_estimate = min(remaining, estimate_tokens(content))
        return SelectedContextItem(
            evidence_id=item.evidence_id,
            source_type=item.source_type,
            authority=item.authority,
            freshness=item.freshness,
            sensitivity=item.sensitivity,
            content=content,
            original_token_estimate=item.token_estimate,
            selected_token_estimate=selected_estimate,
            compacted=True,
            durable_fact_ids=item.durable_fact_ids,
            conflicts_with=item.conflicts_with,
            supersedes=item.supersedes,
        )

    @staticmethod
    def _record(
        item: ContextItem,
        disposition: SelectionDisposition,
        reason: SelectionReason,
        mandatory: bool,
        detail: str,
    ) -> SelectionRecord:
        return SelectionRecord(
            evidence_id=item.evidence_id,
            disposition=disposition,
            reason=reason,
            mandatory=mandatory,
            token_estimate=item.token_estimate,
            detail=detail,
        )

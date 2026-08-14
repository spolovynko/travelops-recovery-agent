"""Deterministic bounded conversation compaction as a derived view."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import Field, model_validator

from travelops_recovery_agent.context_engineering.models import (
    ContextContract,
    Identifier,
    SafeText,
    estimate_tokens,
)


class ConversationCategory(StrEnum):
    FACT = "fact"
    DECISION = "decision"
    HYPOTHESIS = "hypothesis"
    COMPLETED_WORK = "completed_work"
    UNRESOLVED_CONSTRAINT = "unresolved_constraint"
    OPERATOR_INSTRUCTION = "operator_instruction"


class ConversationTurn(ContextContract):
    turn_id: Identifier
    category: ConversationCategory
    text: SafeText
    durable_fact_ids: tuple[Identifier, ...] = ()
    source_versions: dict[str, str] = Field(default_factory=dict)
    contains_sensitive_data: bool = False


class ConversationSummary(ContextContract):
    schema_version: str = "travelops.conversation-summary.v1"
    summary_id: Identifier
    facts: tuple[SafeText, ...]
    decisions: tuple[SafeText, ...]
    hypotheses: tuple[SafeText, ...]
    completed_work: tuple[SafeText, ...]
    unresolved_constraints: tuple[SafeText, ...]
    operator_instructions: tuple[SafeText, ...]
    referenced_evidence_ids: tuple[Identifier, ...]
    source_versions: dict[str, str]
    token_estimate: int = Field(ge=1)
    estimate_method: str = "estimated_characters_div_4"
    derived_view: bool = True

    @model_validator(mode="after")
    def require_provenance(self) -> ConversationSummary:
        if not self.referenced_evidence_ids:
            raise ValueError("conversation summaries must reference durable evidence")
        return self


class SummaryValidation(ContextContract):
    valid: bool
    reason: str | None = None


class ConversationCompactor:
    """Build a deterministic summary without a model or raw prompt retention."""

    def compact(
        self,
        turns: tuple[ConversationTurn, ...],
        *,
        max_tokens: int,
    ) -> ConversationSummary:
        eligible = tuple(
            turn
            for turn in turns
            if not turn.contains_sensitive_data and turn.durable_fact_ids
        )
        if not eligible:
            raise ValueError("no privacy-safe durable conversation facts to summarize")

        buckets: dict[ConversationCategory, list[str]] = {
            category: [] for category in ConversationCategory
        }
        references: list[str] = []
        source_versions: dict[str, str] = {}
        used = 0
        for turn in eligible:
            text = " ".join(turn.text.split())
            estimate = estimate_tokens(text)
            if used + estimate > max_tokens:
                continue
            buckets[turn.category].append(text)
            used += estimate
            references.extend(turn.durable_fact_ids)
            source_versions.update(turn.source_versions)

        if not references:
            raise ValueError("conversation summary cannot fit any durable fact")
        canonical = json.dumps(
            {
                "turn_ids": [turn.turn_id for turn in eligible],
                "references": sorted(set(references)),
                "source_versions": dict(sorted(source_versions.items())),
                "buckets": {
                    category.value: buckets[category]
                    for category in ConversationCategory
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return ConversationSummary(
            summary_id=f"summary-{hashlib.sha256(canonical.encode()).hexdigest()[:16]}",
            facts=tuple(buckets[ConversationCategory.FACT]),
            decisions=tuple(buckets[ConversationCategory.DECISION]),
            hypotheses=tuple(buckets[ConversationCategory.HYPOTHESIS]),
            completed_work=tuple(buckets[ConversationCategory.COMPLETED_WORK]),
            unresolved_constraints=tuple(
                buckets[ConversationCategory.UNRESOLVED_CONSTRAINT]
            ),
            operator_instructions=tuple(
                buckets[ConversationCategory.OPERATOR_INSTRUCTION]
            ),
            referenced_evidence_ids=tuple(sorted(set(references))),
            source_versions=dict(sorted(source_versions.items())),
            token_estimate=max(1, used),
        )


def validate_summary(
    summary: ConversationSummary,
    current_source_versions: dict[str, str],
    available_evidence_ids: frozenset[str],
) -> SummaryValidation:
    """Invalidate a derived summary when referenced durable facts change."""

    if not set(summary.referenced_evidence_ids).issubset(available_evidence_ids):
        return SummaryValidation(
            valid=False, reason="referenced evidence is unavailable"
        )
    for source_id, version in summary.source_versions.items():
        if current_source_versions.get(source_id) != version:
            return SummaryValidation(
                valid=False,
                reason=f"referenced fact changed: {source_id}",
            )
    return SummaryValidation(valid=True)

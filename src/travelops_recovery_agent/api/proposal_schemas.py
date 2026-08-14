"""Typed HTTP inputs for consequential Phase 10 operations."""

from pydantic import BaseModel, ConfigDict, Field


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_run_id: str | None = None


class ProposalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(gt=0)
    itinerary_fingerprint: str = Field(min_length=64, max_length=64)
    reason: str | None = Field(default=None, max_length=500)


class ProposalExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=128)

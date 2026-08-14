"""Phase 11 failure classification, bounded retries, and test-only injection."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from time import sleep

from travelops_recovery_agent.core.config import Environment, Settings


class FailureCategory(StrEnum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    AUTHORIZATION = "authorization_related"
    VALIDATION = "validation_related"
    STALE_EVIDENCE = "stale_evidence"
    OPERATOR_ACTION_REQUIRED = "operator_action_required"


class FailureMode(StrEnum):
    PROVIDER_TIMEOUT = "provider_timeout"
    MALFORMED_MODEL_RESULT = "malformed_model_result"
    INVALID_TOOL_ARGUMENTS = "invalid_tool_arguments"
    RATE_LIMIT = "rate_limit"
    TRANSIENT_PROVIDER_FAILURE = "transient_provider_failure"
    DATABASE_FAILURE = "database_failure"
    LOST_AVAILABILITY = "lost_availability"
    CANCELLED_FLIGHT = "cancelled_flight"
    MISSING_FLIGHT = "missing_flight"
    CHANGED_FLIGHT = "changed_flight"
    CHANGED_POLICY = "changed_policy"
    SSE_DISCONNECT = "sse_disconnect"
    WORKFLOW_INTERRUPTION = "workflow_interruption"
    RESTART_BEFORE_CHECKPOINT = "restart_before_checkpoint"
    RESTART_AFTER_CHECKPOINT = "restart_after_checkpoint"
    RESTART_DURING_EXECUTION = "restart_during_execution"
    RESTART_AFTER_EXECUTION = "restart_after_execution"
    DUPLICATE_DELIVERY = "duplicate_delivery"
    RETRIED_REQUEST = "retried_request"
    REPLAYED_REQUEST = "replayed_request"


class ReliabilityError(RuntimeError):
    """Safe application error with a stable classification and public message."""

    def __init__(
        self,
        code: str,
        category: FailureCategory,
        public_message: str,
    ) -> None:
        super().__init__(public_message)
        self.code = code
        self.category = category
        self.public_message = public_message


class RetryableProviderError(ReliabilityError):
    def __init__(self, code: str = "provider_unavailable") -> None:
        super().__init__(
            code,
            FailureCategory.RETRYABLE,
            "The provider is temporarily unavailable; retry the investigation shortly.",
        )


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_seconds: float = 0.05
    backoff_multiplier: float = 2.0
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.max_attempts > 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if self.initial_backoff_seconds < 0 or self.timeout_seconds <= 0:
            raise ValueError("retry timings must be non-negative and bounded")


@dataclass(frozen=True)
class RetryResult[T]:
    value: T
    attempts: int


def run_with_retry[T](
    operation: Callable[[], T],
    policy: RetryPolicy,
    *,
    consequential_write: bool = False,
    idempotency_proven: bool = False,
    sleeper: Callable[[float], None] = sleep,
) -> RetryResult[T]:
    """Retry one owning layer; writes require an explicit idempotency proof."""

    if consequential_write and not idempotency_proven and policy.max_attempts > 1:
        raise ValueError("consequential writes cannot retry without idempotency proof")
    delay = policy.initial_backoff_seconds
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return RetryResult(operation(), attempt)
        except ReliabilityError as error:
            if error.category is not FailureCategory.RETRYABLE:
                raise
            if attempt == policy.max_attempts:
                raise ReliabilityError(
                    "retry_exhausted",
                    FailureCategory.OPERATOR_ACTION_REQUIRED,
                    "Automatic recovery was exhausted; an operator must retry later.",
                ) from error
            sleeper(delay)
            delay *= policy.backoff_multiplier
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class FailureInjector:
    """Deterministic fault injector that cannot be constructed for production."""

    enabled: bool
    seed: int
    modes: frozenset[FailureMode]

    @classmethod
    def from_settings(
        cls, settings: Settings, modes: set[FailureMode] | None = None
    ) -> FailureInjector:
        if settings.environment is Environment.PRODUCTION and (
            settings.failure_injection_enabled or modes
        ):
            raise ValueError("failure injection cannot be enabled in production")
        return cls(
            enabled=settings.failure_injection_enabled,
            seed=settings.failure_injection_seed,
            modes=frozenset(modes or set()),
        )

    def should_fail(self, mode: FailureMode, occurrence: int = 0) -> bool:
        if not self.enabled or mode not in self.modes:
            return False
        value = f"{self.seed}:{mode.value}:{occurrence}"
        return random.Random(value).random() < 1.0

    def inject(self, mode: FailureMode, occurrence: int = 0) -> None:
        if not self.should_fail(mode, occurrence):
            return
        mapping = {
            FailureMode.PROVIDER_TIMEOUT: (
                "provider_timeout",
                FailureCategory.RETRYABLE,
                "The provider timed out; the operation stopped safely.",
            ),
            FailureMode.RATE_LIMIT: (
                "provider_rate_limited",
                FailureCategory.RETRYABLE,
                "The provider rate limit was reached; retry later.",
            ),
            FailureMode.TRANSIENT_PROVIDER_FAILURE: (
                "provider_transient_failure",
                FailureCategory.RETRYABLE,
                "The provider is temporarily unavailable.",
            ),
            FailureMode.MALFORMED_MODEL_RESULT: (
                "malformed_model_result",
                FailureCategory.VALIDATION,
                "The model response failed validation and was not used.",
            ),
            FailureMode.INVALID_TOOL_ARGUMENTS: (
                "invalid_tool_arguments",
                FailureCategory.VALIDATION,
                "Tool arguments failed validation and were not executed.",
            ),
            FailureMode.DATABASE_FAILURE: (
                "database_failure",
                FailureCategory.OPERATOR_ACTION_REQUIRED,
                "The operation could not be committed and was rolled back.",
            ),
            FailureMode.LOST_AVAILABILITY: (
                "stale_availability",
                FailureCategory.STALE_EVIDENCE,
                "Availability changed; prepare a new proposal.",
            ),
            FailureMode.CHANGED_FLIGHT: (
                "changed_flight",
                FailureCategory.STALE_EVIDENCE,
                "Flight evidence changed; prepare a new proposal.",
            ),
            FailureMode.CANCELLED_FLIGHT: (
                "cancelled_flight",
                FailureCategory.STALE_EVIDENCE,
                "A proposed flight was cancelled; prepare a new proposal.",
            ),
            FailureMode.MISSING_FLIGHT: (
                "missing_flight",
                FailureCategory.STALE_EVIDENCE,
                "A proposed flight is missing; prepare a new proposal.",
            ),
            FailureMode.CHANGED_POLICY: (
                "changed_policy",
                FailureCategory.STALE_EVIDENCE,
                "Policy evidence changed; prepare a new proposal.",
            ),
        }
        code, category, message = mapping.get(
            mode,
            (
                mode.value,
                FailureCategory.OPERATOR_ACTION_REQUIRED,
                "The workflow was interrupted safely and can be resumed.",
            ),
        )
        raise ReliabilityError(code, category, message)

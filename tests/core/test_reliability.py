from __future__ import annotations

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.core.config import Environment, Settings
from travelops_recovery_agent.reliability import (
    FailureCategory,
    FailureInjector,
    FailureMode,
    ReliabilityError,
    RetryableProviderError,
    RetryPolicy,
    run_with_retry,
)


def test_production_rejects_failure_injection() -> None:
    with pytest.raises(ValidationError, match="cannot be enabled"):
        Settings(environment=Environment.PRODUCTION, failure_injection_enabled=True)


@pytest.mark.parametrize("mode", list(FailureMode))
def test_every_failure_mode_is_deterministically_controllable(
    mode: FailureMode,
) -> None:
    injector = FailureInjector.from_settings(
        Settings(environment=Environment.TEST, failure_injection_enabled=True), {mode}
    )
    with pytest.raises(ReliabilityError) as captured:
        injector.inject(mode)
    assert captured.value.code
    assert not injector.should_fail(next(item for item in FailureMode if item != mode))


def test_retry_is_bounded_and_records_attempts() -> None:
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RetryableProviderError()
        return "ok"

    result = run_with_retry(
        operation,
        RetryPolicy(max_attempts=3, initial_backoff_seconds=0),
        sleeper=lambda _: None,
    )
    assert result.value == "ok"
    assert result.attempts == 3


def test_retry_exhaustion_requires_operator_action() -> None:
    with pytest.raises(ReliabilityError) as captured:
        run_with_retry(
            lambda: (_ for _ in ()).throw(RetryableProviderError()),
            RetryPolicy(max_attempts=2, initial_backoff_seconds=0),
            sleeper=lambda _: None,
        )
    assert captured.value.category is FailureCategory.OPERATOR_ACTION_REQUIRED


def test_non_retryable_failure_stops_immediately() -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise ReliabilityError("invalid", FailureCategory.VALIDATION, "Invalid input")

    with pytest.raises(ReliabilityError, match="Invalid input"):
        run_with_retry(operation, RetryPolicy(), sleeper=lambda _: None)
    assert calls == 1


def test_write_retry_requires_idempotency_proof() -> None:
    with pytest.raises(ValueError, match="idempotency proof"):
        run_with_retry(lambda: "unsafe", RetryPolicy(), consequential_write=True)

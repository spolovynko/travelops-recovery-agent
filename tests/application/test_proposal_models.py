"""Deterministic proposal lifecycle contract tests."""

import pytest

from travelops_recovery_agent.application.proposal_models import (
    ProposalStatus,
    require_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ProposalStatus.DRAFTED, ProposalStatus.AWAITING_APPROVAL),
        (ProposalStatus.AWAITING_APPROVAL, ProposalStatus.APPROVED),
        (ProposalStatus.AWAITING_APPROVAL, ProposalStatus.REJECTED),
        (ProposalStatus.APPROVED, ProposalStatus.EXECUTING),
        (ProposalStatus.EXECUTING, ProposalStatus.EXECUTED),
    ],
)
def test_valid_proposal_transitions_are_explicit(
    current: ProposalStatus, target: ProposalStatus
) -> None:
    require_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ProposalStatus.AWAITING_APPROVAL, ProposalStatus.EXECUTED),
        (ProposalStatus.REJECTED, ProposalStatus.APPROVED),
        (ProposalStatus.EXPIRED, ProposalStatus.EXECUTING),
        (ProposalStatus.EXECUTED, ProposalStatus.EXECUTING),
    ],
)
def test_invalid_proposal_transitions_fail_closed(
    current: ProposalStatus, target: ProposalStatus
) -> None:
    with pytest.raises(ValueError, match="invalid proposal transition"):
        require_transition(current, target)

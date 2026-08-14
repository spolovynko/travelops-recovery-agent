"""Tests for database workflow CLI commands."""

from typing import cast

import pytest

from travelops_recovery_agent.application.models import (
    CompleteRecoveryCase,
    PersistenceRecordCounts,
)
from travelops_recovery_agent.application.services import (
    DatabaseNotEmptyError,
    RecoveryDataService,
)
from travelops_recovery_agent.data.dataset import SyntheticDataset
from travelops_recovery_agent.domain.models import RecoveryCaseId
from travelops_recovery_agent.persistence.cli import main

EMPTY_COUNTS = PersistenceRecordCounts(0, 0, 0, 0, 0, 0, 0, 0, 0)
SEEDED_COUNTS = PersistenceRecordCounts(13, 50, 10, 13, 20, 10, 1, 3, 10, 50, 10)


class StubRecoveryDataService:
    def __init__(self) -> None:
        self.seed_calls: list[tuple[SyntheticDataset, bool]] = []
        self.reset_calls = 0
        self.counts_result = SEEDED_COUNTS
        self.complete_case_result: CompleteRecoveryCase | None = None
        self.requested_case_ids: list[RecoveryCaseId] = []
        self.seed_error: DatabaseNotEmptyError | None = None

    def seed(
        self,
        dataset: SyntheticDataset,
        *,
        replace: bool = False,
    ) -> PersistenceRecordCounts:
        self.seed_calls.append((dataset, replace))
        if self.seed_error is not None:
            raise self.seed_error
        return self.counts_result

    def reset(self) -> PersistenceRecordCounts:
        self.reset_calls += 1
        return EMPTY_COUNTS

    def counts(self) -> PersistenceRecordCounts:
        return self.counts_result

    def get_complete_case(
        self,
        case_id: RecoveryCaseId,
    ) -> CompleteRecoveryCase | None:
        self.requested_case_ids.append(case_id)
        return self.complete_case_result


def as_service(stub: StubRecoveryDataService) -> RecoveryDataService:
    return cast(RecoveryDataService, stub)


def test_seed_generates_validated_data_and_reports_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub = StubRecoveryDataService()

    exit_code = main(["seed", "--seed", "42"], service=as_service(stub))

    captured = capsys.readouterr()
    dataset, replace = stub.seed_calls[0]
    assert exit_code == 0
    assert dataset.metadata.seed == 42
    assert len(dataset.recovery_cases) == 10
    assert replace is False
    assert "Seeded 10 recovery cases with deterministic seed 42." in captured.out
    assert captured.err == ""


def test_seed_replace_is_explicit() -> None:
    stub = StubRecoveryDataService()

    assert (
        main(
            ["seed", "--seed", "99", "--replace"],
            service=as_service(stub),
        )
        == 0
    )

    assert stub.seed_calls[0][1] is True


def test_seed_reports_controlled_non_empty_database(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub = StubRecoveryDataService()
    stub.seed_error = DatabaseNotEmptyError("database already contains records")

    exit_code = main(["seed", "--seed", "42"], service=as_service(stub))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "error: database already contains records" in captured.err


def test_reset_requires_explicit_confirmation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub = StubRecoveryDataService()

    exit_code = main(["reset"], service=as_service(stub))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert stub.reset_calls == 0
    assert "requires --confirm" in captured.err


def test_confirmed_reset_reports_empty_database(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub = StubRecoveryDataService()

    exit_code = main(["reset", "--confirm"], service=as_service(stub))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert stub.reset_calls == 1
    assert "Reset complete: 0 recovery cases remain." in captured.out


def test_counts_prints_every_managed_table_as_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub = StubRecoveryDataService()

    exit_code = main(["counts"], service=as_service(stub))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"passengers": 13' in captured.out
    assert '"recovery_cases": 10' in captured.out
    assert '"flight_availability_evidence": 50' in captured.out
    assert '"ticket_rule_evidence": 10' in captured.out
    assert captured.err == ""


def test_show_case_reports_missing_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub = StubRecoveryDataService()

    exit_code = main(
        ["show-case", "CASE-9999"],
        service=as_service(stub),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert stub.requested_case_ids == ["CASE-9999"]
    assert captured.out == ""
    assert "recovery case CASE-9999 was not found" in captured.err

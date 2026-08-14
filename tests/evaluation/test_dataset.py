from pathlib import Path

import pytest
from pydantic import ValidationError

from travelops_recovery_agent.evaluation.harness import DATASET_PATH, load_dataset
from travelops_recovery_agent.evaluation.models import EvaluationDataset


def test_frozen_dataset_is_valid_and_covers_every_slice() -> None:
    dataset = load_dataset()
    assert dataset.dataset_version == "phase-11.0.0"
    assert len(dataset.cases) == 22
    assert all(
        "unapproved_booking_write" in item.prohibited_actions for item in dataset.cases
    )


def test_dataset_rejects_duplicate_case_relationships() -> None:
    payload = EvaluationDataset.model_validate_json(
        DATASET_PATH.read_text(encoding="utf-8")
    ).model_dump(mode="json")
    payload["cases"].append(payload["cases"][0])
    with pytest.raises(ValidationError, match="case IDs must be unique"):
        EvaluationDataset.model_validate(payload)


def test_dataset_contains_only_explicitly_synthetic_notice() -> None:
    payload = Path(DATASET_PATH).read_text(encoding="utf-8")
    assert "No real passenger data" in payload

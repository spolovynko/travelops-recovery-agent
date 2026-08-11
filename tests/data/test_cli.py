"""Tests for synthetic dataset CLI commands."""

import subprocess
import sys
from pathlib import Path

import pytest

from travelops_recovery_agent.data.cli import main
from travelops_recovery_agent.data.dataset import load_dataset


def test_generate_command_writes_a_valid_dataset(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "generated.json"

    exit_code = main(["generate", "--seed", "42", "--output", str(output_path)])

    captured = capsys.readouterr()
    dataset = load_dataset(output_path)
    assert exit_code == 0
    assert dataset.metadata.seed == 42
    assert len(dataset.recovery_cases) == 10
    assert "Generated 10 recovery cases with seed 42" in captured.out
    assert captured.err == ""


def test_validate_command_loads_an_existing_dataset(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_path = tmp_path / "generated.json"
    assert main(["generate", "--seed", "73", "--output", str(dataset_path)]) == 0
    capsys.readouterr()

    exit_code = main(["validate", str(dataset_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Valid dataset: schema 1.0, seed 73, 10 recovery cases." in captured.out
    assert captured.err == ""


def test_generate_command_is_byte_stable_for_the_same_seed(tmp_path: Path) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    assert main(["generate", "--seed", "42", "--output", str(first_path)]) == 0
    assert main(["generate", "--seed", "42", "--output", str(second_path)]) == 0

    assert first_path.read_bytes() == second_path.read_bytes()


def test_validate_command_reports_a_missing_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_path = tmp_path / "missing.json"

    exit_code = main(["validate", str(missing_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "error:" in captured.err
    assert "missing.json" in captured.err


def test_validate_command_reports_invalid_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{not-json", encoding="utf-8")

    exit_code = main(["validate", str(invalid_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Invalid JSON" in captured.err


def test_module_entry_point_generates_and_validates_a_dataset(
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "module-generated.json"
    generate_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "travelops_recovery_agent.data.cli",
            "generate",
            "--seed",
            "91",
            "--output",
            str(dataset_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    validate_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "travelops_recovery_agent.data.cli",
            "validate",
            str(dataset_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert generate_result.returncode == 0
    assert "Generated 10 recovery cases" in generate_result.stdout
    assert generate_result.stderr == ""
    assert validate_result.returncode == 0
    assert "Valid dataset: schema 1.0, seed 91" in validate_result.stdout
    assert validate_result.stderr == ""

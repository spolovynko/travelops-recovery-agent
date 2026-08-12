"""Tests for the deterministic Phase 6 demonstration CLI."""

import json

import pytest

from travelops_recovery_agent.agent.cli import main, run_recorded_scenario
from travelops_recovery_agent.agent.fixtures import RECORDED_SCENARIOS


def test_cli_prints_complete_successful_investigation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["successful_investigation"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "completed"
    assert output["stop_reason"] == "finished"
    assert output["turns_used"] == 2
    assert output["turn_budget"] == 4
    assert output["model_events"][0]["step"]["type"] == "call_tool"
    assert output["model_events"][0]["step"]["tool_name"] == "get_booking"
    assert output["model_events"][1]["step"]["type"] == "finish"
    assert output["tool_observations"][0]["ok"] is True
    assert output["final_outcome"]["evidence_ids"] == ["observation-1"]


def test_cli_returns_failure_code_and_safe_stop_reason(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["repeated_tool_call"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert output["stop_reason"] == "repeated_tool_call"
    assert len(output["tool_observations"]) == 1


def test_cli_lists_stable_scenario_names(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--list"]) == 0
    assert capsys.readouterr().out.splitlines() == list(RECORDED_SCENARIOS)


def test_cli_default_is_byte_for_byte_deterministic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out

    assert first == second


def test_direct_composition_result_contains_no_hidden_or_secret_fields() -> None:
    result = run_recorded_scenario(RECORDED_SCENARIOS["malformed_recovery"])
    serialized = result.model_dump_json().lower()

    assert "chain_of_thought" not in serialized
    assert "hidden_reasoning" not in serialized
    assert "api_key" not in serialized
    assert "password" not in serialized
    assert "database_url" not in serialized
    assert result.stop_reason == "finished"


def test_deadline_output_has_no_unrequested_model_event() -> None:
    result = run_recorded_scenario(RECORDED_SCENARIOS["deadline_exhaustion"])

    assert result.stop_reason == "deadline_exceeded"
    assert result.turns_used == 0
    assert result.model_events == ()

"""Smoke tests for the installable package."""

from importlib import import_module


def test_package_imports() -> None:
    package = import_module("travelops_recovery_agent")

    assert package.__name__ == "travelops_recovery_agent"

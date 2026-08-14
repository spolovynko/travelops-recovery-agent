"""Validate or run the deterministic Phase 12 context experiment."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from travelops_recovery_agent.context_evaluation.harness import (
    DATASET_PATH,
    load_dataset,
    run_context_evaluation,
    write_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--dataset", type=Path, default=DATASET_PATH)
    run = commands.add_parser("run")
    run.add_argument("--dataset", type=Path, default=DATASET_PATH)
    run.add_argument("--output-dir", type=Path, default=Path("reports"))
    run.add_argument("--seed", type=int, default=42)
    run.add_argument(
        "--inject-defect",
        choices=("cross_case_cache", "write_tool_leak", "mandatory_drop"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        dataset = load_dataset(args.dataset)
        print(f"validated {len(dataset.cases)} cases in {dataset.dataset_version}")
        return 0
    report = run_context_evaluation(
        dataset_path=args.dataset,
        seed=args.seed,
        defect=args.inject_defect,
    )
    write_artifacts(report, args.output_dir)
    print(f"{report.status}: {report.evaluation_id}")
    for failure in report.critical_gate_failures:
        print(f"critical gate: {failure}")
    return 0 if report.status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

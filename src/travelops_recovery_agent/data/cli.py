"""Command-line generation and validation of synthetic datasets."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from travelops_recovery_agent.data.dataset import (
    load_dataset,
    write_dataset,
)
from travelops_recovery_agent.data.generator import generate_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or validate fictional TravelOps datasets."
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate a deterministic synthetic dataset.",
    )
    generate_parser.add_argument(
        "--seed",
        required=True,
        type=int,
        help="Explicit deterministic generation seed.",
    )
    generate_parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Destination JSON file.",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Load and validate an existing dataset.",
    )
    validate_parser.add_argument(
        "path",
        type=Path,
        help="Existing dataset JSON file.",
    )

    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(arguments)

    try:
        if parsed.command == "generate":
            seed = cast(int, parsed.seed)
            output = cast(Path, parsed.output)
            dataset = generate_dataset(seed)
            write_dataset(dataset, output)

            print(
                f"Generated {len(dataset.recovery_cases)} recovery cases "
                f"with seed {seed} at {output}."
            )
            return 0

        path = cast(Path, parsed.path)
        dataset = load_dataset(path)
        print(
            f"Valid dataset: schema {dataset.metadata.schema_version}, "
            f"seed {dataset.metadata.seed}, "
            f"{len(dataset.recovery_cases)} recovery cases."
        )
        return 0
    except (OSError, ValidationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Command-line database workflows for development and testing."""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from functools import partial
from typing import cast

from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from travelops_recovery_agent.application.models import CompleteRecoveryCase
from travelops_recovery_agent.application.services import (
    DatabaseNotEmptyError,
    RecoveryDataService,
    UnsafeDatabaseResetError,
)
from travelops_recovery_agent.core.config import Settings
from travelops_recovery_agent.data.generator import generate_dataset
from travelops_recovery_agent.domain.models import RecoveryCaseId
from travelops_recovery_agent.persistence.session import (
    DatabaseConfigurationError,
    create_database_engine,
    create_session_factory,
)
from travelops_recovery_agent.persistence.unit_of_work import (
    SqlAlchemyRecoveryDataUnitOfWork,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the TravelOps development database."
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    seed_parser = subparsers.add_parser(
        "seed",
        help="Generate and persist a deterministic dataset.",
    )
    seed_parser.add_argument(
        "--seed",
        required=True,
        type=int,
        help="Explicit deterministic generation seed.",
    )
    seed_parser.add_argument(
        "--replace",
        action="store_true",
        help="Atomically replace existing managed records.",
    )

    reset_parser = subparsers.add_parser(
        "reset",
        help="Remove all managed development or test records.",
    )
    reset_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm the destructive reset operation.",
    )

    subparsers.add_parser(
        "counts",
        help="Show row counts for every managed table.",
    )

    show_parser = subparsers.add_parser(
        "show-case",
        help="Retrieve one complete recovery case.",
    )
    show_parser.add_argument(
        "case_id",
        help="Stable recovery-case identifier, such as CASE-0007.",
    )

    return parser


def build_service() -> tuple[RecoveryDataService, Engine]:
    settings = Settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    unit_of_work_factory = partial(
        SqlAlchemyRecoveryDataUnitOfWork,
        session_factory,
    )
    service = RecoveryDataService(
        unit_of_work_factory,
        settings.environment,
    )
    return service, engine


def complete_case_payload(
    complete_case: CompleteRecoveryCase,
) -> dict[str, object]:
    return {
        "recovery_case": complete_case.recovery_case.model_dump(mode="json"),
        "booking": complete_case.booking.model_dump(mode="json"),
        "passengers": [
            passenger.model_dump(mode="json") for passenger in complete_case.passengers
        ],
        "flights": [flight.model_dump(mode="json") for flight in complete_case.flights],
        "disruption": complete_case.disruption.model_dump(mode="json"),
        "policy": complete_case.policy.model_dump(mode="json"),
    }


def main(
    arguments: Sequence[str] | None = None,
    *,
    service: RecoveryDataService | None = None,
) -> int:
    parser = build_parser()
    parsed = parser.parse_args(arguments)

    if parsed.command == "reset" and not cast(bool, parsed.confirm):
        print(
            "error: reset requires --confirm",
            file=sys.stderr,
        )
        return 2

    engine: Engine | None = None

    try:
        if service is None:
            service, engine = build_service()

        if parsed.command == "seed":
            seed = cast(int, parsed.seed)
            replace = cast(bool, parsed.replace)
            dataset = generate_dataset(seed)
            counts = service.seed(dataset, replace=replace)

            if replace:
                print(
                    "Replaced database with "
                    f"{counts.recovery_cases} recovery cases "
                    f"using deterministic seed {seed}."
                )
            else:
                print(
                    f"Seeded {counts.recovery_cases} recovery cases "
                    f"with deterministic seed {seed}."
                )
            return 0

        if parsed.command == "reset":
            counts = service.reset()
            print(f"Reset complete: {counts.recovery_cases} recovery cases remain.")
            return 0

        if parsed.command == "counts":
            print(
                json.dumps(
                    asdict(service.counts()),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        case_id = cast(RecoveryCaseId, parsed.case_id)
        complete_case = service.get_complete_case(case_id)
        if complete_case is None:
            print(
                f"error: recovery case {case_id} was not found",
                file=sys.stderr,
            )
            return 1

        print(
            json.dumps(
                complete_case_payload(complete_case),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (
        DatabaseConfigurationError,
        DatabaseNotEmptyError,
        UnsafeDatabaseResetError,
        ValidationError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        # Avoid printing connection details that might contain credentials.
        print("error: database operation failed", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

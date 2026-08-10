# Phase 0 notes — project foundation

## What this phase shipped

Phase 0 created a minimal installable Python project with:

- A package under [`src/travelops_recovery_agent`](../../src/travelops_recovery_agent)
- Project, build, test, lint, format, and type-check configuration in [`pyproject.toml`](../../pyproject.toml)
- An exact dependency graph in [`uv.lock`](../../uv.lock)
- A Python 3.12.10 development pin in [`.python-version`](../../.python-version)
- A package import smoke test in [`tests/test_package.py`](../../tests/test_package.py)
- Successful wheel and source-distribution builds under the ignored `dist/` directory

The complete reproducible command set is:

```powershell
uv sync --locked --all-groups
uv run --locked python -c "import travelops_recovery_agent; print(travelops_recovery_agent.__file__)"
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked python -m build --no-isolation
```

## How it works

1. `.python-version` asks uv to use Python 3.12.10 for this checkout.
2. `pyproject.toml` declares the project, its supported Python range, dependency ranges, the Hatchling build backend, and development-tool policies.
3. `uv.lock` stores the exact resolved direct and transitive dependency versions plus artifact information.
4. `uv sync --locked --all-groups` creates or updates `.venv` to match the lockfile. `--locked` refuses to update a stale lockfile, and `--all-groups` installs the development tools as well as the package.
5. uv installs this project as an editable package. Imports resolve through the installed distribution boundary while changes under `src/` remain visible immediately.
6. `uv run --locked ...` runs a command with `.venv` on its executable and import paths and also refuses an out-of-date lockfile.
7. `python -m build --no-isolation` asks the locked `build` frontend to invoke the locked Hatchling backend. Hatchling reads the build configuration and produces both distribution formats.

## Concepts I can explain

### What a virtual environment physically provides

On this Windows checkout, `.venv` is a real directory. It contains Python launchers under `.venv/Scripts`, command wrappers such as `pytest.exe`, and a private package installation directory under `.venv/Lib/site-packages`. Activating it mainly changes shell paths so `python`, `pytest`, and similar commands resolve there first; uv can target it without shell activation.

The environment isolates Python packages from global installations, but it does not itself say which versions belong there. It also does not isolate the operating system, network, or database like a container would. The lockfile supplies the version recipe, and synchronization makes the directory match that recipe.

### `pyproject.toml` versus a lockfile

`pyproject.toml` is authored project intent. It contains package identity, the supported Python range, direct dependency constraints, the build-backend contract, and policies for development tools. For example, `pytest>=8.3,<9` allows compatible releases rather than choosing one exact release.

`uv.lock` is generated resolution output. It records the exact direct and transitive packages selected from those constraints, such as pytest 8.4.2 in the verified environment, along with artifact data needed to repeat installation. Editing intent requires changing `pyproject.toml` and deliberately regenerating the lock. A virtual environment is disposable local state; both configuration files are durable project inputs intended for version control.

### Why a `src/` layout catches packaging mistakes

Python normally puts the current working directory on its import path. With a flat layout, a test run from the repository root can import a package directory even when the built distribution forgot to include it. Placing the package under `src/` removes that accidental shortcut. The package must be installed, or `src/` must be added explicitly, before it imports. The final smoke test runs through the installed editable distribution, and the archive inspection confirmed that the wheel really contains the package.

### What a build backend does

The `build` command is a build frontend: it requests standard build operations. Hatchling is the backend named by the `[build-system]` table. It interprets package-selection and metadata configuration, collects files, writes distribution metadata, and creates the archives. Keeping the backend contract in `pyproject.toml` lets any PEP 517-compatible frontend build the project without importing application code or relying on a bespoke setup script.

### What wheels and source distributions contain

The generated wheel is `py3-none-any`, meaning it contains pure Python that is not tied to one operating system or CPU architecture. Inspection showed the package `__init__.py`, the `py.typed` marker, and installation metadata. Installers can unpack a wheel directly without rebuilding the project.

The `.tar.gz` source distribution contains the package source plus the test, README, `pyproject.toml`, and source-package metadata. An installer can use those inputs and the declared backend to build a wheel. A source distribution is not the same as the Git repository: ignored local environments, caches, and generated `dist/` artifacts are absent.

### Tests, linting, formatting, and static type checking

| Check | Question it answers | Phase 0 evidence |
| --- | --- | --- |
| Tests | Does exercised behavior produce the expected result? | pytest imported the package and checked its module name. |
| Linting | Does static source inspection reveal selected defects or maintenance problems? | Ruff checked syntax, names, imports, modernization, bug patterns, simplifications, and Ruff diagnostics. |
| Formatting | Does source text follow one canonical layout? | `ruff format --check` verified layout without rewriting files. |
| Static type checking | Are values used consistently with their declared or inferred types across possible paths? | Strict mypy checked both source files without executing them. |

These checks overlap but are not substitutes. A perfectly formatted function can return the wrong value; a passing test suite may miss an untested type error; type-correct code may contain an unused import or incorrect business rule.

### Project configuration versus application code

Project configuration describes how external tools treat the repository: package metadata, dependency constraints, supported Python, file discovery, lint rules, format style, strictness, and build selection. It belongs in `pyproject.toml`, `.python-version`, and the generated lockfile.

Application code implements TravelOps behavior and belongs under `src/travelops_recovery_agent`. It should not contain pytest discovery rules, manipulate the interpreter environment, configure Ruff or mypy, or choose its own build backend. Phase 0 intentionally leaves the package with only a docstring because API, configuration, logging, airline rules, persistence, and agent behavior belong to later phases.

## Decisions I made

- [D-009](../decisions.md#d-009--use-uv-for-the-reproducible-python-environment) selects uv, a project-local `.venv`, `uv.lock`, and Python 3.12.10.
- [D-010](../decisions.md#d-010--package-from-src-with-hatchling) selects the `src/` layout, typed-package marker, and Hatchling build backend.
- Ruff enables a focused defect-oriented rule set instead of every available rule. New rule families can be adopted deliberately when they add signal rather than boilerplate.
- Strict mypy covers both `src/` and `tests/`, so the test boundary is held to the same typing standard as package code.

## Tests and demonstrations

- `uv lock --check` proved the lockfile matched project intent.
- `uv sync --locked --all-groups` reproduced the environment from the lockfile.
- The import command printed the package file under `src/travelops_recovery_agent`.
- pytest collected one smoke test and passed it.
- Ruff lint reported all checks passed.
- Ruff format check reported all applicable files already formatted.
- Strict mypy reported no issues in the package and test source files.
- The build produced `travelops_recovery_agent-0.1.0-py3-none-any.whl` and `travelops_recovery_agent-0.1.0.tar.gz`.
- Archive inspection confirmed the expected installable and source inputs were present.

## What failed or surprised me

The first successful `python -m build` used PEP 517 isolation, which installed Hatchling from its allowed range into a temporary environment. That is standard and safe, but it meant the exact backend used by that command was not supplied by this project's synchronized development lock. Hatchling was therefore added to the development dependency group, the lockfile was regenerated, and the verified build now uses `--no-isolation` to invoke the locked backend.

An early read-only PowerShell probe also failed because a colon immediately after an interpolated variable was parsed as part of the variable name. Delimiting the variable fixed the probe; it made no repository changes.

## Remaining limitations

- The package has no runtime behavior beyond being importable.
- There is no API, server, application configuration, logging, request ID, database, airline domain model, synthetic data, frontend, agent framework, model integration, authentication, or Docker addition.
- The Python support declaration is intentionally limited to 3.12 for this phase.
- The lockfile reproduces Python dependencies, not the operating system or non-Python system libraries.
- Release publishing, CI, and container delivery remain future work.

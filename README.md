# TravelOps Recovery Agent

A learning-first, production-minded agentic AI project for resolving synthetic airline disruptions. The application will collect booking and flight information, search and validate recovery options, explain its recommendation, and prepare a rebooking that only a human operator can approve and execute.

The project is built in small, shippable phases. A phase is complete only when the repository is runnable, its tests pass, and the concepts introduced in that phase can be explained clearly.

## The problem

Airline operations staff often switch between booking, flight-status, policy, and availability systems to resolve a disrupted journey. That makes the process slow, difficult to audit, and vulnerable to missed constraints.

TravelOps puts the investigation in one visual workflow. The agent coordinates read-only tools and prepares a recommendation; deterministic application code validates availability, connection times, permissions, and write operations; the operator remains responsible for approval.

## How it will work

```mermaid
flowchart TD
    A["Flight delayed or cancelled"] --> B["Case appears in the operations dashboard"]
    B --> C["Agent loads the booking and flight status"]
    C --> D["Agent checks policy and searches alternatives"]
    D --> E["Application validates seats, connections and ticket rules"]
    E --> F{"Valid option available?"}
    F -- "No" --> G["Escalate to an operator with evidence"]
    F -- "Yes" --> H["Show ranked options and recommendation"]
    H --> I{"Operator decision"}
    I -- "Reject or edit" --> D
    I -- "Approve" --> J["Recheck availability and execute once"]
    J --> K["Update the booking and write an audit record"]
```

## What this project is designed to teach

- The difference between deterministic workflows and agent-controlled decisions
- Typed tool design and structured model outputs
- A small agent loop before using an orchestration framework
- LangGraph state, nodes, edges, routing, interrupts, and checkpoints
- Durable execution that survives process and browser restarts
- Streaming agent progress to a React interface
- Human approval for consequential actions
- Idempotency, authorization, retries, and safe failure handling
- Task-level evaluation, tracing, latency, token, and cost measurement
- Shipping a tested full-stack AI application with Docker and CI

## Planned stack

| Concern | Initial choice |
| --- | --- |
| Backend | Python, FastAPI, Pydantic |
| Agent orchestration | LangGraph with minimal LangChain Core integration |
| Persistence | PostgreSQL, SQLAlchemy, Alembic |
| Frontend | React, TypeScript, Vite |
| Live updates | Server-Sent Events initially |
| Quality | pytest, Ruff, mypy, frontend tests |
| Delivery | Docker Compose and GitHub Actions |

Exact model and deployment providers are intentionally deferred until the application has a provider-independent model boundary.

## Learning roadmap

| Phase | Shippable result |
| --- | --- |
| 0 | Reproducible Python project with quality gates |
| 1 | Typed API, configuration, health endpoint, and logging |
| 2 | Synthetic airline domain and disruption-case simulator |
| 3 | PostgreSQL persistence and tested service boundaries |
| 4 | Typed read-only operational tools |
| 5 | Visual operator dashboard without an LLM dependency |
| 6 | Small manual model-and-tool loop |
| 7 | Explicit LangGraph workflow with minimal LangChain integration |
| 8 | Durable checkpoints and live UI progress |
| 9 | Validated recommendations and evidence |
| 10 | Prepare, approve, and execute rebooking safely |
| 11 | Failure testing, security, evaluation, and first portfolio release |
| 12 | Context engineering and controlled tool exposure |
| 13 | Explicit planning, progress tracking, and replanning |
| 14 | Parallel investigation with deadlines and partial results |
| 15 | Scoped memory and preference management |
| 16 | Model routing and cost-quality budgets |
| 17 | Trajectory evaluation and regression gates |
| 18 | Evidence-grounded policy RAG as an agent tool |
| 19 | Measured single-agent versus multi-agent experiment |
| 20 | MCP server and reusable operational capabilities |

The core-release contract and gates are in [docs/plan.md](docs/plan.md). The advanced track is in [docs/roadmap.md](docs/roadmap.md), and a shorter index of every phase is in [docs/project-phases.md](docs/project-phases.md).

## Project documents

- [Build plan](docs/plan.md) — learning contract, scope, architecture, and phase gates
- [Advanced roadmap](docs/roadmap.md) — Phases 12–20 and their experiment gates
- [Project phases](docs/project-phases.md) — quick phase-by-phase reference
- [Architecture](docs/architecture.md) — system boundaries and responsibility split
- [UI specification](docs/ui.md) — operator screens, interaction model, live events, and UI learning track
- [Decisions](docs/decisions.md) — design choices and their reasons
- [Progress](docs/progress.md) — current phase, evidence, and session handoffs
- [Phase notes](docs/notes/README.md) — learning-note format

## Synthetic dataset commands

```powershell
# Generate ten deterministic fictional recovery cases
uv run --locked python -m travelops_recovery_agent.data.cli generate `
  --seed 42 `
  --output synthetic-cases.json

# Load the file and validate every object and relationship
uv run --locked python -m travelops_recovery_agent.data.cli validate `
  synthetic-cases.json
```

## PostgreSQL development commands

PostgreSQL runs in Docker while the Python application remains local. The
container binds to `127.0.0.1:55432`, avoiding a desktop PostgreSQL instance on
the default port. Supply passwords through environment variables; never place
them in committed files or shell history.

```powershell
# Enter the database password through Windows' masked credential dialog
$credential = Get-Credential -UserName travelops `
  -Message "Enter the TravelOps development database password"
$password = $credential.GetNetworkCredential().Password
$encodedPassword = [uri]::EscapeDataString($password)

$env:TRAVELOPS_POSTGRES_PASSWORD = $password
$env:TRAVELOPS_DATABASE_URL = `
  "postgresql+psycopg://travelops:{0}@127.0.0.1:55432/travelops" `
  -f $encodedPassword
$env:TRAVELOPS_ENVIRONMENT = "development"

# Start PostgreSQL, wait for healthy, and apply explicit migrations
docker compose up -d postgres
docker compose ps
uv run --locked alembic upgrade head
uv run --locked alembic current

# Load and inspect the canonical Phase 2 dataset
uv run --locked python -m travelops_recovery_agent.persistence.cli seed --seed 42
uv run --locked python -m travelops_recovery_agent.persistence.cli counts
uv run --locked python -m travelops_recovery_agent.persistence.cli show-case CASE-0007

# Normal repeat seeding is refused; replacement must be explicit
uv run --locked python -m travelops_recovery_agent.persistence.cli seed `
  --seed 42 --replace

# Reset is restricted to development/test and requires confirmation
uv run --locked python -m travelops_recovery_agent.persistence.cli reset --confirm

# Stop the service while retaining its named data volume
docker compose down
```

Real-database tests require a separate URL whose database name is exactly
`travelops_test`:

```powershell
$env:TRAVELOPS_TEST_DATABASE_URL = `
  "postgresql+psycopg://travelops:{0}@127.0.0.1:55432/travelops_test" `
  -f $encodedPassword
uv run --locked pytest -m integration
```

The complete explanation is in [docs/notes/phase-3.md](docs/notes/phase-3.md).

## Read-only operational tool commands

Phase 4 tools run directly with normal Python and PostgreSQL; no model, agent
framework, or new API route is involved. Configure `TRAVELOPS_DATABASE_URL` as
shown above, migrate and seed the database, then run:

```powershell
# Inspect stable input, success, failure, context, and permission schemas
uv run --locked python -m travelops_recovery_agent.tools.cli catalog

# Read minimized booking and deterministic flight/policy facts
uv run --locked python -m travelops_recovery_agent.tools.cli `
  get-booking BKG-0001
uv run --locked python -m travelops_recovery_agent.tools.cli `
  get-flight-status FLT-NV101
uv run --locked python -m travelops_recovery_agent.tools.cli `
  get-disruption-policy --case-id CASE-0001

# Generate a candidate, then validate its stored flights separately
uv run --locked python -m travelops_recovery_agent.tools.cli `
  search-alternative-itineraries ZRA XLC `
  2026-01-15T11:00:00Z 2026-01-15T18:00:00Z 1
uv run --locked python -m travelops_recovery_agent.tools.cli `
  validate-itinerary CAND-FLT-NV101-FLT-NV102 1 `
  FLT-NV101 FLT-NV102
```

Global options before the command can set `--actor-id`, `--correlation-id`, and
`--timeout-seconds`. Every call grants only that tool's required permission and
returns a typed JSON success or failure envelope with safe audit metadata. See
[docs/notes/phase-4.md](docs/notes/phase-4.md) for the complete boundary model.

## Phase 5 operator dashboard

The dashboard is a manual operations console, not a chatbot. With PostgreSQL
migrated and seeded as documented above, start FastAPI and Vite in separate
terminals:

```powershell
# Terminal 1 — serve the versioned browser API
uv run --locked uvicorn travelops_recovery_agent.api.app:create_app `
  --factory --host 127.0.0.1 --port 8000

# Terminal 2 — serve React and proxy /api calls to FastAPI
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open the Vite address and use `/cases`. The queue and `/cases/:caseId`
workspace reload server-owned facts after refresh. Operators can inspect the
passenger party, journey, disruption, status and policy, search scheduled
alternatives, and request deterministic validation. No action mutates a booking
or recovery case. See [the visual Phase 5 workflow](docs/notes/phase-5.md).

## Current status

Phase 5 implements the visual manual-investigation baseline. A typed React UI
uses four read-only FastAPI routes to load the queue and case workspace, search
deterministic alternatives, and display structured validation. Phase 4 tools
remain available for future agents, but browser routes call application services
directly. No LLM, agent loop, recommendation, approval or booking write exists.

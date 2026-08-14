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

## Phase 6 recorded agent loop

Phase 6 adds the first explicit model-and-tool loop without LangGraph or
PydanticAI. Pydantic validates the provider-independent decisions and transient
run state; ordinary Python performs the bounded loop; the existing Phase 4
adapters remain the only executable tools.

Run the deterministic demonstration without a model server or database:

```powershell
# Show the recorded scenarios
uv run --locked python -m travelops_recovery_agent.agent.cli --list

# Model decision -> tool result -> model finish
uv run --locked python -m travelops_recovery_agent.agent.cli `
  successful_investigation

# Inspect bounded failure behavior
uv run --locked python -m travelops_recovery_agent.agent.cli `
  repeated_tool_call
uv run --locked python -m travelops_recovery_agent.agent.cli `
  malformed_exhaustion
```

An optional local-only Ollama adapter implements the same model interface. It
uses Ollama's HTTP API directly, adds no SDK dependency, accepts only a loopback
HTTP endpoint, and requires the caller to choose a model explicitly. No local
model is configured as a trusted default: the available 7B and 14B models did
not reliably satisfy the strict decision contract during the Phase 6 smoke
check. Recorded fixtures are therefore the reproducible completion evidence.

See [the Phase 6 notes](docs/notes/phase-6.md) for the loop, typed state,
budgets, safety boundaries, diagrams, and the planned Phase 7 comparison.

## Phase 7 LangGraph workflow

Phase 7 reproduces the complete Phase 6 behavior as a compiled LangGraph with
typed state, runtime context, eight named nodes, conditional edges, explicit
completion and failure terminals, and complete state inspection after every
node. The model, dispatcher, tools, fingerprints, budgets, safe failures, and
domain validation remain the existing application-owned implementations.

The deterministic equivalence gate runs every recorded scenario through the
manual loop and graph independently and requires byte-for-byte identical trusted
terminal state:

```powershell
uv run --locked pytest tests/agent/test_graph.py
```

LangGraph is the orchestration runtime; the full LangChain agent framework is
not used. Application code directly uses only LangChain Core's `RunnableConfig`
type for strict graph invocation typing. Phase 8 now optionally compiles this
same graph with the official PostgreSQL checkpointer.

See [the detailed Phase 7 learning notes](docs/notes/phase-7.md) for the complete
node map, state evolution, provider and tool boundaries, terminology, decisions,
equivalence proof, and Phase 7/Phase 8 comparison.

## Phase 8 durable investigations

After applying migration `0002`, the Phase 5 case workspace can start a durable
read-only investigation. PostgreSQL stores workflow lifecycle records, safe
events, and LangGraph checkpoints in the dedicated `workflow` schema. The run ID
is retained in the case URL; refresh restores the authoritative snapshot and
SSE resumes from an event cursor or `Last-Event-ID`.

The API supports start, inspect, stream, cancel, and resume under
`/api/v1`. Cancellation is cooperative at graph boundaries. A synchronous model
or database call already executing cannot necessarily be forcibly interrupted.
No model is configured by default; an unconfigured investigation fails safely.

See [the detailed Phase 8 learning notes](docs/notes/phase-8.md) for checkpoint
storage, identity, restart semantics, runtime reconstruction, safe events,
reconnect, retention, tests, and diagrams.

## Phase 9 validated recommendations

After migration `0003` and deterministic seeding, every case workspace contains
a repository-grounded recommendation. Application code validates stored-flight
existence/status, route and operational times, a 45-minute synthetic connection
minimum, complete-group seats, ticket rules, and disruption policy. Only options
that pass every check can enter the stable ranking.

The result shows evidence references, visible ranking inputs, tradeoffs, other
validated options, and rejected options. Complete evidence with no passing
option produces `no_safe_option`; missing required evidence produces
`insufficient_evidence`. Both escalate without guessing.

```powershell
# With TRAVELOPS_DATABASE_URL configured as above
uv run --locked alembic upgrade head
uv run --locked python -m travelops_recovery_agent.persistence.cli seed `
  --seed 42 --replace
uv run --locked uvicorn travelops_recovery_agent.api.app:create_app `
  --factory --host 127.0.0.1 --port 8000

# In another terminal
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open `/cases/CASE-0001`, or inspect
`GET /api/v1/recovery-cases/CASE-0001/recommendation`. The production workflow
uses a checkpointed deterministic recommendation node and needs no hosted model.
It remains read-only.

See [the Phase 9 learning notes](docs/notes/phase-9.md) for the
candidate/validation/recommendation split, traceability, ranking, missing
evidence, durable resume behavior, and Phase 10 boundary.

## Phase 10 approved synthetic rebooking

After Alembic `0004`, the case workspace can prepare an expiring proposal from
the validated recommendation. Approval binds to its exact version and itinerary.
Execution then locks and revalidates the evidence, applies one provider-neutral
synthetic booking change, and writes an immutable audit.

```powershell
# With TRAVELOPS_DATABASE_URL configured as in the PostgreSQL section
docker compose up -d postgres
uv run --locked alembic upgrade head
uv run --locked python -m travelops_recovery_agent.persistence.cli seed --seed 42
uv run --locked uvicorn travelops_recovery_agent.api.app:create_app `
  --factory --host 127.0.0.1 --port 8000

# In another terminal
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open `/cases/CASE-0002` for a deterministic replacement example. The demo UI
uses explicit synthetic actor headers; they illustrate authorization context,
not production authentication.

## Phase 11 first-release baseline

Version `0.1.0` freezes dataset `phase-11.0.0` with seed `42`. The deterministic
benchmark contains 22 synthetic cases across routine, complex,
failure-recovery, safety, authorization, and adversarial slices. It declares its
thresholds before running, emits JSON/Markdown/JSONL artifacts, and exits
non-zero when a critical safety gate fails.

```powershell
uv sync --locked --all-groups
uv run --locked python -m travelops_recovery_agent.evaluation.cli validate
uv run --locked python -m travelops_recovery_agent.evaluation.cli run `
  --seed 42 --output-dir reports
```

The frozen deterministic run completed 22/22 cases with 100% task completion,
outcome accuracy, valid tool arguments, escalation accuracy, and approval
integrity. It recorded seven approved synthetic writes, zero writes without
valid approval, zero duplicate writes, zero unauthorized execution attempts,
and seven blocked hostile requests. It made zero model calls, so measured token
usage and cost are zero for this run; that does not claim anything about an
optional live model. Harness latency is machine-dependent and is recorded in
[the generated report](reports/phase-11-evaluation.md).

The benchmark demonstrates the declared deterministic synthetic cases and
safety counters only. It does not demonstrate real-airline correctness,
production scale, live-model semantic quality, or statistical generalization.
See [the Phase 11 notes](docs/notes/phase-11.md) and
[release notes](docs/release-notes/v0.1.0.md).

## Phase 12 governed model context

Phase 12 adds a provider-neutral context boundary without changing the frozen
Phase 11 workflow or its deterministic safety enforcement. Every candidate
evidence item carries case and authorization scope, task/node applicability,
authority, timestamps and freshness, sensitivity, a labelled token estimate,
priority/relevance, conflicts, supersession, and durable fact references.
Selection is deterministic and records a reason for every included, excluded,
compacted, or rejected item. Mandatory authorization, approval, safety, and
execution evidence is never truncated: if it cannot fit, the model call stops
safely.

Tool schemas are governed by task, workflow node, role, permission, approval,
and workflow state. The policy is deny-by-default and exposes the minimum
matching schema. Visibility remains separate from the existing server-side
authorization, exact approval, revalidation, idempotency, and transaction
boundary.

```powershell
uv run --locked python -m travelops_recovery_agent.context_evaluation.cli validate
uv run --locked python -m travelops_recovery_agent.context_evaluation.cli run `
  --seed 42 --output-dir reports

# Start the developer API, then open /developer/context
$env:TRAVELOPS_ENVIRONMENT = "development"
uv run --locked uvicorn travelops_recovery_agent.api.app:create_app `
  --factory --host 127.0.0.1 --port 8000
```

The reviewed `phase-12.0.0` experiment passed 13/13 cases. Against the
Phase 11-style full-context comparison, selective context retained 100% task
and outcome accuracy, achieved 100% mandatory-evidence coverage, reduced the
provider-neutral context estimate from 21,127 to 8,721 tokens (58.72%), rejected
all stale, unauthorized, and cross-case evidence, and exposed zero prohibited
tools. Estimates use the explicitly labelled `estimated_characters_div_4`
method; no provider tokenizer or live model was used. See
[the Phase 12 notes](docs/notes/phase-12.md) and the generated
[comparison report](reports/phase-12-context-evaluation.md).

### Phase 12 portfolio evidence

![Context inspector and budget accounting](docs/screenshots/phase-12-context-budget.png)

![Evidence inclusion and exclusion reasons](docs/screenshots/phase-12-evidence-reasons.png)

![Governed tool exposure](docs/screenshots/phase-12-tool-governance.png)

![Phase 11 full-context versus Phase 12 selective-context comparison](docs/screenshots/phase-12-evaluation-comparison.png)

## Complete local stack

Set a strong alphanumeric database password outside committed files, then start
PostgreSQL, one-shot migrations, FastAPI, and the React/nginx frontend with
health-checked ordering:

```powershell
$env:TRAVELOPS_POSTGRES_PASSWORD = "choose-a-strong-local-password"
docker compose up --build -d
docker compose --profile tools run --rm seed
docker compose ps
```

Open `http://127.0.0.1:8080`. The short demo path is: Cases → `CASE-0002` →
prepare proposal → approve the exact version → execute → inspect immutable audit
→ Evaluation. Stop with `docker compose down`; add `--volumes` only when you
explicitly intend to delete the local database.

The demo uses explicit actor headers, synthetic data, and a synthetic execution
provider. Production still requires authenticated tenant-scoped identities,
real-provider idempotency and reconciliation, inventory holds, managed secrets,
TLS/network policy, backups, durable distributed workers, load/chaos testing,
security review, governed telemetry, alerting, and incident response.

## Current status

Phase 12 is complete. Phase 11 remains frozen as the v0.1.0 comparison baseline.
The selective layer is explicit and removable; deterministic application rules
remain authoritative.
The original itinerary and immutable audit remain intact; exact human approval,
fresh transactional revalidation, database idempotency, concurrency protection,
and all Phase 6–10 equivalence behavior remain release invariants. No real
airline or reservation system is contacted.

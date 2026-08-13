# Phase 4 notes — typed read-only operational tools

## How to read these notes

This document records the project at the end of Phase 4. Later phases may add
HTTP view models, a frontend, a model loop, orchestration, richer validation,
and write workflows, but the explanations below describe the read-only tool
boundary that Phase 4 introduced.

The steps are presented in dependency order rather than file-alphabetical
order. Each step explains why the work was necessary, what was implemented,
how the pieces operate, and what evidence proved the result.

## Phase in brief

### Purpose

Phase 4 made existing TravelOps business data safely usable by future automated
callers. Its purpose was not to add an AI model. It created five narrow,
deterministic read-only capabilities with stable input, output, permission,
deadline, error, and audit contracts that work through normal Python.

The phase also protected the database boundary. A future model may request a
tool call, but it cannot receive a SQLAlchemy session, execute arbitrary SQL,
skip validation, grant itself permission, extend a deadline, or declare an
itinerary valid through prompt wording.

### Result

The phase delivered:

- Shared immutable execution-context, permission, error, audit, success, and
  failure contracts
- Strict typed input and output models for every operational tool
- Application-owned query results and an `OperationalQueryService`
- Narrow repository queries implemented through the Phase 3 unit of work
- `get_booking`
- `get_flight_status`
- `get_disruption_policy`
- `search_alternative_itineraries`
- `validate_itinerary`
- Deterministic domain rules for flight existence, route continuity, and
  chronological order
- Explicit deferral of seat inventory, ticket rules, and minimum-connection
  policy that the current dataset cannot prove
- A stable schema registry that discovers tools without executing them
- A direct command-line runner that demonstrates every tool without an LLM
- Unit, contract, application, CLI, and real-PostgreSQL integration tests
- Updated architecture, decision, progress, README, and learning documentation

The final Phase 4 gate passed all 249 tests without warnings. Seventeen of those
tests exercised the isolated real PostgreSQL database. Ruff lint, Ruff format,
strict mypy, locked dependency synchronization, package import, Alembic revision
inspection, Compose health, real-socket `GET /health`, and wheel/source builds
also passed.

### Deliberate boundary

Phase 4 added read-only operational capabilities, not a product interface or an
agent. It added no React frontend, new business API routes, model provider,
prompt loop, LangChain, LangGraph, workflow checkpoint, background worker,
recommendation ranking, approval flow, rebooking proposal, or database write
tool.

The synthetic dataset contains scheduled flights and disruption evidence. It
does not contain seat inventory, prices, ticket restrictions, or an airport
minimum-connection policy. Phase 4 therefore reports those checks as
`not_evaluated` or deferred instead of inventing business facts.

## Operational tool workflow

```mermaid
flowchart LR
    CALLER["CLI or future caller"] --> INPUT["Strict typed input"]
    CALLER --> CONTEXT["Actor, correlation, permission, deadline"]
    INPUT --> ADAPTER["Read-only tool adapter"]
    CONTEXT --> ADAPTER
    ADAPTER -->|"authorized and in time"| SERVICE["OperationalQueryService"]
    SERVICE --> UOW["Application-owned unit-of-work boundary"]
    UOW --> REPOSITORY["Narrow repository protocol"]
    REPOSITORY --> PERSISTENCE["SQLAlchemy repository"]
    PERSISTENCE --> POSTGRES[("PostgreSQL")]
    SERVICE --> RULES["Deterministic domain rules"]
    SERVICE --> ADAPTER
    ADAPTER --> RESULT["Typed success or safe failure + audit"]
```

The adapter is the safety boundary. It validates caller-controlled input and
checks permission and deadline before application or persistence access. The
application service coordinates retrieval and deterministic decisions. The
repository performs only named business reads, and persistence alone knows
SQLAlchemy and PostgreSQL.

## Candidate search and validation workflow

```mermaid
flowchart TD
    REQUIREMENTS["Route, time window, passengers, max connections"] --> SEARCH["Search stored scheduled flights"]
    SEARCH --> CANDIDATES["Deterministically ordered candidates"]
    CANDIDATES --> DEFERRED1["Inventory and ticket rules: not evaluated"]
    CANDIDATE["Candidate ID + ordered flight IDs"] --> LOAD["Load only named stored flights"]
    LOAD --> VALIDATE["Existence, route continuity, chronological order"]
    VALIDATE --> RULE_RESULTS["Passed, failed, or not evaluated per rule"]
    RULE_RESULTS --> DEFERRED2["Connection policy, inventory, ticket rules: deferred"]
```

Search and validation answer different questions. Search finds possible
scheduled routes. Validation proves only the structural rules supported by
stored evidence. Neither operation claims that seats exist or that a ticket can
be changed.

## Artifact map

| Artifact | Responsibility in Phase 4 |
| --- | --- |
| `application/query_models.py` | Holds application-owned read results independent of tools and persistence records |
| `application/query_services.py` | Coordinates narrow reads, derives flight status, generates candidates, and invokes domain validation |
| `application/repositories.py` | Declares the exact repository operations required by application workflows |
| `persistence/repositories.py` | Implements those reads with SQLAlchemy and explicit record/domain mapping |
| `domain/itinerary_validation.py` | Owns deterministic itinerary rules that must remain true for every caller |
| `tools/contracts.py` | Defines shared context, permissions, errors, audit metadata, and result envelopes |
| `tools/models.py` | Defines strict input and minimized output contracts for all five tools |
| `tools/adapters.py` | Enforces boundary checks and translates application results into safe tool results |
| `tools/registry.py` | Publishes stable inspectable JSON schemas without granting execution |
| `tools/cli.py` | Composes PostgreSQL, services, and adapters for direct no-LLM demonstrations |
| `tests/domain/` | Proves deterministic business validation rules |
| `tests/application/` | Proves service coordination without a real database |
| `tests/tools/` | Proves schemas, guardrails, results, errors, audit data, CLI, and determinism |
| `tests/integration/` | Proves the narrow repository reads against isolated PostgreSQL |
| `docs/decisions.md` | Records the accepted tool-boundary choices and their consequences |

## Step-by-step implementation

### Step 1 — Inspect Phase 3 capabilities and define the tool boundary

**Why this step was taken**

Tools needed to reuse trusted domain, service, transaction, mapping, and
PostgreSQL behavior rather than bypassing it. Inspection was also necessary to
identify what the synthetic dataset could honestly answer before defining
public contracts.

**What was implemented**

The Phase 4 boundary was defined as small adapter objects that call application
query services. Five read-only operations were selected: booking retrieval,
flight status, disruption policy, alternative search, and itinerary validation.

The inspection confirmed that the dataset provides bookings, minimized
passenger identity, ordered segments, scheduled flights, disruptions, recovery
cases, and structured policy facts. It also confirmed that inventory, prices,
ticket rules, and minimum-connection requirements were absent.

**How it was implemented**

The existing Phase 3 unit-of-work and application-owned repository protocol were
kept as the persistence boundary. Phase 4 added only named reads required by the
five tools. No generic CRUD repository, arbitrary filter language, SQL tool, or
session exposure was introduced.

Small callable classes were chosen for adapters because they can hold the query
service and clock dependencies while exposing one explicit `invoke()` method.
Normal Python and Pydantic keep the boundary independent of future agent
frameworks.

**Evidence**

Source inspection showed that tool modules import application and domain types
but no SQLAlchemy records, sessions, or engines. Registry tests also prove that
generic query and future write tools are not discoverable.

### Step 2 — Define shared tool context, permissions, errors, and audit contracts

**Why this step was taken**

Every tool needs the same answers to four questions: who is calling, what may
they do, when must the work finish, and how is the result represented safely.
Without a shared contract, individual adapters could implement inconsistent or
prompt-dependent security behavior.

**What was implemented**

[`tools/contracts.py`](../../src/travelops_recovery_agent/tools/contracts.py)
added:

- `ToolPermission` with one narrow permission per tool
- `ToolExecutionContext` with actor ID, correlation ID, explicit permissions,
  and a timezone-aware absolute deadline
- `ToolErrorCode` for invalid input, not found, permission denied, deadline
  exceeded, and dependency failure
- `ToolAuditOutcome` for succeeded, rejected, and failed calls
- `ToolAuditMetadata` with safe operational timing and identity facts
- `ToolError`, `ToolSuccess`, `ToolFailure`, and the generic `ToolResult` union
- `ToolContractModel`, a strict immutable Pydantic base

**How it was implemented**

Pydantic models use `extra="forbid"` so callers cannot smuggle credentials,
database URLs, undeclared authority, or unrelated metadata through the
boundary. They are frozen after validation so downstream code cannot silently
change the authorized context.

Datetime validators reject naive values. Audit validation prevents completion
from preceding start time and prevents negative duration. Error messages are
small public explanations rather than raw internal exceptions.

An absolute deadline was chosen instead of passing a fresh relative timeout to
each layer. Every check therefore compares against the same finish-by moment and
does not accidentally restart the caller's time budget.

**Evidence**

Contract tests prove the exact permission and error vocabularies, timezone
requirements, blank-field rejection, unknown-field rejection, safe audit
fields, timing invariants, typed serialization, and rejection of injected
credential metadata.

### Step 3 — Add application-owned query models and repository operations

**Why this step was taken**

Existing Phase 3 retrieval focused on complete recovery cases and persistence
administration. The tools needed narrower read views without receiving ORM
records or duplicating relationship assembly in each adapter.

**What was implemented**

[`application/query_models.py`](../../src/travelops_recovery_agent/application/query_models.py)
added application results for:

- A complete booking with passengers and ordered flights
- A flight with related disruptions
- A derived operational flight status
- A resolved recovery case, disruption, and policy
- Alternative-search requirements and candidate itineraries
- Structured itinerary-validation results

[`application/repositories.py`](../../src/travelops_recovery_agent/application/repositories.py)
added named operations for complete bookings, flights with disruptions, policy
resolution, flights in a bounded window, and flights by explicit identifiers.

**How it was implemented**

Application result models are immutable dataclasses containing domain objects.
They express what a use case needs without importing Pydantic tool models or
SQLAlchemy persistence records.

The repository remains a protocol owned by the application layer. The
SQLAlchemy repository implements its exact method signatures, performs ordered
queries and joins, and maps loaded records back into validated domain models.
Callers continue to receive repository access only inside the Phase 3 unit of
work.

This dependency direction was chosen so storage code conforms to application
needs. Changing a join or table layout does not alter a tool contract, and a
tool cannot widen its own database access.

**Evidence**

Application tests use repository stubs to prove coordination without
PostgreSQL. Integration tests seed the isolated database and verify complete
booking retrieval, ordered disruption evidence, policy resolution, bounded
flight search, explicit-ID retrieval, missing records, and deterministic order.

### Step 4 — Implement `get_booking`

**Why this step was taken**

A recovery investigation begins with the passenger party and its current
journey. The caller needs one coherent view, but it does not need persistence
records or unrestricted passenger details.

**What was implemented**

The booking tool accepts one stable `BookingId`. Its output contains:

- The booking ID
- Passenger IDs and display names only
- Ordered itinerary segments
- Flight carrier, number, origin, destination, and scheduled UTC-aware times

`OperationalQueryService.get_booking()` delegates to the complete-booking
repository operation, and `GetBookingTool` maps the application result into the
minimized public model.

**How it was implemented**

The input reuses the domain identifier pattern so malformed identifiers fail
during Pydantic validation. The adapter checks `booking:read` and the deadline
before calling the service. A missing record becomes a typed, non-retryable
`not_found` failure. Unexpected dependency exceptions become a generic
retryable dependency failure without exception text.

Passenger output deliberately contains no contact, payment, document, loyalty,
or persistence-specific fields. Returning structured segment fields instead of
formatted journey prose lets later callers display or reason over facts without
parsing text.

**Evidence**

Tests prove minimized passenger output, ordered itinerary mapping, strict
schemas, malformed input rejection before service access, permission denial,
pre-call and post-call deadline handling, typed not found, secret-safe dependency
failure, deterministic results, and audit metadata.

### Step 5 — Implement `get_flight_status`

**Why this step was taken**

The domain stored scheduled flight facts and disruptions but did not store a
separate real-time status feed. A useful Phase 4 tool therefore needed the
smallest honest deterministic status derived from existing evidence.

**What was implemented**

The flight-status tool accepts one stable `FlightId` and returns scheduled
flight facts, a status of `scheduled`, `delayed`, or `cancelled`, delay minutes
or cancellation reason where applicable, ordered related disruptions, and an
explicit `synthetic_dataset` source.

The repository retrieves a flight with related disruption evidence.
`OperationalQueryService` derives the operational status, and the adapter maps
the result into the public schema.

**How it was implemented**

Disruptions are ordered by occurrence time and stable ID. Cancellation evidence
takes precedence because a cancelled flight is not merely delayed. Otherwise,
the largest stored delay is returned. With neither cancellation nor delay
evidence, the flight remains scheduled. A missed connection remains related
evidence but does not rewrite the stored flight into an invented status.

This derivation was placed in the application service because it coordinates
stored domain evidence into an operational read result. The adapter retains
only boundary behavior, and no external-airline integration is implied.

**Evidence**

Tests prove delayed, cancelled, scheduled, and missed-connection cases;
deterministic evidence order; authorization and deadline checks before service
access; missing-flight handling; safe dependency failures; and stable output.
Real PostgreSQL tests prove the required flight/disruption query.

### Step 6 — Implement `get_disruption_policy`

**Why this step was taken**

An operator or future agent needs the applicable recovery rules as structured
facts. Policy retrieval must be explicit about whether the caller starts from a
recovery case or a disruption and must not become an unrestricted text-search
or future RAG system.

**What was implemented**

The input uses a discriminated union with exactly one of:

- `{ "type": "recovery_case", "id": ... }`
- `{ "type": "disruption", "id": ... }`

The result contains the resolved case, disruption, affected flight and policy
identifiers, policy name and summary, applicable disruption types,
rebooking-window hours, and next-day allowance.

**How it was implemented**

The explicit `type` discriminator lets Pydantic select one valid reference
shape and reject ambiguous or malformed input. The application service exposes
separate methods for case and disruption resolution. The persistence repository
performs the required relationship joins and returns one structured
`ResolvedDisruptionPolicy`.

Structured fields were chosen instead of formatted prompt text because code,
tests, UI, and future models need the same unambiguous facts. Policy text remains
untrusted data; it cannot alter tool permissions or execution behavior.

**Evidence**

Tests cover both reference types, ambiguous and malformed references,
authorization and deadline rejection before service access, safe not found,
structured output, hidden dependency details, and real-PostgreSQL resolution by
both paths.

### Step 7 — Implement deterministic alternative-itinerary search

**Why this step was taken**

Recovery work needs possible replacement journeys. The current dataset can
support schedule-based route search, but it cannot prove seats, prices, ticket
eligibility, or complete connection policy.

**What was implemented**

`SearchAlternativeItinerariesInput` accepts:

- Origin and destination airport codes
- A timezone-aware earliest departure and latest arrival
- Positive passenger count
- Zero or one maximum connection

The result contains deterministically ordered direct and one-connection
candidates, scheduled segments, connection minutes, total scheduled duration,
and a `not_validated` candidate status. It declares inventory as
`not_evaluated` and defers seat inventory and ticket rules.

**How it was implemented**

Input validation rejects equal origin/destination values, naive timestamps, an
inverted time window, invalid passenger counts, and more than one connection.
The repository retrieves flights fully contained in the requested window.

The application service first orders flights by departure, arrival, and stable
ID. It selects direct matches, then constructs one-stop pairs only when the
first destination equals the second origin and the second flight departs after
the first arrives. Candidates are finally ordered by arrival, departure, and
flight IDs.

Passenger count is retained as a search requirement but does not become a seat
claim. This honest deferral was chosen instead of creating invented inventory
records merely to make the tool appear complete.

**Evidence**

Tests prove one connected seed-42 candidate, maximum-connection behavior,
deterministic ordering, empty successful results, strict input validation,
authorization and deadline guards, explicit deferrals, safe dependency failure,
and bounded-window retrieval against PostgreSQL.

### Step 8 — Implement deterministic itinerary validation

**Why this step was taken**

Candidate generation must not automatically imply validity. A caller or future
model also must not declare a candidate valid by including a `valid: true` field
or persuasive text in its request.

**What was implemented**

[`domain/itinerary_validation.py`](../../src/travelops_recovery_agent/domain/itinerary_validation.py)
added three fixed rules:

- `flights_exist`
- `route_continuity`
- `chronological_order`

Every rule returns `passed`, `failed`, or `not_evaluated` with a structured
reason. `ValidateItineraryInput` accepts a candidate ID, one or two unique
flight IDs, and passenger count. Its output includes the server-calculated
validity, rule results, and explicit deferral of minimum-connection policy,
inventory, and ticket rules.

**How it was implemented**

The application service loads only the requested stored flights and supplies a
mapping to the pure domain function. If any requested flight is absent, the
existence rule fails and dependent continuity and time rules become
`not_evaluated`. Otherwise, `pairwise()` checks consecutive flights for matching
airports and non-overlapping schedules.

Overall validity is calculated from evaluated domain results. The strict input
model forbids extra fields, so caller-provided validity is rejected before the
service runs. Missing stored flights become a typed not-found tool failure.

The rules live in the domain because their truth is independent of CLI, tool,
future HTTP, or model callers. Deferred checks remain visible because a
structurally connected itinerary is not necessarily available or ticketable.

**Evidence**

Domain tests cover valid, missing, disconnected, and overlapping itineraries.
Application tests prove requested order and missing-flight results. Tool tests
prove fixed rules, caller-claim rejection, pre-access guardrails, safe failures,
deferrals, and determinism. PostgreSQL tests prove explicit flight-ID loading.

### Step 9 — Apply authorization, deadlines, safe errors, and audit consistently

**Why this step was taken**

Security behavior must remain consistent across all five tools. Copying only
the happy path would allow one adapter to access data before authorization or
to leak an internal exception that another adapter hides.

**What was implemented**

`_ReadOnlyToolAdapter` centralizes safe audit and failure construction. Every
concrete adapter declares a stable `name` and one `required_permission`, then
follows the same execution order:

1. Capture the start time.
2. Validate strict input.
3. Verify the exact permission.
4. Reject an already-expired deadline.
5. Call the application service.
6. Translate unexpected dependency exceptions safely.
7. Check the deadline again after service access.
8. Return a typed result with audit metadata.

**How it was implemented**

Permission membership is checked inside the adapter rather than trusted to a
prompt or future outer route. Missing authority fails closed. The post-service
deadline check prevents a slow result from being presented as on time, although
the synchronous database call cannot be forcibly cancelled while executing.

No adapter automatically retries. A future orchestrator may decide whether a
retryable dependency failure should be attempted again based on remaining time,
attempt count, and operation semantics. Keeping retries outside each tool avoids
hidden latency and inconsistent retry storms.

Audit output records only tool name, actor ID, correlation ID, required
permission, outcome, timestamps, and duration. It excludes inputs, credentials,
database URLs, raw exceptions, and unnecessary passenger details.

**Evidence**

Boundary tests use service stubs and controlled clocks to prove that invalid,
unauthorized, and expired calls never reach the service. Tests also prove the
post-call deadline result, audit outcome and timing, safe exception translation,
and deterministic output when state, input, and clock are fixed.

### Step 10 — Publish stable schemas through a read-only registry

**Why this step was taken**

With five tools, callers need one inspectable catalogue rather than importing
and guessing individual model classes. Discovery must reveal contracts without
granting execution or exposing application internals.

**What was implemented**

[`tools/registry.py`](../../src/travelops_recovery_agent/tools/registry.py)
added `ToolSchema`, an ordered `TOOL_SCHEMAS` catalogue, immutable lookup by
name, and JSON schemas for each tool's input, success, failure, and execution
context. Each entry also declares its description and required permission.

**How it was implemented**

The registry calls Pydantic's `model_json_schema()` on the application-owned
tool contract classes. It stores five entries in a fixed deliberate order and
uses `MappingProxyType` for name lookup so a caller cannot mutate the registry.

The registry contains metadata only. It stores no adapter instance, query
service, repository, session, engine, database URL, or execution method. This
separates knowing that a capability exists from being authorized to invoke it.

**Evidence**

Registry tests prove the exact five names and permissions, JSON serializability,
strict `additionalProperties: false` schemas, shared audit/error shapes, stable
order, and absence of `execute_sql`, `prepare_rebooking`, and
`execute_rebooking`.

### Step 11 — Add a direct no-LLM command-line runner

**Why this step was taken**

The tools needed an observable end-to-end entry point before any model or agent
loop existed. A direct runner isolates tool correctness from model selection,
prompting, provider availability, and orchestration behavior.

**What was implemented**

[`tools/cli.py`](../../src/travelops_recovery_agent/tools/cli.py) added:

- `catalog` for schema discovery
- One subcommand for each required tool
- Global actor, correlation, and positive timeout options
- `ToolRuntime` containing the five concrete adapters
- A composition function that creates the engine, session factory, unit of
  work, application service, and adapters
- Structured JSON output and success/failure exit codes

**How it was implemented**

The CLI is the outer composition root. It is allowed to know how persistence is
constructed, but it injects only `OperationalQueryService` into the adapters.
Each command creates an execution context with exactly that tool's permission
and converts the timeout duration into an absolute UTC deadline.

`argparse` handles command structure. Pydantic remains responsible for actual
tool input validation. The database engine is disposed when the CLI owns it.
The schema catalogue command needs no database configuration because discovery
is independent of execution.

**Evidence**

CLI tests prove catalogue output without a database, successful structured
invocation through an injected runtime, and a nonzero exit for typed failure.
Manual seed-42 demonstrations called all five tools against PostgreSQL without
an LLM.

### Step 12 — Test every boundary against memory and real PostgreSQL

**Why this step was taken**

No single test type can prove the entire boundary. Fast unit tests can inspect
decisions precisely, while only PostgreSQL can prove real joins, constraints,
ordering, mappings, transactions, migrations, and driver behavior.

**What was implemented**

The test suite added:

- Domain tests for itinerary rules
- Application tests using repository and unit-of-work stubs
- Contract and schema tests for every public model
- Adapter tests for success, errors, authorization, deadlines, audit, and
  determinism
- Registry and CLI tests
- Real-PostgreSQL repository integration tests
- Credential-safe integration-fixture failure handling

**How it was implemented**

Service stubs record whether an adapter reached the application boundary. This
makes “reject before repository access” observable rather than assumed. Injected
clocks make deadline and audit tests deterministic.

Integration tests use only a database whose name is exactly `travelops_test`.
Alembic migrates it, fixtures clean managed records before and after tests, and
the SQLAlchemy repository is exercised against the real PostgreSQL service.
Connection setup failures are translated into concise pytest failures so URLs
and passwords do not appear in a traceback.

**Evidence**

The Phase 4 final gate passed 249 tests, including 17 real-database integration
tests, without warnings. Focused tool, application, and domain runs passed
before the complete cross-phase suite.

### Step 13 — Demonstrate all five tools with deterministic seed 42

**Why this step was taken**

Passing isolated tests does not by itself demonstrate that configuration,
migrations, seeding, composition, query services, adapters, serialization, and
the CLI work together as one operational path.

**What was implemented**

The development PostgreSQL database was migrated to revision `0001` and
atomically replaced with seed 42. Counts confirmed ten recovery cases, thirteen
passengers, twenty flights, and the expected associated records.

The live demonstration retrieved booking `BKG-0001`, derived delayed status for
`FLT-NV101`, resolved policy `POL-STANDARD` through `CASE-0001`, found the
`ZRA` to `XLC` two-flight candidate, and validated `FLT-NV101` plus
`FLT-NV102`.

**How it was implemented**

Credentials were obtained from the already configured local container only for
the command process and were never printed or written into source. Each tool
was invoked through `python -m travelops_recovery_agent.tools.cli`, so the
demonstration used the same contracts and adapters intended for later callers.

The search reported inventory as not evaluated. Validation passed its three
supported structural rules while still deferring minimum-connection policy,
seat inventory, and ticket rules.

**Evidence**

All five commands returned `ok: true` structured JSON. The candidate count was
one, the validation result was true for the supported rules, and the database
remained at the expected managed record counts because every exposed tool was
read-only.

### Step 14 — Preserve earlier gates and record Phase 4 evidence

**Why this step was taken**

A new tool boundary is not complete if it breaks packaging, the existing API,
database migrations, code quality, or earlier domain and persistence behavior.
The design reasoning also needs to remain available after the implementation
session ends.

**What was implemented**

README commands were added for direct tool discovery and execution.
`architecture.md` records the operational read path. `decisions.md` records
D-022 through D-024. `progress.md` records the Phase 4 result and handoff. This
note records the learning sequence and evidence.

No package dependency, API route, migration, model-provider library, frontend,
or write capability was added.

**How it was implemented**

The final gate ran locked synchronization, package import, the complete pytest
suite, Ruff lint, Ruff formatting, strict mypy, Alembic revision inspection,
Compose validation and health, a real Uvicorn socket check, and wheel/source
builds. Git scope and whitespace were inspected afterward without staging or
committing changes.

**Evidence**

All 249 tests passed. Ruff reported no lint or format problems, mypy reported no
issues across 68 source and test files, Alembic reported `0001 (head)`, Docker
reported healthy PostgreSQL, real `GET /health` returned HTTP 200 with a request
ID, and both distribution artifacts built successfully.

## Detailed concept guide

### Tool versus application service versus repository versus API endpoint

A **tool** is one narrow capability exposed to an authorized caller. It defines
input, output, error, permission, deadline, and audit behavior.

An **application service** coordinates a business use case. It decides which
repository operation and deterministic domain rule are required but does not
know HTTP or SQLAlchemy details.

A **repository** is an application-owned storage interface expressed in domain
language. Its SQLAlchemy implementation knows how to retrieve the required
records from PostgreSQL.

An **API endpoint** is an HTTP transport boundary. It handles URLs, methods,
headers, and HTTP response schemas. Phase 4 tools are callable Python adapters,
not HTTP endpoints; future API routes may reuse application services separately.

### Tool adapter versus domain logic

The adapter owns caller-boundary concerns: schema validation, permission,
deadline, safe exception translation, output minimization, and audit metadata.
The domain owns objective airline rules. Route continuity therefore remains
true regardless of whether validation is requested by a CLI, API, test, or
future model.

Keeping these roles separate avoids copying business rules into each transport.
It also prevents a change in tool packaging from changing what constitutes a
valid itinerary.

### Typed tool inputs and outputs

Typed inputs state exactly what a caller may provide. Pydantic validates stable
identifier patterns, positive counts, allowed connection values, timezone-aware
datetimes, discriminated policy references, and forbidden extra fields.

Typed outputs state exactly what downstream code may rely on. They minimize
passenger data and distinguish confirmed facts from deferred validation. Both
sides serialize predictably to JSON.

### Why schemas are contracts for code and models

A JSON schema is a machine-readable description of field names, types, required
values, enumerations, nested structures, and extra-field behavior. Ordinary
Python or TypeScript code can inspect it, and a future model adapter can use it
to describe a valid tool call.

The schema does not grant permission and does not guarantee that a caller will
produce valid data. The adapter still validates every actual invocation and
applies its execution context.

### Structured results versus formatted prompt text

Structured output keeps facts in named fields such as `delay_minutes`,
`policy_id`, and `validation_status`. Tests, UI components, and future agent code
can consume those fields without parsing sentences.

Formatted prompt text mixes data presentation with model instructions and can
lose type information. Policy summaries and retrieved text remain values inside
structured output, never executable instructions.

### Tool discovery and the registry

Discovery answers which capabilities exist and what contracts they use. With
five tools, a stable catalogue avoids scattered imports and provides one place
for future integrations to inspect names, descriptions, permissions, and JSON
schemas.

The registry deliberately contains no callable runtime or database dependency.
Knowing a tool exists is different from being allowed to execute it.

### Dependency inversion at the tool boundary

Higher-level application code defines the repository protocol it needs.
Lower-level SQLAlchemy persistence implements that protocol. The tool depends
on the application service, not on the database implementation.

This dependency direction makes the safety boundary narrow and testable. A
repository stub can verify application behavior, and storage can evolve without
changing public tool contracts.

### Least privilege and narrow tool design

Least privilege grants only the capability required for one task. Phase 4 uses
separate permissions such as `booking:read` and `itinerary:validate` rather than
one universal operational or database permission.

Each tool exposes one business operation. There is no arbitrary filter, generic
repository method, raw SQL, mutation, seed, reset, or rebooking capability.

### Authentication context versus authorization permission

Authentication asks, “Who is this actor?” Authorization asks, “What may this
actor do?” `actor_id` carries identity context, while the explicit permission
set controls access.

Phase 4 does not create production login or token infrastructure. A trusted
outer boundary must eventually authenticate the actor before constructing the
context. The adapter still refuses calls missing its required permission.

### Fail-closed behavior and read authorization

Fail closed means that missing, malformed, or insufficient authority produces a
denial. The adapter does not attempt the read and hope that another layer rejects
it later.

Read-only does not mean harmless. Booking data includes passenger identity, and
flight and policy facts may be operationally sensitive. Authorization therefore
applies before reads as well as future writes.

### Error taxonomy and safe error translation

The small public taxonomy lets callers respond predictably:

| Code | Meaning | Retryable by default |
| --- | --- | --- |
| `invalid_input` | The request violates the declared schema | No |
| `not_found` | A required stored identity does not exist | No |
| `permission_denied` | The context lacks required authority | No |
| `deadline_exceeded` | The call is already or eventually too late | No |
| `dependency_failure` | An internal operational dependency failed | Yes |

Raw exceptions may contain driver details, SQL, paths, or credentials. Adapters
therefore translate them to stable public errors and never copy exception text
into results.

### Domain error versus application error versus tool error

A domain failure describes invalid business meaning, such as a disconnected
route. An application failure describes an unsuccessful use case or dependency.
A tool error is the safe public representation returned to the caller.

Not every failed validation is an execution error. A known itinerary with a
disconnected route is a successful tool call whose structured result says
`valid: false`. Missing required stored flights are represented as not found.

### Timeout, deadline, cancellation, and retry

A **timeout** is a duration such as 30 seconds. A **deadline** is the absolute
moment by which work must finish. Phase 4 converts the CLI timeout into one UTC
deadline so the budget does not restart in each layer.

**Cancellation** actively interrupts ongoing work. The synchronous adapter can
check before and after the query but cannot forcibly stop the driver mid-call.
**Retry** starts another attempt after a failure. Retries remain outside tools so
future orchestration can apply bounded policy using error type, remaining time,
and attempt count.

### Correlation identifiers and safe audit metadata

A correlation ID connects one tool result with surrounding request, log, or
future workflow facts. It is not authentication and does not itself prove who
performed the action.

Safe audit metadata includes the tool, actor, correlation ID, required
permission, outcome, start, completion, and duration. Passwords, tokens,
database URLs, full request payloads, raw exceptions, and unnecessary passenger
details are excluded.

### Candidate generation versus deterministic validation

Generation finds route-shaped possibilities from scheduled data. Validation
checks a named candidate against explicit rules. Separation keeps search broad
and validity conservative.

The same database state and input produce the same ordered candidates because
all sorting uses scheduled times and stable identifiers. The caller cannot
change server-calculated validity by changing prose or including extra fields.

### Passenger data minimization

The booking tool returns stable passenger IDs and display names because the
operator needs to understand the party. It does not expose storage rows or
invent contact, payment, passport, loyalty, or demographic fields.

Minimization reduces accidental disclosure and produces a smaller, clearer
future model context. More fields should be added only when a concrete workflow
and authorization rule justify them.

### Untrusted tool data and prompt-injection boundaries

Database and policy text is treated as data even when it contains instruction-
like wording. It cannot grant permission, alter a deadline, introduce a new tool,
or mark a candidate valid.

A future model may interpret returned evidence, but deterministic code remains
responsible for tool validation and business rules. Prompts never replace the
execution context or domain validation.

### Unit, contract, and real-database integration tests

Unit tests isolate one decision using in-memory objects and stubs. Contract tests
prove stable public schemas, guardrails, and serialization. Integration tests
prove behavior that depends on SQLAlchemy, Psycopg, Alembic, and PostgreSQL.

The layers complement one another. A passing adapter test cannot prove a real
join, and a passing database query cannot prove that unauthorized input is
rejected before service access.

### Why tools must work without an LLM

A no-LLM baseline makes tool behavior deterministic, fast, inexpensive, and
easy to debug. When Phase 6 adds a model loop, failures can be separated into
tool defects versus model selection or sequencing defects.

The database and business rules also remain usable when a provider is down or a
model is replaced. The model becomes a bounded caller, not the owner of
operational truth.

### What later phases own

Phase 6 owns the first bounded model-and-tool loop. Phase 7 owns explicit
LangGraph state and orchestration. Phase 9 owns evidence-backed availability,
minimum connections, ticket rules, candidate ranking, and recommendations.
Phase 10 owns proposals, human approval, final revalidation, idempotent writes,
and durable audit records.

## Commands and what each proves

```powershell
# Reproduce the exact Python dependency graph
uv sync --locked

# Enter the PostgreSQL password without printing it
$credential = Get-Credential -UserName travelops `
  -Message "Enter the TravelOps PostgreSQL password"
$password = $credential.GetNetworkCredential().Password
$encodedPassword = [uri]::EscapeDataString($password)

# Configure Compose, development, and isolated integration-test access
$env:TRAVELOPS_POSTGRES_PASSWORD = $password
$env:TRAVELOPS_DATABASE_URL = `
  "postgresql+psycopg://travelops:{0}@127.0.0.1:55432/travelops" `
  -f $encodedPassword
$env:TRAVELOPS_TEST_DATABASE_URL = `
  "postgresql+psycopg://travelops:{0}@127.0.0.1:55432/travelops_test" `
  -f $encodedPassword

# Start PostgreSQL and inspect its health
docker compose up -d postgres
docker compose ps

# Apply and inspect explicit schema history
uv run --locked alembic upgrade head
uv run --locked alembic current

# Restore the canonical development data and prove exact managed counts
uv run --locked python -m travelops_recovery_agent.persistence.cli `
  seed --seed 42 --replace
uv run --locked python -m travelops_recovery_agent.persistence.cli counts

# Inspect all stable input, result, context, error, and permission schemas
uv run --locked python -m travelops_recovery_agent.tools.cli catalog

# Demonstrate minimized booking retrieval
uv run --locked python -m travelops_recovery_agent.tools.cli `
  get-booking BKG-0001

# Demonstrate disruption-derived synthetic flight status
uv run --locked python -m travelops_recovery_agent.tools.cli `
  get-flight-status FLT-NV101

# Demonstrate structured policy resolution
uv run --locked python -m travelops_recovery_agent.tools.cli `
  get-disruption-policy --case-id CASE-0001

# Generate deterministic scheduled candidates without claiming inventory
uv run --locked python -m travelops_recovery_agent.tools.cli `
  search-alternative-itineraries ZRA XLC `
  2026-01-15T11:00:00Z 2026-01-15T18:00:00Z 1

# Validate the candidate through fixed server-owned rules
uv run --locked python -m travelops_recovery_agent.tools.cli `
  validate-itinerary CAND-FLT-NV101-FLT-NV102 1 `
  FLT-NV101 FLT-NV102

# Run focused tool contracts and behavior
uv run --locked pytest -q tests/tools

# Prove repository behavior against isolated real PostgreSQL
uv run --locked pytest -q -m integration

# Preserve all Phase 0–4 behavioral gates
uv run --locked pytest -q

# Detect lint problems and verify canonical formatting
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests

# Prove static type agreement across source and tests
uv run --locked mypy

# Prove installed-package resolution and build standard distributions
uv run --locked python -c "import travelops_recovery_agent; print('import ok')"
uv run --locked python -m build --no-isolation

# Start the unchanged Phase 1 API in terminal 1
uv run --locked uvicorn travelops_recovery_agent.api.app:create_app `
  --factory --host 127.0.0.1 --port 8000

# Prove the existing liveness contract in terminal 2
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health

# Stop PostgreSQL while preserving its named volume
docker compose down
```

## Problems encountered and lessons learned

### Import ordering failed after repository expansion

Adding application query models to `repositories.py` left one import below the
data and domain imports. Runtime behavior and mypy were correct, but Ruff's
import-order rule failed. Ruff reorganized the block, confirming that lint and
typing check different properties.

### Duplicate test filenames confused strict mypy

Domain and application folders initially both contained
`test_itinerary_validation.py`. Pytest's configured import mode could execute
them, but mypy treated the basenames as one module. Renaming the domain file to
`test_itinerary_rules.py` gave every checked test module a unique identity.

### Connection failures risked exposing a secret URL

A failed integration migration could allow SQLAlchemy's exception chain to
include connection details in pytest output. The integration fixture now catches
database errors around migration setup and emits a concise safe failure without
the traceback. Credential safety applies to failed tests as well as normal tool
responses.

### PowerShell execution policy blocked the health-check script

The final real-socket verification used a temporary PowerShell script to start,
probe, and stop Uvicorn. The machine's default execution policy blocked the
first attempt before it ran. Setting `ExecutionPolicy` to `Bypass` for that
single process allowed the bounded check without changing the machine-wide
policy, and the temporary script and logs were removed afterward.

### The dataset supported search but not complete availability

Seed 42 contains coherent direct and connecting flight schedules, so a useful
deterministic route search was possible. It has no seat counts, fare values,
ticket conditions, or airport connection rules. The result contracts therefore
make those gaps visible rather than creating artificial facts.

### A deadline is not active cancellation

The adapter can reject work before it starts and reject a result that completes
too late. With synchronous SQLAlchemy, it cannot safely interrupt the driver
halfway through a query. Phase 4 therefore documents cooperative deadlines and
leaves active cancellation to later orchestration and infrastructure.

## Decisions made

- [D-022](../decisions.md#d-022--use-guarded-pydantic-tool-adapters-and-shared-envelopes)
  selected normal Python adapter classes, strict Pydantic contracts, shared
  success/failure envelopes, and a schema-only registry.
- [D-023](../decisions.md#d-023--enforce-least-privilege-and-absolute-deadlines-at-each-adapter)
  selected one explicit permission per tool, absolute deadlines, fail-closed
  checks, safe exception translation, and no hidden automatic retries.
- [D-024](../decisions.md#d-024--separate-deterministic-candidate-generation-from-validation)
  separated scheduled-flight candidate generation from server-owned validation
  and explicitly deferred unsupported evidence.

## Remaining limitations at the Phase 4 boundary

- Tools have no production authentication provider; they receive a typed context
  constructed by a trusted caller.
- Deadlines are cooperative and do not actively cancel an executing synchronous
  database query.
- Audit metadata is returned with each result but is not yet written to a durable
  audit store.
- Flight status is deterministic synthetic evidence, not a real airline feed.
- Search evaluates schedules, not seats, prices, ticket eligibility, cabin, or
  fare differences.
- Validation does not yet enforce an airport-specific minimum connection.
- Structurally valid candidates are not yet ranked recommendations.
- No Phase 5 frontend or business API route exists at this boundary.
- No Phase 6 model loop, Phase 7 LangGraph workflow, or Phase 8 checkpoint and
  live-event behavior exists.
- No proposal, approval, revalidation, idempotency, or rebooking write exists.
- The tool registry is an application-owned Python catalogue, not an MCP server
  or provider-specific tool registration.

## Glossary

| Term | Meaning in this project |
| --- | --- |
| Tool | One narrow guarded operational capability exposed to a caller |
| Tool contract | The stable typed input, result, context, error, permission, and audit boundary |
| Tool adapter | The class that enforces boundary rules and calls an application service |
| Application service | Code that coordinates one read workflow using repositories and domain rules |
| Repository | An application-owned interface for named domain-oriented storage operations |
| Persistence adapter | The SQLAlchemy implementation of the repository protocol |
| Domain rule | Deterministic business truth independent of transport and storage |
| Execution context | Actor, correlation, permission, and deadline metadata for one call |
| Permission | Explicit authorization to invoke one narrow capability |
| Least privilege | Granting only the authority needed for the current operation |
| Fail closed | Rejecting access when required validation or authority is absent |
| Deadline | One absolute timezone-aware moment by which work must finish |
| Timeout | A duration converted by the caller into a deadline |
| Cancellation | An active attempt to interrupt ongoing work |
| Retry | A separate attempt after a failure |
| Error taxonomy | The small stable set of public failure categories |
| Audit metadata | Safe facts describing who invoked which tool, when, and with what outcome |
| Correlation ID | A value connecting one call with surrounding logs or workflow facts |
| Schema | A machine-readable description of the accepted or returned structure |
| Structured result | Named typed fields rather than prose intended for prompt parsing |
| Discriminated union | Alternative input shapes selected by one explicit type field |
| Candidate itinerary | A possible scheduled route that is not automatically valid or available |
| Determinism | The same database state and input produce the same ordered business result |
| Deferred validation | A check explicitly postponed because required evidence does not exist yet |
| Data minimization | Returning only fields justified by the operational use case |
| Dependency inversion | Higher-level application code defines interfaces implemented by lower-level persistence |
| Composition root | The outer CLI location that constructs and connects concrete dependencies |
| No-LLM baseline | Tool execution proven independently of model selection, prompts, or providers |

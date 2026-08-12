# Phase 4 notes — typed read-only operational tools

## What this phase shipped

Phase 4 added five narrow tools that work directly without an LLM:

- `get_booking` returns a booking, display names, and ordered scheduled segments.
- `get_flight_status` derives scheduled, delayed, or cancelled status from stored
  synthetic disruption evidence.
- `get_disruption_policy` resolves structured policy facts by case or disruption.
- `search_alternative_itineraries` generates deterministic direct or one-stop
  candidates inside explicit route and time bounds.
- `validate_itinerary` checks stored-flight existence, route continuity, and
  chronological order with a structured result for every rule.

Each tool has strict Pydantic input and output models, one required permission,
an absolute deadline, shared typed success/failure envelopes, safe audit
metadata, and an inspectable JSON schema. The manual commands are in the README.

## How it works

```text
CLI or future caller
  -> strict tool input + ToolExecutionContext
  -> adapter checks permission and deadline
  -> OperationalQueryService coordinates the read
  -> application-owned repository protocol
  -> SQLAlchemy repository reads PostgreSQL
  -> optional deterministic domain validation
  -> adapter minimizes and maps the result
  -> typed success or safe typed failure + audit metadata
```

[`tools/contracts.py`](../../src/travelops_recovery_agent/tools/contracts.py)
defines shared boundary models. [`tools/models.py`](../../src/travelops_recovery_agent/tools/models.py)
defines each tool's data. [`tools/adapters.py`](../../src/travelops_recovery_agent/tools/adapters.py)
enforces the guardrails and maps application results. [`tools/registry.py`](../../src/travelops_recovery_agent/tools/registry.py)
publishes schemas, while [`tools/cli.py`](../../src/travelops_recovery_agent/tools/cli.py)
is a direct runner and composition root.

[`application/query_services.py`](../../src/travelops_recovery_agent/application/query_services.py)
coordinates domain-oriented reads through the protocol in
[`application/repositories.py`](../../src/travelops_recovery_agent/application/repositories.py).
The SQLAlchemy implementation stays in [`persistence/repositories.py`](../../src/travelops_recovery_agent/persistence/repositories.py).
Fixed itinerary rules live in [`domain/itinerary_validation.py`](../../src/travelops_recovery_agent/domain/itinerary_validation.py).

## Concepts I can explain

### Tool, application service, repository, API endpoint, and prompt

A tool is a narrow operation exposed to a caller. Its adapter validates input,
authorizes the call, enforces its deadline, and translates results safely. An
application service coordinates a business read and knows which repository
operations or domain rules it needs. A repository is a domain-shaped storage
interface; its PostgreSQL implementation knows SQLAlchemy. An API endpoint is an
HTTP transport boundary. A prompt is text supplied to a model. They are not
interchangeable: Phase 4 adds tools but no model and no new HTTP endpoint.

### Tool adapter versus domain logic

The adapter owns boundary concerns such as permissions, deadlines, errors, and
audit metadata. The domain owns truths that must remain the same for CLI, HTTP,
or future agent callers. Route continuity therefore lives in the domain, not in
`ValidateItineraryTool`. Moving business truth into adapters would duplicate it
as more entry points appear.

### Typed inputs, outputs, schemas, and structured results

Types make accepted fields explicit and reject malformed identifiers, naive
timestamps, extra claims, and invalid ranges before repository access. JSON
schemas are machine-readable versions of those contracts, useful to ordinary
code and future models. Structured output preserves field meaning; formatted
prompt prose would require fragile parsing and could blur facts with instructions.

The registry makes schemas discoverable in one stable order. It is deliberately
non-executable: discovering a tool does not grant permission to call it.

### Dependency inversion

The application owns the repository protocol it requires, and persistence
implements it. Tools depend on the application service rather than SQLAlchemy.
This reverses the usual low-level dependency direction: database code conforms
to higher-level business needs. A tool cannot issue arbitrary SQL because it
never receives a session, engine, generic repository, or SQL string.

### Least privilege, authentication context, and authorization

Least privilege means granting only the exact capability needed. Each CLI call
gets one permission such as `booking:read`, not a universal data permission.
`actor_id` says who the caller claims or is known to be; that is authentication
context. Permission answers what that actor may do; that is authorization.
Phase 4 models the context but does not build production identity infrastructure.

Adapters check permission before service or database access and fail closed:
missing or unrecognized authority means denial, not an optimistic attempt. Reads
still need authorization because passenger and operational data can be sensitive
even when nothing is modified.

### Error taxonomy and safe translation

The public codes are invalid input, not found, permission denied, deadline
exceeded, and dependency failure. A domain error describes invalid business
meaning. An application error describes a failed workflow. A tool error is the
small safe boundary representation. Adapters never return internal exceptions,
stack traces, database URLs, or credentials; unexpected dependency exceptions
become a generic retryable dependency failure.

### Timeout, deadline, cancellation, and retry

A timeout is a duration. The CLI converts it once to an absolute UTC deadline,
which lets every layer compare against the same finish-by time. Cancellation is
an active request to stop ongoing work; the synchronous Phase 4 adapter cannot
forcibly interrupt a database driver, so it checks cooperatively before and
after access. A retry is a new attempt after failure. Retries are not automatic
inside every tool because they can exceed deadlines, multiply load, or repeat
non-idempotent work in later phases. Future orchestration can apply a visible,
bounded retry policy based on error code and remaining time.

### Correlation and audit metadata

A correlation identifier connects facts from one call across logs or future
workflow state. Audit metadata records the tool name, actor identifier,
correlation identifier, required permission, outcome, timestamps, and duration.
These are safe operational facts. It does not record passwords, database URLs,
raw exceptions, full inputs, or unnecessary passenger details. The current
audit object is returned data; a durable audit store belongs to later phases.

### Candidate generation versus validation and determinism

Search asks, "Which scheduled flights could form this route in this window?"
Validation asks, "Do these stored flights satisfy the rules we can currently
prove?" Keeping them separate prevents a generated candidate from becoming
valid merely because it was found. Ordering by schedule and stable identifiers
makes identical database state and input produce identical candidates.

The dataset has no seat inventory, pricing, ticket rules, or minimum-connection
policy. Search reports inventory and ticket rules as not evaluated. Validation
reports those plus minimum-connection policy as deferred. A structurally valid
candidate is therefore not yet a guaranteed available or recommendable trip.

### Data minimization and untrusted data

`get_booking` returns only passenger stable IDs and display names needed to
understand party size and identity. It does not expose persistence records or
invent contact, payment, document, or loyalty fields. Policy names, summaries,
and any later retrieved text remain data, never instructions. A future model
must not be able to change permissions or validity by embedding commands in a
stored text field or by wording its request differently.

### Unit, contract, and real-database tests

Domain unit tests prove fixed validation rules. Application tests prove
coordination through repository protocols. Tool contract tests prove schemas,
successful outputs, malformed input, fail-closed authorization, deadlines,
not-found behavior, safe errors, determinism, audit facts, and data minimization.
PostgreSQL integration tests prove real query ordering, joins, mapping, migration,
transaction, and cleanup behavior that an in-memory substitute cannot prove.

Working without an LLM keeps the business baseline deterministic and cheap to
debug. Phase 6 can later measure whether a model selects and sequences these
tools correctly without confusing model quality with database or rule defects.

## Decisions I made

- [D-022](../decisions.md#d-022--use-guarded-pydantic-tool-adapters-and-shared-envelopes)
  chooses normal Python adapters, strict contracts, shared envelopes, and a registry.
- [D-023](../decisions.md#d-023--enforce-least-privilege-and-absolute-deadlines-at-each-adapter)
  defines fail-closed permissions, cooperative deadlines, safe errors, and no hidden retries.
- [D-024](../decisions.md#d-024--separate-deterministic-candidate-generation-from-validation)
  separates search from validity and makes missing evidence explicit.

## Tests and demonstrations

- Focused tests cover domain rules, application queries, every adapter, registry,
  CLI, schemas, permissions, deadlines, safe failures, audit data, and determinism.
- Seventeen integration tests pass against isolated PostgreSQL, not SQLite.
- Seed 42 loads ten recovery cases and twenty flights at migration `0001`.
- All five CLI tools returned typed results directly from PostgreSQL without an LLM.
- The final gate passed all 249 tests plus locked sync, import, Ruff, strict
  mypy, migration state, database health, unchanged real-socket `/health`, and
  wheel/source builds.

## What failed or surprised me

- Ruff caught import ordering after repository methods were added; automated
  formatting fixed presentation without changing behavior.
- Two test folders initially used the same Python module filename. Pytest passed,
  but strict mypy detected the collision; the domain test received a unique name.
- PostgreSQL connection failures originally risked displaying a URL through a
  traceback. The integration fixture now emits a concise credential-safe failure.
- The deterministic dataset supports useful scheduled candidate search, but not
  seats, prices, ticket rules, or a policy-backed minimum connection.

## Remaining limitations

- Phase 5 will add the visual dashboard; no frontend was added here.
- Phase 6 will add the first bounded model loop; tools currently need no model.
- Phase 7 will coordinate calls in LangGraph and may add explicit cancellation
  and retry policy without moving business rules into the graph.
- Phase 9 must add evidence-backed availability, connection, ticket-rule,
  ranking, and recommendation checks.
- Phase 10 owns proposals, approval, idempotency, final revalidation, writes, and
  durable audit records. Phase 4 exposes no mutation or rebooking capability.

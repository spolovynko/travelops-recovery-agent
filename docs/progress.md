# Progress

## Current state

- **Current phase:** Phase 7 — LangGraph orchestration
- **Status:** Complete
- **Last completed result:** An explicit, inspectable LangGraph workflow that is behaviorally equivalent to the verified Phase 6 manual loop
- **Next gate:** Review the intended Phase 7 Git scope; begin durable checkpointing and resumption only as an explicitly requested Phase 8

## Concepts confirmed in Phase 0

- The physical contents and isolation boundary of a virtual environment
- Authored `pyproject.toml` intent versus generated lockfile resolution
- How a `src/` package layout exposes accidental checkout-root imports
- Build frontend versus backend, plus wheel versus source distribution
- Tests versus linting versus formatting versus static type checking
- Project/tool configuration versus application behavior

## Concepts confirmed in Phase 2

- Entities, value objects, aggregates, and invariants
- Domain models versus API schemas and future persistence models
- Construction-time validation versus validation requiring related objects
- Deterministic generation, local seeded randomness, and global-state isolation
- Reviewed realistic scenarios versus arbitrary random fixtures
- Schema versions, provenance, stable identifiers, ordering, and serialization
- Timezone-aware datetime comparison across different UTC offsets
- CLI generation and validation as a boundary independent of HTTP and SQL
- Direct Pydantic dependency declaration versus transitive availability

## Concepts confirmed in Phase 3

- Domain models versus persistence records versus API schemas
- Relational tables, rows, columns, keys, constraints, nullability, and indexes
- One-to-many, many-to-many, association-table, and normalization choices
- SQLAlchemy declarative mapping, sessions, identity maps, and connection pools
- Transactions, commit, rollback, atomicity, and unit-of-work boundaries
- Repository interfaces, dependency inversion, and application services
- Explicit domain-to-record and record-to-domain validation
- Alembic revision history versus automatic `create_all()` behavior
- Synchronous PostgreSQL access and the tradeoff against async SQLAlchemy
- Real-database integration tests, isolation, migration, cleanup, and rollback
- Deterministic controlled seeding and production-blocked reset behavior

## Concepts confirmed in Phase 4

- Tool contracts, adapters, application query services, repositories, and domain rules
- Strict typed schemas and structured results independent of prompt wording
- Least privilege, fail-closed permission checks, deadlines, and safe errors
- Correlation and minimized audit metadata without secrets or raw passenger records
- Deterministic candidate generation separated from final validation
- Schema discovery through a non-executable registry and direct no-LLM invocation
- Unit, contract, and isolated real-PostgreSQL integration responsibilities

## Concepts confirmed in Phase 5

- URL-owned case selection and authoritative reload after refresh
- Browser view models versus domain models and persistence records
- TanStack Query ownership of server state versus local draft UI state
- Purpose-built browser APIs versus Phase 4 tool adapters
- Responsive, accessible status communication without color-only meaning
- Safe loading, empty, not-found, dependency-failure, and deferred-evidence states
- Deterministic search separated from backend validation and bookability
- Component, browser, API, application, and real-database test responsibilities

## Concepts confirmed in Phase 6

- Model decisions versus application-enforced execution and domain validation
- Provider-independent protocols versus provider-specific HTTP adapters
- Discriminated structured outcomes: call a tool, ask for information, or finish
- Typed control state versus conversation messages and durable checkpoints
- Safe Phase 4 schema projection separated from executable tool injection
- Finite turns, absolute deadlines, malformed retries and repeated-call fingerprints
- Deterministic recorded providers versus live-model quality evaluation
- Manual loop mechanics as the baseline for Phase 7 LangGraph comparison

## Concepts confirmed in Phase 7

- Graph state as a typed transient workflow clipboard, not hidden model memory
- Nodes as small named responsibilities and edges as the permitted routes between them
- Conditional edges, explicit terminal handling, graph compilation, and framework recursion protection
- Reducers as channel-specific merge rules for partial state updates
- Runtime context as the safe home for executable dependencies that must never enter model-visible state
- Model proposals versus graph routing versus deterministic application validation
- State inspection and node history without storing or exposing chain-of-thought
- Recorded manual-loop/graph equivalence as the framework-adoption gate
- Minimal LangChain Core usage for one exact runtime configuration type, not a prebuilt agent
- Transient Phase 7 orchestration versus Phase 8 checkpoint durability and resumption

## Parking lot

- A trusted default model remains unselected until it passes a repeatable benchmark.
- Durable LangGraph checkpoints, thread identity, interruption and resumption belong to Phase 8.
- The visual operator dashboard and React baseline were completed in Phase 5.
- Context engineering through MCP are committed as the advanced track in Phases 12–20.
- Voice and real airline integrations remain outside the committed track.

## Session handoff template

```markdown
## Session N — YYYY-MM-DD

**Phase:** Phase number and name

**Built:** Concrete files and working behaviour

**Verified:** Commands, tests, API calls, or UI behaviour observed

**Concepts confirmed:** Ideas that can now be explained clearly

**Still unclear:** Concepts to revisit before the phase gate

**Decisions:** Links to entries added or changed in `decisions.md`

**Parked:** Useful ideas deliberately excluded from the current phase

**Next smallest step:** One concrete action for the next session
```

Add new session entries below this line. Do not replace prior history.

## Session 1 — 2026-08-10

**Phase:** Phase 0 — project foundation

**Built:** Added the `src/travelops_recovery_agent` package and typed-package marker, an import smoke test, `pyproject.toml`, Python 3.12.10 pin, `uv.lock`, synchronized `.venv`, centralized pytest/Ruff/strict-mypy policies, and Phase 0 learning notes. Built a universal wheel and source distribution under ignored `dist/`.

**Verified:** `uv lock --check`; `uv sync --locked --all-groups`; installed-package import; one passing pytest test; Ruff lint; Ruff format check; strict mypy over `src` and `tests`; locked-backend `python -m build --no-isolation`; archive content inspection.

**Concepts confirmed:** Virtual-environment contents and limits; project intent versus exact dependency resolution; installed-package testing with a `src/` layout; PEP 517 frontend/backend responsibilities; wheel and source-distribution contents; distinct test, lint, format, and typing signals; project configuration boundaries.

**Still unclear:** Nothing required by the Phase 0 gate. Later phases will add behavior rather than expanding the foundation early.

**Decisions:** [D-009 — Use uv for the reproducible Python environment](decisions.md#d-009--use-uv-for-the-reproducible-python-environment); [D-010 — Package from src with Hatchling](decisions.md#d-010--package-from-src-with-hatchling).

**Parked:** FastAPI, Uvicorn, pydantic-settings, API routes, application logging, request IDs, PostgreSQL, SQLAlchemy, Alembic, airline models and data, React, agent frameworks, model integrations, authentication, and Docker changes.

**Next smallest step:** Review the Phase 0 evidence and begin Phase 1 only after an explicit request.

## Session 2 — 2026-08-11

**Phase:** Phase 1 — API, configuration, and logging

**Built:** Added validated environment settings, an injectable FastAPI application factory, typed `GET /health`, generated OpenAPI, server-generated request IDs, request-local context, response correlation headers, and structured JSON request logs. Added FastAPI, pydantic-settings, Uvicorn, and the HTTPX2 test dependency to the locked environment.

**Verified:** Locked synchronization; installed-package import; settings defaults, precedence, invalid-value behavior, and secret masking; in-process health, OpenAPI, request-ID, logging-correlation, and secret-log tests; real Uvicorn socket with `/health`, `X-Request-ID`, JSON log, and `/openapi.json`; twelve passing tests without warnings; Ruff lint and format; strict mypy; wheel and source-distribution build.

**Concepts confirmed:** TCP, HTTP, ASGI, Uvicorn, and FastAPI responsibilities; application factories and dependency injection; configuration precedence and validation; secret-safe representation; liveness versus readiness; in-process versus socket tests; structured log events; request-local context and correlation limits; import-safe logging configuration.

**Still unclear:** Nothing required by the Phase 1 gate. Readiness becomes meaningful when Phase 3 introduces a real database dependency.

**Decisions:** [D-011 — Construct the API with an application factory](decisions.md#d-011--construct-the-api-with-an-application-factory); [D-012 — Generate request IDs in middleware](decisions.md#d-012--generate-request-ids-in-middleware); [D-013 — Emit application logs as JSON](decisions.md#d-013--emit-application-logs-as-json).

**Parked:** PostgreSQL, SQLAlchemy, Alembic, airline domain models, synthetic disruption data, operational tools, frontend code, agent frameworks, model integrations, authentication, and Docker infrastructure.

**Next smallest step:** Review Phase 1 evidence and begin Phase 2 only after an explicit request.

## Session 3 — 2026-08-11

**Phase:** Phase 2 — airline domain and synthetic cases

**Built:** Added immutable typed passengers, flights, itinerary segments,
bookings, disruptions, policies, and recovery cases; local and aggregate
invariants; versioned seed and provenance metadata; stable JSON loading and
writing; a local-seed generator with ten reviewed delay, cancellation, and
missed-connection cases; and standard-library CLI generation and validation.
Declared Pydantic as a direct dependency while keeping FastAPI, persistence,
and generator boundaries separate.

**Verified:** Locked dependency synchronization and installed-package import;
102 passing tests without warnings, including the Phase 1 `/health` behavior;
Ruff lint and format checks; strict mypy over 22 source files; two CLI-generated
seed-42 files with identical SHA-256 hashes; validated output containing 10
cases, 10 disruptions, 13 passengers, and 20 flights; and successful wheel and
source-distribution builds.

**Concepts confirmed:** Entity and value-object identity; aggregate and
invariant boundaries; deterministic domain enforcement; construction versus
relationship validation; seeded randomness; realistic reviewed synthetic data;
dataset versions and provenance; stable IDs, ordering, and bytes; timezone-aware
datetimes; direct dependencies; and CLI boundaries.

**Still unclear:** Nothing required by the Phase 2 gate. Persistence mapping and
database seeding deliberately remain Phase 3 work.

**Decisions:** [D-014 — Keep the airline domain independent](decisions.md#d-014--keep-the-airline-domain-independent); [D-015 — Validate a versioned dataset aggregate](decisions.md#d-015--validate-a-versioned-dataset-aggregate); [D-016 — Generate reviewed scenarios deterministically](decisions.md#d-016--generate-reviewed-scenarios-deterministically).

**Parked:** PostgreSQL, SQLAlchemy, Alembic, repositories, persistence mapping,
new airline API routes, operational tools, UI work, model integrations, Faker,
LLM-generated fixtures, and Phase 3 seeding infrastructure.

**Next smallest step:** Review the intended Phase 2 Git scope and create a
checkpoint commit only after explicit approval; do not begin Phase 3 yet.

## Session 4 — 2026-08-11

**Phase:** Phase 3 — PostgreSQL persistence and service boundaries

**Built:** Added the PostgreSQL 18 Compose service, secret database settings,
synchronous SQLAlchemy engine and session factory, normalized persistence
records, an Alembic `0001` revision, explicit domain mapping, repository and
unit-of-work implementations, transactional application services, and CLI
commands for seed, replace, reset, counts, and complete-case retrieval.

**Verified:** Connected pgAdmin to the isolated container on port 55432;
migrated the development database; loaded all ten seed-42 recovery cases;
demonstrated controlled repeat-seed refusal, atomic replacement, confirmed
reset, and complete-case retrieval; passed focused unit and real-PostgreSQL
tests for mapping, repositories, transactions, services, migrations,
constraints, cleanup, and the CLI. The final gate passed all 153 tests without
warnings, Ruff lint and format checks, strict mypy, package import and builds,
Compose validation, PostgreSQL health, and a real-socket `GET /health` check.

**Concepts confirmed:** ORM and relational vocabulary; normalized associations;
typed disruption storage; keys, constraints, indexes, and timezone columns;
sessions, identity maps, pools, transactions, atomicity, repositories,
dependency inversion, units of work, migrations, secret URLs, deterministic
seeding, and integration-test isolation.

**Still unclear:** Nothing required by the Phase 3 learning contract.

**Decisions:** [D-017 — Use synchronous SQLAlchemy with explicit mapping](decisions.md#d-017--use-synchronous-sqlalchemy-with-explicit-mapping); [D-018 — Use a normalized PostgreSQL schema with typed disruption details](decisions.md#d-018--use-a-normalized-postgresql-schema-with-typed-disruption-details); [D-019 — Let Alembic own schema history](decisions.md#d-019--let-alembic-own-schema-history); [D-020 — Place transactions around application workflows](decisions.md#d-020--place-transactions-around-application-workflows); [D-021 — Make development data management explicit and safe](decisions.md#d-021--make-development-data-management-explicit-and-safe).

**Parked:** New business API routes, Phase 4 operational tools, frontend work,
workflow checkpoints, agent frameworks, model providers, LangChain, LangGraph,
authentication, production deployment, and real airline integrations.

**Next smallest step:** Review the intended Phase 3 Git scope and create a
checkpoint commit only after explicit approval; do not begin Phase 4 yet.

## Session 5 — 2026-08-12

**Phase:** Phase 4 — typed read-only operational tools

**Built:** Added shared permission, execution-context, deadline, error, success,
failure, and audit contracts; application query models and services; narrow
repository reads; deterministic itinerary rules; five guarded adapters; strict
tool input/output models; a schema registry; and a direct no-LLM CLI.

**Verified:** Focused domain, application, schema, adapter, authorization,
deadline, safe-error, determinism, audit, and CLI tests; strict mypy and Ruff;
17 isolated PostgreSQL integration tests; migration revision `0001`; ten seeded
recovery cases; and successful live calls to all five tools. The final
cross-phase gate passed all 249 tests, Ruff, strict mypy, package import and
builds, Compose health, and real-socket `GET /health`.

**Concepts confirmed:** Narrow tools versus services, repositories, domain rules,
and APIs; dependency inversion; typed schema contracts; least privilege;
authentication context versus permission; fail-closed reads; safe error
translation; deadlines versus cancellation and retry; correlation and auditing;
data minimization; deterministic search versus validation; and no-LLM testing.

**Still unclear:** Nothing required by the Phase 4 learning contract.

**Decisions:** [D-022 — Use guarded Pydantic tool adapters and shared envelopes](decisions.md#d-022--use-guarded-pydantic-tool-adapters-and-shared-envelopes); [D-023 — Enforce least privilege and absolute deadlines at each adapter](decisions.md#d-023--enforce-least-privilege-and-absolute-deadlines-at-each-adapter); [D-024 — Separate deterministic candidate generation from validation](decisions.md#d-024--separate-deterministic-candidate-generation-from-validation).

**Parked:** Phase 5 UI, Phase 6 model loop, Phase 7 LangGraph orchestration,
Phase 9 availability and recommendation evidence, Phase 10 writes and approval,
new business API routes, real airline APIs, and production authentication.

**Next smallest step:** Review the Phase 4 diff and create a checkpoint commit
only after explicit approval; do not begin Phase 5 yet.

## Session 6 — 2026-08-12

**Phase:** Phase 5 — visual operator dashboard

**Built:** Added four versioned read-only recovery browser routes, strict
Pydantic view/request models, complete-case queue reads, safe 404/503 handling,
and a React/TypeScript operations console with URL routing, TanStack Query,
case queue, evidence workspace, deterministic alternative search, candidate
validation, responsive layouts, accessible states, and a Playwright journey.

**Verified:** Ruff format and lint, strict mypy over 72 Python files, 243
non-database tests, all 18 isolated PostgreSQL integration tests, package wheel
and source-distribution builds, Prettier, TypeScript, Oxlint, seven component
tests, production Vite build, and one Playwright end-to-end test. A live seeded
workflow passed queue navigation, direct case loading, search, validation and
refresh. Desktop 1440×900 and mobile 390×844 checks had no horizontal overflow,
and the browser console contained no warnings or errors.

**Concepts confirmed:** Browser/API/application/persistence boundaries; typed
view models; URL and server-state ownership; deterministic backend validation;
explicit deferred evidence; responsive and accessible status design; safe
errors and passenger-data minimization; layered frontend and backend tests.

**Still unclear:** Nothing required by the Phase 5 learning contract. Seat
inventory, ticket rules, minimum-connection policy and durable workflow state
remain explicitly unavailable until their assigned phases.

**Decisions:** [D-025 — Use a separate Vite frontend with URL-owned case selection](decisions.md#d-025--use-a-separate-vite-frontend-with-url-owned-case-selection); [D-026 — Give TanStack Query ownership of server state](decisions.md#d-026--give-tanstack-query-ownership-of-server-state); [D-027 — Expose purpose-built read-only browser APIs, not tool adapters](decisions.md#d-027--expose-purpose-built-read-only-browser-apis-not-tool-adapters).

**Parked:** LLM integration, agent loops, LangGraph, SSE, durable checkpoints,
recommendations, live inventory, ticket rules, prices, approval, booking writes,
production authentication, and real airline integrations.

**Next smallest step:** Review and commit the Phase 5 scope. Begin Phase 6 only
after an explicit request.

## Session 7 — 2026-08-12

**Phase:** Phase 6 — first explicit agent loop

**Built:** Added strict Pydantic decision and transient run-state contracts, an
application-owned `DecisionModel` protocol, safe projection of all five Phase 4
tool schemas, an exact read-only dispatcher, canonical repeated-call
fingerprints, a finite Python loop with deadline/turn/malformed guards, ten
recorded scenarios, an offline CLI, and an optional local-only Ollama HTTP
adapter. Added Phase 6 architecture, decisions, run instructions and learning
notes. No API route, frontend behavior, database schema or dependency changed.

**Verified:** Lock check and locked sync; intended imports; 185 focused agent and
tool tests; 354 non-database repository tests; all 18 isolated PostgreSQL
integration tests against a disposable `travelops_test`; Ruff lint and format;
strict mypy over 92 source files; wheel and source-distribution builds; frontend
clean install, Prettier, TypeScript and Oxlint; seven component tests; production
Vite build; and one Playwright operator journey. Dependency files, Phase 5 API
and frontend source were unchanged. The temporary PostgreSQL container and test
URL were removed after the gate.

**Concepts confirmed:** An agent loop is model request, typed decision,
application guard, optional tool execution, safe observation and repeat; JSON
Schema guides the model while Pydantic and the whitelist enforce contracts;
messages are context rather than trusted control state; bounded recovery prevents
unlimited context growth; deterministic recordings test orchestration without
claiming live-model quality; deterministic services, not model reasoning, decide
domain validity.

**Still unclear:** No local model has earned default selection. Smoke checks of
the installed Qwen 2.5 7B and 14B models did not reliably satisfy the strict
decision schema, so the Ollama adapter remains explicit and optional.

**Decisions:** [D-006 — Defer the model provider](decisions.md#d-006--defer-the-model-provider); [D-028 — Own the first agent loop and state in normal Python](decisions.md#d-028--own-the-first-agent-loop-and-state-in-normal-python); [D-029 — Fail closed around tool dispatch and run budgets](decisions.md#d-029--fail-closed-around-tool-dispatch-and-run-budgets); [D-030 — Make recorded scenarios the Phase 6 provider gate](decisions.md#d-030--make-recorded-scenarios-the-phase-6-provider-gate); [D-031 — Keep Ollama optional, local and behind the model boundary](decisions.md#d-031--keep-ollama-optional-local-and-behind-the-model-boundary).

**Parked:** LangGraph and minimal justified LangChain adaptation, durable
checkpoints, SSE and UI integration, recommendation evidence, model-quality
benchmarks, provider retry policy, approval and booking writes.

**Next smallest step:** Review and commit the Phase 6 scope. Begin Phase 7 only
after an explicit request, then reproduce these recorded outcomes with explicit
graph state, nodes, edges and terminal routing.

## Session 8 — 2026-08-13

**Phase:** Phase 7 — LangGraph orchestration and minimal LangChain integration

**Built:** Reproduced the Phase 6 recovery loop as an explicit compiled
LangGraph `StateGraph` with typed transient state, separately injected runtime
context, append-only node history, eight named application nodes, conditional
edges, verified terminal routing and inspectable state snapshots. Reused the
existing `DecisionModel`, strict decision contracts, ten recorded scenarios,
Phase 4 dispatcher, call fingerprints, budgets and safe failures. Extracted one
shared model-request builder so the manual loop and graph receive identical
safe context. Renamed the provider boundary from `model.py` to the clearer
`decision_model.py`. Added no checkpointer, API route, frontend integration,
write capability, default model or multi-agent behavior.

**Verified:** Lock check and locked environment sync; import smoke test;
30 focused Phase 7 tests; 215 agent/tool tests; 384 non-integration tests; all
18 isolated PostgreSQL integration tests; exact manual-loop/graph equivalence
for all ten recordings; Ruff lint and format; strict mypy over 95 source files;
wheel and source-distribution builds; frontend clean install, Prettier,
TypeScript, Oxlint, seven component tests, production build and one Playwright
journey. Python and npm dependency audits reported no known vulnerabilities;
high-confidence secret findings were reviewed as placeholders or deliberately
unsafe test data. Phase 5 API and frontend source remained unchanged, and the
temporary database container, Playwright results and test listeners were
removed. The audit required raising the development-only pytest range from 8.x
to `>=9.0.3,<10`; the lock selected 9.1.1 and the complete gate passed again.

**Concepts confirmed:** State, nodes, edges, reducers, routing, compilation,
runtime context, terminal states, state streaming and recursion limits;
LangGraph orchestration versus LangChain integrations; model proposals versus
application authority; inspectability without chain-of-thought; transient
execution versus future checkpoint durability.

**Still unclear:** Nothing required by the Phase 7 learning contract. A model
provider still needs a separate quality benchmark before it can become a
default.

**Decisions:** [D-032 — Express Phase 6 as an explicit LangGraph StateGraph](decisions.md#d-032--express-phase-6-as-an-explicit-langgraph-stategraph); [D-033 — Keep executable dependencies in LangGraph runtime context](decisions.md#d-033--keep-executable-dependencies-in-langgraph-runtime-context); [D-034 — Make recorded manual-loop equivalence the Phase 7 gate](decisions.md#d-034--make-recorded-manual-loop-equivalence-the-phase-7-gate); [D-035 — Defer LangGraph checkpointing to Phase 8](decisions.md#d-035--defer-langgraph-checkpointing-to-phase-8).

**Parked:** Durable checkpoints and resumption, SSE, background execution, API
and UI integration, new recommendation logic, inventory, pricing, ticket rules,
approval, booking writes, persistent workflow auditing, multi-agent design,
provider benchmarks and production integrations.

**Next smallest step:** Review the Phase 7 diff and learning notes. Begin Phase
8 durability only after an explicit request; do not add checkpointing as Phase
7 cleanup.

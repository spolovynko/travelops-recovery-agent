# Decision record

Record decisions when they become real constraints. Each entry should state the context, chosen option, alternatives, consequences, and evidence that could justify revisiting it.

## D-001 — Build in small, explained phases

**Status:** Accepted

**Context:** The primary goal is to learn agent engineering while producing a credible portfolio project. A large scaffold would make progress look fast while hiding the relationships between application services, tools, the agent loop, graph state, persistence, and approval.

**Decision:** Build one shippable capability per phase in small increments. Codex
explains and documents each mechanism, but learner questions or quizzes are not a
completion gate. A phase ends after its checks pass and its result is
demonstrated.

**Consequence:** Development may appear slower, but every commit should have a clear purpose and the final repository will document how the system evolved.

## D-002 — Start with one agent

**Status:** Accepted

**Context:** The workflow requires coordination across tools but does not initially require independent specialists.

**Decision:** Use one agent for the first release. Add multiple agents only if evaluation identifies a task that benefits measurably from specialization.

**Consequence:** State, traces, costs, and failures remain easier to understand.

## D-003 — Implement a manual loop before LangGraph

**Status:** Accepted

**Context:** LangGraph is the planned orchestration runtime, but learning requires understanding what it manages.

**Decision:** Implement a small, bounded, read-only tool loop with normal Python before representing the same behaviour as a graph.

**Consequence:** Phase 7 includes an explicit comparison between the manual loop and LangGraph.

## D-004 — Keep business rules outside the model and graph

**Status:** Accepted

**Context:** Seat availability, connection validity, permissions, approvals, and write consistency require deterministic and testable enforcement.

**Decision:** Put these rules in domain services. The model may select tools and explain validated results; the graph may coordinate services; neither becomes the enforcement boundary.

**Consequence:** Some workflows contain more conventional application code, which is intentional.

## D-005 — Use synthetic data only

**Status:** Accepted

**Context:** Airline bookings and passenger records are sensitive, and real integrations would distract from the agent-learning goals.

**Decision:** Use fictional airlines, passengers, bookings, policies, and operational events generated deterministically.

**Consequence:** The project can be public and reproducible, but it must not claim compatibility with a real airline system.

## D-006 — Defer the model provider

**Status:** Proposed

**Context:** The orchestration and tool contracts should not depend on one provider's response objects, while a real provider is eventually needed for tool-calling experiments.

**Decision:** Define a small application-owned model interface in Phase 6, then choose and document a provider using current availability, structured-output support, cost, and testing needs.

**Consequence:** No model SDK enters the foundation phases without a demonstrated need.

## D-007 — Commit to an advanced track after the first release

**Status:** Accepted

**Context:** The project should teach advanced agent engineering, including context management, replanning, concurrency, memory, routing, trajectory evaluation, agentic RAG, multi-agent coordination, and MCP. Adding these before a reliable baseline would make their effects difficult to understand or measure.

**Decision:** Complete and preserve Phase 11 as the first portfolio baseline, then implement all advanced topics as Phases 12–20. Every advanced phase requires a baseline comparison and may retain a documented negative result when added complexity does not improve the system.

**Consequence:** The complete project has a long learning path, but each advanced capability remains attributable, testable, and explainable.

## D-008 — Treat the UI as an observability and control surface

**Status:** Accepted

**Context:** A chat-only interface would hide workflow state, tool activity, deterministic validation, errors, and the exact action awaiting approval. The learning goal requires these mechanisms to be visible.

**Decision:** Build an operator console beginning in Phase 5 and extend it alongside later agent capabilities. The UI will display structured progress and evidence, while keeping business rules and approval enforcement on the server.

**Consequence:** Frontend work is part of the learning track, including typed API contracts, live-event handling, accessibility, browser testing, privacy, and safe approval design.

## D-009 — Use uv for the reproducible Python environment

**Status:** Accepted

**Context:** Every phase needs the same Python and dependency graph to be recoverable from repository files. A virtual environment alone isolates packages but does not record which versions should be installed.

**Decision:** Use uv to create the project-local `.venv`, resolve dependencies into `uv.lock`, and synchronize with `uv sync --locked --all-groups`. Pin the development interpreter to Python 3.12.10 in `.python-version`, while declaring support for Python 3.12 in `pyproject.toml`.

**Alternatives:** Use `venv` plus a hand-maintained requirements file, use pip-tools to compile requirements, or adopt Poetry or PDM as the project manager.

**Consequences:** Setup and dependency updates use one tool, and `--locked` fails instead of silently changing the resolved graph. Contributors need uv, lockfile changes must be intentional, and platform-specific resolutions remain visible in the lockfile.

**Revisit when:** A deployment target cannot consume the uv-managed workflow, the project becomes a multi-package workspace with different needs, or supported Python versions expand beyond 3.12.

## D-010 — Package from src with Hatchling

**Status:** Accepted

**Context:** Phase 0 needs a real importable distribution and should detect tests that succeed only because Python can see files at the repository root.

**Decision:** Place the package under `src/travelops_recovery_agent`, mark it as typed with `py.typed`, and use Hatchling as the PEP 517 build backend. Configure the wheel to contain the package and the source distribution to contain the source, tests, README, and build configuration. Keep Hatchling in the locked development group and use the synchronized backend for the Phase 0 build gate.

**Alternatives:** Use a flat package layout, use setuptools as the build backend, or defer distribution builds until the application has more code.

**Consequences:** Tests exercise an installed package boundary, build configuration stays small, and standard wheels and source distributions can be produced immediately. Hatchling becomes a build-time dependency and specialized future build requirements would need reevaluation.

**Revisit when:** The package needs compiled extensions, generated build artifacts, namespace-package behavior, or another requirement Hatchling does not serve cleanly.

## D-011 — Construct the API with an application factory

**Status:** Accepted

**Context:** Settings, middleware, logging, and later services need explicit assembly. Constructing a global FastAPI object during import would hide configuration loading and make isolated test applications harder to create.

**Decision:** Expose `create_app(settings: Settings | None = None) -> FastAPI`. Inject settings when supplied, otherwise validate them during application construction, and use Uvicorn's factory mode for real startup.

**Alternatives:** Export a module-level `app`, load global settings during import, or create a separate dependency-injection framework before the application needs one.

**Consequences:** Application assembly is explicit and testable with ordinary Python. Startup commands must include `--factory`, and process-level configuration belongs in or around the factory rather than module import.

**Revisit when:** Application assembly gains enough independently managed services to justify a dedicated composition object or dependency container.

## D-012 — Generate request IDs in middleware

**Status:** Accepted

**Context:** Every HTTP response and request log needs a shared correlation value, including routes added later. Concurrent asynchronous requests must not overwrite each other's value.

**Decision:** Generate a UUID for every request in middleware, store it in a `ContextVar`, include it in `X-Request-ID`, and reset the context in `finally`. Do not trust caller-provided request IDs in Phase 1.

**Alternatives:** Duplicate ID creation in each route, store it in a process global, use only `request.state`, or accept arbitrary IDs from clients.

**Consequences:** Routes inherit correlation automatically and logging can read request-local state. The ID covers this application process only and is not an authentication, audit-integrity, or distributed-tracing mechanism.

**Revisit when:** A trusted proxy or trace standard supplies validated correlation identifiers across multiple services.

## D-013 — Emit application logs as JSON

**Status:** Accepted

**Context:** Request activity needs machine-readable fields and correlation without allowing package imports to reconfigure global logging.

**Decision:** Use a small standard-library JSON formatter and explicitly configure the `travelops_recovery_agent` logger hierarchy during application construction. Record method, path, status, duration, and request ID while excluding query strings and settings values.

**Alternatives:** Emit prose logs, call `logging.basicConfig()` during import, configure the root logger, or add a structured-logging dependency immediately.

**Consequences:** Logs are parseable and dependency-free, and unrelated loggers remain untouched. The project owns a small formatter that may be replaced when tracing or a deployment logging platform introduces stronger requirements.

**Revisit when:** Phase 11 tracing, external log ingestion, schema versioning, or richer context demonstrates that a dedicated observability library is justified.

## D-014 — Keep the airline domain independent

**Status:** Accepted

**Context:** Passengers, flights, bookings, disruptions, policies, and recovery
cases will later appear through HTTP and PostgreSQL, but their business rules
must remain valid without either boundary.

**Decision:** Define immutable Pydantic domain models under `domain/`, separate
from FastAPI response schemas and future persistence models. Enforce local
invariants during model construction and expose explicit domain validation for
rules that require related objects.

**Alternatives:** Reuse API schemas as domain models, design SQLAlchemy models
early, or keep rules only in generators and tests.

**Consequences:** The domain is deterministic and usable before persistence,
but later phases must map between domain, API, and persistence representations.

**Revisit when:** Repeated mapping becomes demonstrably error-prone or a domain
concept requires behavior that Pydantic models cannot express clearly.

## D-015 — Validate a versioned dataset aggregate

**Status:** Accepted

**Context:** Individually valid objects can still contain duplicate IDs,
missing references, disconnected itineraries, or unrelated recovery-case
relationships. Generated files also need an explicit compatibility contract.

**Decision:** Use `SyntheticDataset` as the cross-record validation boundary.
Require schema version, generator version, seed, deterministic timestamp, and
provenance metadata, and reject unsupported version 1.0 inputs through normal
Pydantic validation.

**Alternatives:** Exchange unrelated JSON lists, rely on a future database for
foreign-key validation, or infer the schema from whichever fields are present.

**Consequences:** Files fail before reaching APIs or persistence and errors name
the broken relationship. Version changes must be deliberate and loaders support
only versions they understand.

**Revisit when:** A second schema version requires migration support or datasets
become large enough to require streaming validation.

## D-016 — Generate reviewed scenarios deterministically

**Status:** Accepted

**Context:** Later phases need repeatable demonstrations and test cases. Purely
random fixtures can be incoherent, while Faker or an LLM would add dependencies,
variability, provider concerns, or global state without improving ten curated
airline scenarios.

**Decision:** Define ten reviewed scenario blueprints and generate their safe
fictional attributes with a local `random.Random(seed)` instance. Derive all
timestamps and identifiers deterministically, preserve collection order, encode
one canonical UTF-8 JSON form, and expose generation and validation through a
standard-library `argparse` CLI.

**Alternatives:** Hand-maintain one large fixture, use global random functions,
add Faker, generate records with an LLM, or expose generation first through an
HTTP route.

**Consequences:** The same seed produces identical bytes without network access
or global-random mutation. Scenario variety is intentionally bounded and new
stories require reviewed blueprint changes.

**Revisit when:** The project needs hundreds of locale-specific profiles, a
streaming format, or evaluation demonstrates that the fixed catalogue lacks
important variation.

## D-017 — Use synchronous SQLAlchemy with explicit mapping

**Status:** Accepted

**Context:** Phase 3 needs PostgreSQL persistence without coupling the Phase 2
Pydantic domain to an ORM or introducing asynchronous control flow before it is
needed.

**Decision:** Use synchronous SQLAlchemy 2.x with Psycopg. Keep declarative
records under `persistence/` and translate through explicit mapping functions.

**Alternatives:** Turn domain models into ORM models, reuse API schemas, use raw
SQL throughout the application, or introduce async SQLAlchemy immediately.

**Consequences:** Domain rules remain independently testable and transaction
flow stays small and visible, at the cost of deliberate mapping code.

**Revisit when:** Measured concurrent database load shows synchronous workers
are a bottleneck or repeated mapping defects justify a more automated approach.

## D-018 — Use a normalized PostgreSQL schema with typed disruption details

**Status:** Accepted

**Context:** The dataset contains relational identities and three known
disruption variants. PostgreSQL should enforce important cross-record and
type-specific facts rather than storing the dataset as an opaque document.

**Decision:** Normalize entities and association tables. Store disruption
variants in typed nullable columns constrained according to their discriminator.

**Alternatives:** Store the complete dataset as JSONB, use one JSONB details
column, or create one table per disruption subtype.

**Consequences:** Keys and checks are inspectable and queryable, while adding a
new disruption variant will require an explicit model and migration change.

**Revisit when:** Disruption attributes become genuinely open-ended or variant
growth makes the current constrained-column representation unwieldy.

## D-019 — Let Alembic own schema history

**Status:** Accepted

**Context:** A database must evolve reproducibly from an empty state and later
from existing revisions without application imports silently changing it.

**Decision:** Use reviewed Alembic revisions as the only schema creation and
evolution path. Do not call `metadata.create_all()` during startup or import.

**Alternatives:** Create tables automatically from current ORM metadata, keep a
manual SQL file, or require developers to construct tables in pgAdmin.

**Consequences:** Schema changes are explicit, ordered, reversible when a safe
downgrade exists, and testable from zero. Every model change may require a new
reviewed migration.

**Revisit when:** Never for the ownership principle; tooling may change if a
future deployment platform requires another migration runner.

## D-020 — Place transactions around application workflows

**Status:** Accepted

**Context:** Dataset seeding spans many related rows and must never partially
commit. Future tools also need application behavior without arbitrary SQL access.

**Decision:** Application services define transaction-sized workflows through
an application-owned unit-of-work protocol. SQLAlchemy supplies the concrete
unit of work and repository. Repositories flush but never commit.

**Alternatives:** Commit inside each repository method, pass sessions through
API and tool layers, use a generic CRUD repository, or rely on implicit cleanup.

**Consequences:** A workflow commits or rolls back as one operation and future
adapters depend on application contracts. The small unit-of-work abstraction is
additional code that must remain focused.

**Revisit when:** A workflow genuinely spans external systems and needs a
different consistency strategy such as an outbox or saga.

## D-021 — Make development data management explicit and safe

**Status:** Accepted

**Context:** Deterministic fixtures must be easy to load repeatedly without
silently mixing datasets or allowing a reset command to erase production data.

**Decision:** Refuse ordinary seed on a non-empty database. Require `--replace`
for atomic replacement and `--confirm` for reset. Block reset in production and
require integration URLs to name the isolated `travelops_test` database.

**Alternatives:** Ignore duplicate seeds, upsert every row, reset automatically,
or run tests against the development database.

**Consequences:** Destructive intent is visible and tests clean up safely. This
is a controlled fixture workflow rather than a general data synchronization tool.

**Revisit when:** The project needs versioned reference-data upgrades or a
production-safe administrative lifecycle.

## D-022 — Use guarded Pydantic tool adapters and shared envelopes

**Status:** Accepted

**Context:** Future callers need stable schemas and narrow access without gaining
database sessions, arbitrary repositories, or framework-specific tool objects.

**Decision:** Use small callable adapter classes around application query
services. Define strict immutable Pydantic inputs, outputs, execution context,
safe failure taxonomy, audit metadata, and shared success/failure envelopes.
Publish their JSON schemas in a read-only registry.

**Alternatives:** Plain unvalidated functions, framework-specific LangChain
tools, HTTP endpoints for every tool, exceptions as the public contract, or a
generic database query capability.

**Consequences:** Tools work without an LLM and future model integration can
discover the same contracts. There is deliberate mapping between application
results and minimized tool outputs.

**Revisit when:** Phase 6 proves that a model-provider adapter needs additional
metadata; keep the application-owned contracts stable beneath it.

## D-023 — Enforce least privilege and absolute deadlines at each adapter

**Status:** Accepted

**Context:** Read access can still expose passenger or operational data, and a
future caller must not bypass authorization or continue stale work indefinitely.

**Decision:** Require an explicit per-tool permission and timezone-aware absolute
deadline in every execution context. Check both before application access, check
the deadline again afterward, fail closed, translate internal exceptions to safe
dependency failures, and do not retry automatically inside adapters.

**Alternatives:** Trust a prompt, authorize only at a future API route, use one
broad read permission, accept relative timeouts in deep layers, or hide retries
inside each tool.

**Consequences:** Every entry point has consistent local protection and clear
audit facts. Synchronous work cannot be forcibly cancelled mid-query, so the
deadline is cooperative; higher orchestration may later add cancellation and
policy-based retries.

**Revisit when:** Trusted authentication infrastructure supplies principals or
asynchronous external calls require active cancellation.

## D-024 — Separate deterministic candidate generation from validation

**Status:** Accepted

**Context:** The synthetic dataset has schedules and disruptions but no seat
inventory, prices, ticket rules, or minimum-connection policy. Search must not
turn missing evidence into invented validity.

**Decision:** Search deterministic direct and one-connection scheduled-flight
candidates in a bounded window. Validate stored-flight existence, route
continuity, and chronological order separately. Report inventory, ticket rules,
and minimum-connection policy as not evaluated or deferred.

**Alternatives:** Treat search results as valid, invent availability, combine
search and validation into one opaque operation, or postpone all candidate work.

**Consequences:** Results are repeatable and honest about evidence limits. A
candidate may be structurally valid without being a recommendable or bookable
option; later phases must add and recheck the missing facts.

**Revisit when:** Phase 9 introduces repository-backed availability, connection,
and ticket-rule evidence.

## Decision template

```markdown
## D-NNN — Short decision title

**Status:** Proposed | Accepted | Superseded

**Context:** What problem or constraint required a decision?

**Decision:** What was selected?

**Alternatives:** What reasonable options were considered?

**Consequences:** What becomes easier, harder, or constrained?

**Revisit when:** What evidence would justify reopening the decision?
```

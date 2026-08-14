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

**Status:** Accepted

**Context:** The orchestration and tool contracts should not depend on one provider's response objects, while a real provider is eventually needed for tool-calling experiments.

**Decision:** Define a small application-owned model interface in Phase 6. Use
recorded decisions as the required test provider and offer a local-only Ollama
HTTP adapter as an experiment. Require an explicit Ollama model; do not select a
default until a candidate reliably satisfies the structured contract.

**Consequence:** The loop has no provider SDK dependency and remains testable
offline. Live model suitability is an evaluated configuration choice rather
than an architectural dependency.

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

## D-025 — Use a separate Vite frontend with URL-owned case selection

**Status:** Accepted

**Context:** The manual dashboard needs typed routing, component tests and a
production build without coupling React source to Python packaging.

**Decision:** Keep React and TypeScript under `frontend/`, use npm with a locked
dependency graph, Vite for development/build, React Router for `/cases` and
`/cases/:caseId`, and a development proxy to FastAPI.

**Alternatives:** Server-render HTML from FastAPI, embed frontend source inside
the Python package, or keep the selected case only in component state.

**Consequences:** Frontend and backend have explicit build boundaries. Direct
URLs and refresh work, while both dependency ecosystems require their own gate.

**Revisit when:** Deployment packaging requires one distributable artifact.

## D-026 — Give TanStack Query ownership of server state

**Status:** Accepted

**Context:** Queue, workspace, search and validation requests need consistent
loading, failure, retry and cache behavior without copying authoritative facts
into local component state.

**Decision:** Use TanStack Query for HTTP-derived state. Keep only draft search
fields and current-session presentation state in React state. Store no passenger
or database data in local storage.

**Alternatives:** Hand-written effects and loading flags, a global client store,
or browser persistence.

**Consequences:** Refresh reloads business state and components remain focused
on rendering. The project gains one small server-state dependency.

**Revisit when:** Durable live workflow state arrives in Phase 8.

## D-027 — Expose purpose-built read-only browser APIs, not tool adapters

**Status:** Accepted

**Context:** Phase 4 tools and the browser serve different callers. Tool audit,
permission and execution envelopes are not useful UI view models.

**Decision:** Add four `/api/v1` routes that call application query services and
map to strict Pydantic UI views. Complex searches use POST bodies but never
mutate data. Keep `/health` unchanged and translate failures safely.

**Alternatives:** Invoke tool adapters from routes, expose persistence records,
or add a generic query endpoint.

**Consequences:** Browser contracts minimize data and can evolve independently
from model tools and storage. Some deliberate mapping code exists at the API
boundary.

**Revisit when:** Authentication or generated client contracts are introduced.

## D-028 — Own the first agent loop and state in normal Python

**Status:** Accepted

**Context:** Phase 6 must make every model call, state change, tool dispatch and
stop condition visible before an orchestration framework manages them.

**Decision:** Use a small `DecisionModel` protocol, a discriminated Pydantic
decision union, an immutable transient `AgentRunState`, and an explicit bounded
`for` loop. Do not add PydanticAI, LangChain or LangGraph in this phase.

**Alternatives:** Adopt an agent framework immediately, or use conversation
messages and provider response objects as implicit state.

**Consequences:** The mechanism is easy to inspect and test, but persistence,
resumption and graph visualization remain deliberately absent.

**Revisit when:** Phase 7 reproduces this behavior as an explicit LangGraph.

## D-029 — Fail closed around tool dispatch and run budgets

**Status:** Accepted

**Context:** A model can request unknown tools, repeat a call, return malformed
data, or consume unbounded time and turns. Prompt instructions cannot enforce
these limits.

**Decision:** Dispatch only the complete five-tool Phase 4 whitelist. Give each
call exactly its registered read permission, fingerprint canonical calls, stop
repeats before execution, cap turns and malformed retries, and check one absolute
deadline before and after external calls. Do not retry a tool automatically.

**Alternatives:** Trust the requested tool name, retry indefinitely, or infer a
nearby tool/argument when output is invalid.

**Consequences:** Failures are deterministic and safe, at the cost of requiring
the operator or a later workflow policy to resume some recoverable cases.

**Revisit when:** Phase 11 measures error-specific retry policies.

## D-030 — Make recorded scenarios the Phase 6 provider gate

**Status:** Accepted

**Context:** A phase gate must be repeatable without network access, credentials,
model downloads, sampling variance or a particular provider installation.

**Decision:** Record typed model decisions and Phase 4-shaped tool envelopes for
success, information request, direct finish, tool failure, unknown tool, repeat,
malformed recovery/exhaustion, turn exhaustion and deadline exhaustion. Validate
recorded arguments against the real Phase 4 input models.

**Alternatives:** Mock provider wire responses only, require a live model, or
assert only the final prose.

**Consequences:** Loop behavior has byte-for-byte deterministic evidence. Model
quality remains a separate evaluation problem rather than a hidden unit-test
dependency.

**Revisit when:** A reviewed live-model benchmark is added in Phase 11.

## D-031 — Keep Ollama optional, local and behind the model boundary

**Status:** Accepted

**Context:** Ollama offers a useful local structured-output experiment, but the
agent core should not inherit a provider SDK or silently trust an installed
model. Phase 6 smoke checks found that the available Qwen 2.5 7B and 14B models
did not reliably produce the strict decision shape.

**Decision:** Implement the `/api/chat` adapter with the Python standard-library
HTTP client, a strict response limit, non-streaming schema-constrained requests,
and a loopback-only endpoint. Require an explicit model name and configure no
default. Treat malformed content as a safe provider-independent model error.

**Alternatives:** Add the Ollama Python SDK, weaken the application contract,
choose one unverified local model, or make Ollama required for tests.

**Consequences:** No dependency or lockfile change is needed and provider faults
cannot leak raw responses. A future model must earn selection through contract
and task evaluation.

**Revisit when:** A local model passes a repeatable decision and task benchmark,
or another provider is evaluated against the same `DecisionModel` protocol.

## D-032 — Express Phase 6 as an explicit LangGraph StateGraph

**Status:** Accepted

**Context:** Phase 7 must make orchestration topology and intermediate state
inspectable without changing the verified provider, tool, validation, or safety
contracts established by Phase 6.

**Decision:** Build a low-level LangGraph `StateGraph` with typed state, eight
named nodes, explicit conditional-edge maps, safe node history, and separate
completion and failure terminals. Retain the manual loop as comparison code. Do
not use a prebuilt LangChain agent or PydanticAI.

**Alternatives:** Replace Phase 6 with `langchain.create_agent`, keep only the
manual loop, or let nodes return unrestricted dynamic destinations.

**Consequences:** Routing and state evolution are directly inspectable and ready
for later checkpointing. More explicit node and edge code is required, but the
application keeps control of every legal transition.

**Revisit when:** A future workflow shape demonstrates that a prebuilt agent or
subgraph removes material code without weakening the boundaries.

## D-033 — Keep executable dependencies in LangGraph runtime context

**Status:** Accepted

**Context:** Model clients, dispatchers and clocks are required by nodes but are
not investigation facts and must not enter inspectable or future persisted state.

**Decision:** Put the application-owned `DecisionModel`, exact read-only
dispatcher, actor identifier, and injectable clock in frozen `AgentGraphContext`.
Keep graph state limited to the validated run ledger and safe routing data.

**Alternatives:** Store executable objects in graph state, use globals, or let
nodes construct provider and tool dependencies themselves.

**Consequences:** State snapshots contain no executable services or credentials,
and dependencies remain injectable for deterministic testing. Callers must
provide a context for each run.

**Revisit when:** Phase 8 defines which context values must be reconstructed for
durable resumption.

## D-034 — Make recorded manual-loop equivalence the Phase 7 gate

**Status:** Accepted

**Context:** Framework adoption is not evidence of correctness. Phase 7 needs to
prove that graph routing preserves the already verified application behavior.

**Decision:** Replay all ten Phase 6 scenarios independently through both
orchestrators and require identical status, outcome, information request,
failure code, tool sequence, observations, evidence, model requests, and complete
serialized terminal `AgentRunState`.

**Alternatives:** Assert only graph terminal status, compare final prose, or use a
live probabilistic model as the primary gate.

**Consequences:** The graph has deterministic byte-for-byte behavioral evidence.
The suite intentionally says nothing about live-model quality.

**Revisit when:** The manual loop is retired after later durable behavior has an
equally strong stable reference and migration proof.

## D-035 — Defer LangGraph checkpointing to Phase 8

**Status:** Accepted

**Context:** LangGraph supports checkpoint persistence, interrupts and resume,
but these introduce thread identity, serialization, storage lifecycle,
at-least-once effects, and restart semantics beyond Phase 7's equivalence goal.

**Decision:** Compile the Phase 7 graph without a checkpointer. Expose in-process
state streaming for inspection only. Add no checkpoint backend dependency or
workflow tables.

**Alternatives:** Add an in-memory saver as a placeholder, persist checkpoints in
the business schema now, or combine graph adoption and durability in one phase.

**Consequences:** Phase 7 remains small and deterministic but cannot resume after
a process exit. Phase 8 must add durability explicitly rather than inheriting an
accidental checkpoint design.

**Revisit when:** Phase 8 begins and defines thread identifiers, persistence,
resumption, cancellation, progress events, and duplicate-effect protection.

## D-036 — Use the official PostgreSQL LangGraph checkpointer

**Status:** Accepted

**Context:** Phase 8 must survive process loss and preserve completed graph
boundaries. The project already depends on PostgreSQL and psycopg.

**Decision:** Lock `langgraph-checkpoint-postgres>=3,<4`, compile the existing
graph with `PostgresSaver`, run its supported setup migration, and use a strict
TravelOps deserialization allowlist.

**Alternatives:** In-memory or SQLite savers, copied saver tables, a custom
checkpointer, or hosted LangGraph services.

**Consequences:** Checkpoints survive restarts without another infrastructure
system. Saver table history remains owned by the supported package.

**Revisit when:** Deployment constraints require another supported backend.

## D-037 — Isolate execution persistence in a workflow schema

**Status:** Accepted

**Context:** Business truth, execution progress, and UI activity have different
meaning and retention.

**Decision:** Keep airline tables in `public`; place workflow runs, safe events,
and saver tables in `workflow`.

**Alternatives:** Put all tables in public, use another database, or treat
checkpoints as recovery-case records.

**Consequences:** Schema inspection and lifecycle policy cannot silently confuse
business facts with orchestration state.

**Revisit when:** Separate database credentials become operationally necessary.

## D-038 — Give each workflow run one distinct internal thread ID

**Status:** Accepted

**Context:** A recovery case can have historical investigations while LangGraph
requires a stable checkpoint thread.

**Decision:** Generate opaque run and thread IDs separately. Keep a one-to-one
run/thread mapping and a many-to-one historical run/case mapping.

**Alternatives:** Reuse case ID as thread ID or expose thread ID as the public run
identity.

**Consequences:** Domain and framework identity remain decoupled.

**Revisit when:** A deliberate multi-session thread design is introduced.

## D-039 — Resume only the latest checkpoint with no fresh initial input

**Status:** Accepted

**Context:** Passing initial state on resume risks restarting completed work.

**Decision:** Resume the same thread with `None` input after reconstructing
runtime context. Reject terminal and concurrently leased resumes.

**Alternatives:** Rebuild state from events, replay from the beginning, or expose
arbitrary checkpoint time travel through the operator API.

**Consequences:** Normal resumption follows the recorded next node and does not
repeat a committed tool boundary.

**Revisit when:** Diagnostic time travel receives its own safe API.

## D-040 — Prevent duplicate active runs with both an index and a lease

**Status:** Accepted

**Context:** HTTP retries and multiple backend processes can race.

**Decision:** Use a partial unique case index for active lifecycle values and an
expiring row lease with a unique owner per execution attempt.

**Alternatives:** Process-local locks, frontend button disabling, or an external
queue.

**Consequences:** Database constraints remain authoritative after process loss.

**Revisit when:** A distributed task queue is justified by measured load.

## D-041 — Make cancellation cooperative at graph boundaries

**Status:** Accepted

**Context:** Phase 7 model and database adapters are synchronous.

**Decision:** Persist an idempotent cancellation request and observe it before
each next node. State explicitly that an executing synchronous call may return
before cancellation completes.

**Alternatives:** Unsafe thread termination or falsely claim immediate cancel.

**Consequences:** Cancellation is predictable and does not corrupt checkpoints.

**Revisit when:** Dependencies offer reviewed cancellable async operations.

## D-042 — Persist only ordered safe UI events with bounded retention

**Status:** Accepted

**Context:** Operators need progress, but logs and checkpoints are unsafe UI
contracts and permanent business audit is out of scope.

**Decision:** Store versioned per-run events with monotonic sequences, recursive
sensitive-field rejection, bounded replay batches, and seven-day retention.

**Alternatives:** Stream logs, stream raw graph updates, or retain an unbounded
audit history.

**Consequences:** The UI gets stable activity without exposing prompts,
arguments, passenger rows, SQL, credentials, or internal exceptions.

**Revisit when:** A separately governed business audit system is designed.

## D-043 — Reconnect SSE from a snapshot-owned cursor

**Status:** Accepted

**Context:** Browsers disconnect, refresh, and automatically resend
`Last-Event-ID`.

**Decision:** Load the authoritative run first, stream after its sequence,
support `Last-Event-ID`, deduplicate IDs in React, and require snapshot reset when
retention creates a gap.

**Alternatives:** WebSockets, browser-only event state, or full replay on every
connection.

**Consequences:** Refresh and reconnect recover missed activity without treating
events as the workflow source of truth.

**Revisit when:** Bidirectional low-latency communication is required.

## D-044 — Reconstruct runtime context through application factories

**Status:** Accepted

**Context:** Checkpoints must not contain executable dependencies or secrets.

**Decision:** Rebuild provider adapters, the dispatcher, read-only tools, units
of work, actor, and clock for each claimed execution from stable configuration.

**Alternatives:** Serialize context, use globals, or store session objects in
graph state.

**Consequences:** Restart tests dispose original runtime objects and resume from
stable identifiers alone.

**Revisit when:** A dependency version must become explicit safe run metadata.

## D-045 — Keep read-only fingerprinted tools as the Phase 8 idempotency boundary

**Status:** Accepted

**Context:** Cross-system exactly-once execution is not supplied by checkpoints.

**Decision:** Permit only Phase 4 reads, retain call fingerprints in trusted
state, and add no automatic retry of non-idempotent work.

**Alternatives:** Assume checkpointing makes every tool exactly once or introduce
booking writes before effect-level idempotency exists.

**Consequences:** Normal resume does not repeat committed tool calls, and hard
failure during an in-flight call has bounded read-only consequences.

**Revisit when:** Phase 10 adds an effect ledger and idempotency keys.

## D-046 — Store synthetic recommendation evidence as business data

**Status:** Accepted

**Context:** Availability and ticket constraints must survive processes, support
missing-evidence tests, and be independently traceable.

**Decision:** Alembic `0003` adds normalized flight-availability and
booking-ticket-rule evidence with observation times and sources. Deterministic
seeding creates the synthetic rows.

**Alternatives:** Hard-code seat counts in validation, hide rules in fixtures,
or require an external airline service.

**Consequences:** Recommendations use repository facts and evidence can be
removed to prove safe failure. The evidence is still synthetic and not reserved.

**Revisit when:** A versioned external inventory or fare adapter is introduced.

## D-047 — Derive validity only from complete deterministic checks

**Status:** Accepted

**Context:** A model or caller must not be able to label an unsafe itinerary valid.

**Decision:** Application code evaluates existence, route, operational times,
minimum connection, group seats, ticket/policy compatibility, and current
status. Every check must pass; immutable contracts revalidate the derived flag.

**Alternatives:** Model self-verification, weighted validity scores, or treating
unknown evidence as a warning.

**Consequences:** Validity is reproducible and fail-closed. A model may explain
or compare only the resulting validated set.

**Revisit when:** New deterministic rules are added, not when model quality changes.

## D-048 — Rank valid options with a visible lexicographic key

**Status:** Accepted

**Context:** Operators need stable ordering without an opaque score that hides
missing evidence or subjective weights.

**Decision:** Rank by operational arrival, connections, connection waiting,
seat surplus, and stable option ID. Expose every input and explicit tradeoffs.

**Alternatives:** A hidden weighted score, model ranking, or arrival time alone.

**Consequences:** Repeated runs are stable and auditable. The chosen operational
preference remains visible and can be revised deliberately.

**Revisit when:** Reviewed operator feedback justifies different priorities or
scoped preferences.

## D-049 — Separate no-safe-option from insufficient-evidence escalation

**Status:** Accepted

**Context:** Complete evidence proving rejection is different from an inability
to validate because evidence is absent.

**Decision:** Use separate `no_safe_option` and `insufficient_evidence` outcomes,
plus complete/partial/insufficient evidence status. Neither may contain a
recommended itinerary.

**Alternatives:** One generic failure, low-confidence guesses, or silently
dropping candidates with missing facts.

**Consequences:** Operators can distinguish an operational dead end from a data
gap and pursue the correct escalation.

**Revisit when:** Escalation routing becomes a separately governed workflow.

## D-050 — Checkpoint the read-only recommendation as graph state

**Status:** Accepted

**Context:** Phase 9 results must preserve Phase 8 restart behavior without
changing Phase 6/7 equivalence or adding a second workflow engine.

**Decision:** Keep the original graph build as the equivalence default. The
application enables a `validated_recommendation` entry node that stores the
typed result in `AgentRunState`, emits one safe structured event, and checkpoints
before completion.

**Alternatives:** Recompute only in HTTP, store a separate recommendation row,
or require the model/tool loop to declare validity.

**Consequences:** Production recommendations need no model and resume without
duplicate work. Reads remain the only airline operations.

**Revisit when:** Phase 10 introduces proposals and effect-level idempotency.

## D-051 — Separate recommendation, proposal, approval, and execution

**Status:** Accepted

**Decision:** Persist an expiring proposal snapshot between Phase 9 output and
any decision, then keep execution as a separate freshly validated operation.

**Consequences:** No fluent model output or recommendation can authorize a
write; operators and audits can distinguish every boundary.

## D-052 — Bind decisions to version and itinerary fingerprint

**Status:** Accepted

**Decision:** Require one attributable decision containing the exact proposal
version and full itinerary fingerprint; prohibit creator self-approval.

**Consequences:** Changes and stale forms cannot inherit old authorization.

## D-053 — Recompute Phase 9 validation under execution locks

**Status:** Accepted

**Decision:** Lock safety-critical repository rows, rerun Phase 9 inside the
transaction, and require itinerary and evidence fingerprints to remain equal.

**Consequences:** Missing or changed status, schedule, seats, ticket, or policy
evidence stops execution and escalates.

## D-054 — Make PostgreSQL the idempotency and concurrency authority

**Status:** Accepted

**Decision:** Combine row locks with unique idempotency, proposal-change, and
booking-change constraints rather than trusting process memory.

**Consequences:** Retries and competing backend processes apply at most one
synthetic change.

## D-055 — Preserve original itinerary in an append-only change ledger

**Status:** Accepted

**Decision:** Keep original itinerary rows and record the synthetic replacement
with before/after flight identifiers in `booking_changes`.

**Consequences:** The phase proves a durable controlled effect without
pretending to update an airline system or destroying original evidence.

## D-056 — Pause the durable graph on authoritative proposal state

**Status:** Accepted

**Decision:** Checkpoint the proposal ID, release the workflow lease while it is
awaiting approval, and resume by reading the stored decision and using a
workflow-derived execution idempotency key.

**Consequences:** Browser or backend restarts cannot invent approval or repeat a
successful effect.

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

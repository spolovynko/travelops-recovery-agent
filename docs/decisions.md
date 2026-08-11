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

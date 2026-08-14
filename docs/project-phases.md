# Project phases

This is the quick reference. [The build plan](plan.md) contains Phases 0–11 and the first portfolio release. [The advanced roadmap](roadmap.md) contains Phases 12–20.

The [UI specification](ui.md) maps visible operator and developer-facing UI increments across the same phases, beginning with the manual dashboard in Phase 5.

| Phase | Focus | What is visibly shipped | Main learning question |
| --- | --- | --- | --- |
| 0 | Foundation | Reproducible package and quality commands | How does Python project tooling fit together? |
| 1 | API | Health endpoint, typed configuration, logs | What happens between an HTTP request and application code? |
| 2 | Domain | Repeatable synthetic disruption cases | Which facts and rules define a valid airline journey? |
| 3 | Persistence | Migrated and seeded PostgreSQL database | How do domain logic, transactions, and storage stay separate? |
| 4 | Tools | Tested read-only operational tools | What makes a tool safe and useful to a model? |
| 5 | UI | Manual disruption investigation dashboard | What must users see before any agent automation exists? |
| 6 | Manual agent | Bounded read-only tool loop | What does an agent framework normally do for us? |
| 7 | LangGraph and LangChain | Explicit stateful workflow with minimal model and tool adapters | How do framework integrations support a workflow without owning its rules? |
| 8 | Durability | Resumable workflow with live UI events | How does long-running work survive interruption? |
| 9 | Recommendation | Evidence-backed, validated recovery options | Where should model judgment stop and deterministic validation begin? |
| 10 | Approval | Safe prepare/approve/execute workflow | How can a human retain control of a consequential action? |
| 11 | Evaluation | Failure-tested, measured first portfolio release | How do we prove the agent works and state its limits honestly? |
| 12 | Context | Selected evidence and state-dependent tools | What should enter the model context, and why? |
| 13 | Planning | Inspectable plans and bounded replanning | How does a plan change without creating loops or repeated work? |
| 14 | Concurrency | Parallel investigation with partial results | Which operations can run together safely? |
| 15 | Memory | Scoped, correctable, expiring preferences | What should survive a run, and for how long? |
| 16 | Model routing | Capability-based routing and execution budgets | Which model capability is justified for each step? |
| 17 | Advanced evaluation | Trajectory metrics and regression gates | Did the agent reach the result efficiently and safely? |
| 18 | Agentic RAG | Versioned policy evidence with verified citations | How should an agent retrieve and trust policy evidence? |
| 19 | Multi-agent experiment | Measured specialist-agent comparison | Does specialization outperform the single-agent baseline? |
| 20 | MCP | Reusable, permission-aware operational interface | How can other AI hosts use the same capabilities safely? |

## How each phase improves the complete solution

### Phase 0 — foundation

- Creates a reproducible environment so every later capability can be installed, tested, and built consistently.
- Introduces quality gates that prevent packaging, formatting, typing, and basic code defects from accumulating.

### Phase 1 — API, configuration, and logging

- Gives the UI and future integrations a stable HTTP contract instead of coupling them directly to Python code.
- Adds validated configuration, request correlation, and logs so failures can be diagnosed from the beginning.

### Phase 2 — airline domain and synthetic cases

- Gives the application coherent passengers, bookings, flights, policies, and disruptions on which every workflow can operate.
- Creates repeatable scenarios that later become demos, integration tests, failure cases, and evaluation benchmarks.

### Phase 3 — persistence and service boundaries

- Makes business data durable across requests, browser refreshes, and application restarts.
- Separates domain rules from storage details so the database can evolve without spreading persistence logic throughout the system.

### Phase 4 — typed operational tools

- Gives the agent narrow, validated capabilities instead of unrestricted access to databases or internal services.
- Establishes permission, timeout, schema, and error contracts that make later automation safer and easier to test.

### Phase 5 — visual operator dashboard

- Gives operators one place to understand a disruption, inspect evidence, and compare recovery options.
- Establishes a manual workflow baseline so later agent automation can be compared against visible human-controlled behaviour.

### Phase 6 — explicit agent loop

- Adds the first model-controlled investigation while restricting it to bounded, read-only tool use.
- Makes tool selection, stop conditions, context growth, and malformed outputs understandable before a framework manages them.

### Phase 7 — LangGraph orchestration and minimal LangChain integration

- Replaces the manual loop with explicit state, nodes, edges, and routing that support more complex workflows.
- Introduces only the LangChain model, message, or tool adapters that demonstrate a concrete benefit after the manual-loop baseline exists.
- Makes execution easier to inspect, test, extend, and compare without moving business rules into the graph.

### Phase 8 — durability and live progress

- Allows investigations to survive backend restarts and resume without repeating completed work.
- Streams structured progress to the UI so operators can see tools, retries, evidence, and current status while the agent runs.

### Phase 9 — validated recommendations

- Prevents the agent from recommending itineraries that fail deterministic connection, availability, route, or ticket checks.
- Connects each recommendation to stored evidence and explicit tradeoffs, increasing operator trust and review quality.
- Distinguishes complete no-safe-option evidence from insufficient evidence and escalates both without guessing.
- Checkpoints the typed read-only result while leaving approval and booking effects to Phase 10.

### Phase 10 — human-approved rebooking

- Converts recommendations into useful actions while keeping the exact rebooking under human control.
- Adds proposal expiry, final validation, authorization, idempotency, and auditing so a write cannot execute casually or twice.
- Complete: the PostgreSQL-backed synthetic executor preserves the original itinerary, records the replacement once, and resumes durably around human approval.

### Phase 11 — failure testing, evaluation, and first release

- Tests the complete system against service failures, malicious inputs, permission violations, and difficult disruption cases.
- Produces reproducible quality, safety, latency, and cost evidence that makes the repository a credible portfolio release.
- Complete: freezes dataset `phase-11.0.0`, critical approval/write gates,
  privacy-safe trace schema, evaluation UI, Docker Compose stack, and CI evidence.

### Phase 12 — context engineering and tool governance

- Reduces confused decisions by sending the model only relevant, current, authorized evidence and tools.
- Controls token growth and records context choices, improving cost, latency, privacy, and debuggability.

### Phase 13 — planning and replanning

- Gives complex cases an explicit plan with dependencies, completion criteria, and progress that operators can inspect.
- Allows the workflow to adapt safely when seats disappear, tools fail, or new passenger constraints change the original assumptions.

### Phase 14 — parallel investigation

- Reduces recovery time by running independent status, policy, and availability checks concurrently.
- Handles deadlines and partial results explicitly, allowing useful progress even when one external capability is slow or unavailable.

### Phase 15 — scoped memory and personalization

- Preserves useful passenger preferences and operator feedback across appropriate cases without confusing them with current operational facts.
- Adds provenance, expiry, correction, deletion, and isolation controls so personalization does not create hidden privacy or staleness risks.

### Phase 16 — model routing and execution budgets

- Uses model capability according to task difficulty and risk, avoiding the same expensive path for every decision.
- Enforces call, token, time, and cost ceilings so the agent degrades safely instead of consuming resources without limit.

### Phase 17 — trajectory evaluation and regression gates

- Evaluates how the agent reaches an outcome, exposing unnecessary tools, invalid arguments, poor replanning, and unsafe intermediate behaviour.
- Adds regression gates that protect proven behaviour while prompts, models, tools, and orchestration continue to change.

### Phase 18 — policy RAG as an agent tool

- Lets the agent search a larger, versioned policy collection and support recommendations with effective, traceable sources.
- Adds retrieval evaluation, citation verification, temporal filtering, and injection defenses so retrieved text cannot silently control the workflow.

### Phase 19 — measured multi-agent orchestration

- Tests whether specialist policy and itinerary agents improve difficult cases beyond the established single-agent baseline.
- Preserves a feature-flagged fallback and removes unjustified complexity when specialization does not improve quality enough to offset cost and latency.

### Phase 20 — MCP operational interface

- Makes stable TravelOps tools reusable from other compatible AI hosts without rebuilding each integration separately.
- Carries schemas, permissions, approvals, rate limits, errors, and audit correlation across the protocol boundary so reuse does not weaken control.

## Standard phase rhythm

1. Read the phase definition and identify its constraints.
2. Codex selects and explains the smallest shippable increment.
3. Write or update tests while implementing in small increments.
4. Run the result and inspect the observable behaviour.
5. Review design, naming, typing, error handling, and boundaries.
6. Document the mechanisms in clear language without quizzing the learner.
7. Record decisions and a learning note.
8. Update progress. Commit only when the learner explicitly requests it.

## Gate rule

Do not begin the next phase while any of these remain true:

- The main branch is not runnable.
- Required checks fail.
- The result cannot be demonstrated.
- The phase notes do not yet explain a core mechanism clearly.
- A design decision exists only in chat and not in the repository.

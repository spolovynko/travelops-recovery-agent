# Advanced roadmap — Phases 12 to 20

This track begins only after the Phase 11 release is reproducible and evaluated. Advanced does not mean adding abstractions indiscriminately. Each phase starts from a measured limitation or a controlled experiment, preserves the working baseline, and must demonstrate whether the added capability helped.

## Advanced-track contract

1. Preserve Phase 11 as a tagged comparison baseline.
2. Change one important agent capability at a time.
3. Define the expected benefit and possible regression before implementation.
4. Add evaluation cases before or alongside the feature.
5. Compare quality, safety, latency, and cost against the previous phase.
6. Remove or disable an advanced feature if its measured value does not justify its complexity.
7. Keep deterministic validation, authorization, and approval boundaries unchanged.

## Phase 12 — context engineering and tool governance

### Why this phase exists

The core agent can accumulate messages, evidence, tool results, and schemas until irrelevant or stale information harms decisions. A production agent needs an explicit policy for what enters the model context and which tools are visible at each step.

### Ship

- A typed context builder separate from graph state
- Evidence selection by task, freshness, authority, and token budget
- Conversation summarization with links back to durable facts
- Dynamic tool exposure based on workflow state and operator permissions
- Context-size, cache-hit, and selected-evidence telemetry
- A developer-mode context inspector showing selected evidence and currently available tools
- Tests for stale, conflicting, oversized, and unauthorized context

### Learn to explain

- Durable state versus model context versus conversation history
- Context selection, ordering, compaction, and truncation
- Why summaries are derived views rather than sources of truth
- Tool discovery versus exposing every tool on every turn
- How token budgets affect quality, latency, and cost

### Experiment

Compare the Phase 11 full-context baseline with selective context across long cases, conflicting evidence, and repeated tool calls.

### Gate

The agent stays within a declared context budget, never exposes unauthorized tools, retains the evidence required for correct decisions, and does not regress task completion beyond the agreed tolerance.

## Phase 13 — explicit planning and replanning

### Why this phase exists

The core workflow knows its graph path but does not maintain a human-readable, testable plan that can change when assumptions fail.

### Ship

- A structured plan schema with steps, dependencies, status, and completion criteria
- A planning node for non-trivial cases
- Plan validation against allowed capabilities
- Progress updates linked to evidence and tool results
- Replanning triggers for lost seats, new constraints, failed tools, and conflicting information
- A plan-history view in the operator UI

### Learn to explain

- Workflow structure versus a model-generated task plan
- Planning, execution, reflection, and replanning boundaries
- Plan validation and bounded plan size
- Progress detection and loop prevention
- Why plans are inspectable artifacts rather than hidden reasoning

### Experiment

Compare fixed graph routing with explicit planning on complex multi-segment disruptions and injected mid-run changes.

### Gate

Every plan step maps to an allowed tool or deterministic operation, plan changes cite an observable trigger, completed work is not repeated, and simple cases do not pay unnecessary planning cost.

## Phase 14 — parallel investigation

### Why this phase exists

Flight status, policy lookup, and initial availability searches are often independent. Sequential calls increase recovery time, but concurrency introduces deadlines, partial results, cancellation, and state-merge problems.

### Ship

- Fan-out nodes for independent read operations
- A typed fan-in result with success, failure, and timeout states
- Per-tool deadlines and an overall investigation budget
- Cancellation of obsolete searches after replanning
- Deterministic state merge rules
- UI progress for simultaneous operations and partial completion

### Learn to explain

- Concurrency versus parallelism
- Async I/O and cooperative cancellation
- Fan-out, fan-in, barriers, and partial results
- Race conditions and deterministic reducers
- When sequential execution is safer or simpler

### Experiment

Measure sequential versus parallel p50 and p95 completion time under normal, slow, and partially failing tool conditions.

### Gate

Parallel execution improves the declared latency metric, produces deterministic merged state, respects deadlines, and does not duplicate or leak work after cancellation.

## Phase 15 — scoped memory and personalization

### Why this phase exists

Some preferences should survive a single run, while operational facts and temporary conclusions should not become permanent memory. The system needs deliberate memory scopes and retention rules.

### Ship

- Explicit working, case, passenger-preference, and operator-feedback memory scopes
- Provenance, confidence, timestamp, expiry, and owner on every memory record
- Consent-aware preference storage and deletion
- Retrieval rules that separate preferences from authoritative operational facts
- Conflict handling when a current instruction differs from stored preference
- UI controls to inspect, correct, and remove retained preferences

### Learn to explain

- Working memory, episodic memory, semantic memory, and durable business state
- Memory writing versus memory retrieval
- Staleness, provenance, consent, retention, and deletion
- Why generated summaries must not silently become facts
- Cross-user and cross-tenant isolation risks

### Experiment

Test repeat disruptions with useful preferences, outdated preferences, contradictory instructions, and attempted cross-passenger access.

### Gate

Memory improves the targeted personalization cases, current explicit instructions win over stored preferences, expired data is excluded, and isolation tests show zero cross-user leakage.

## Phase 16 — model routing and execution budgets

### Why this phase exists

Not every step needs the same model capability. Routing may reduce cost and latency, but it can also create inconsistent behaviour and harder debugging.

### Ship

- A model capability registry behind the application-owned model interface
- Deterministic routing by task type, risk, context size, and structured-output requirements
- Escalation to a stronger model after defined validation failures
- Per-case token, call, cost, and time budgets
- Budget-exhausted and degraded-service outcomes
- Routing and fallback telemetry
- A UI budget summary showing route choice, time, tokens, cost, and escalation reason

### Learn to explain

- Capability routing versus provider routing
- Quality, latency, and cost tradeoffs
- Fallback policy and escalation thresholds
- Budget enforcement and graceful degradation
- Why routing decisions must be reproducible and observable

### Experiment

Compare a single-model baseline with routed execution across simple, ambiguous, long-context, and high-risk cases.

### Gate

Routing reduces the chosen cost or latency metric without violating safety gates or materially reducing completion quality, and every escalation has a recorded reason.

## Phase 17 — trajectory evaluation and regression gates

### Why this phase exists

Final-outcome metrics can hide inefficient, unsafe, or lucky trajectories. Advanced evaluation must examine how the agent reached the result.

### Ship

- A versioned trajectory dataset with acceptable alternative paths
- Evaluators for tool choice, arguments, ordering, evidence coverage, plan changes, retries, and stop decisions
- Failure taxonomy and slice reports by disruption type and difficulty
- Deterministic graders where possible and calibrated model graders where necessary
- Statistical comparison of experiments with repeated runs
- CI smoke gates and scheduled full evaluation reports
- An evaluation dashboard for versions, failure slices, trajectories, latency, and cost

### Learn to explain

- Outcome, component, trajectory, and safety evaluation
- Exact-match versus set-based versus rubric-based grading
- Non-determinism, repeated trials, variance, and confidence intervals
- Evaluator reliability and model-grader bias
- Regression thresholds and release decisions

### Experiment

Re-evaluate the Phase 11 baseline and Phases 12–16 using one frozen benchmark and publish a comparison report.

### Gate

The evaluation suite catches seeded trajectory defects, reports uncertainty honestly, prevents declared critical regressions, and remains reproducible from documented commands.

## Phase 18 — policy RAG as an agent tool

### Why this phase exists

The core policy tool returns curated sections. Real policy collections require retrieval, citation, version awareness, and defenses against malicious or misleading content.

### Ship

- A versioned synthetic policy corpus with provenance and effective dates
- Policy ingestion, chunking, hybrid retrieval, and metadata filtering
- A typed `search_policy_evidence` tool returning passages and source identifiers
- Citation-support validation before recommendations are shown
- Temporal and jurisdiction-aware policy selection
- Indirect prompt-injection test documents and content isolation
- A policy-source viewer with citations, effective dates, and conflict warnings

### Learn to explain

- RAG as one bounded agent capability rather than the entire application
- Retrieval query formation and tool-use decisions
- Hybrid retrieval, reranking, and metadata filters
- Citation validity and conflicting policy evidence
- Indirect prompt injection and trusted-instruction boundaries

### Experiment

Compare curated lookup with retrieved policy evidence on paraphrases, rare conditions, outdated rules, conflicts, and malicious passages.

### Gate

Policy claims resolve to supporting, effective sources; outdated and malicious text cannot override system behaviour; and retrieval improves the declared benchmark without unacceptable latency.

## Phase 19 — measured multi-agent orchestration

### Why this phase exists

The single-agent system is the baseline. Specialized agents may improve complex cases, but they add coordination, context duplication, latency, cost, and new failure paths.

### Ship

- One bounded multi-agent design, such as a supervisor with policy and itinerary specialists
- Typed handoff contracts and minimal context transfer
- Clear ownership of the final recommendation
- Per-agent budgets, permissions, traces, and stop conditions
- Conflict-resolution and unavailable-specialist paths
- A feature flag that preserves the single-agent baseline
- A UI comparison view for specialist activity, handoffs, final ownership, latency, and cost

### Learn to explain

- Supervisor, handoff, and agent-as-tool patterns
- Context isolation and delegation contracts
- Coordination failure, duplicated work, and conflicting conclusions
- Per-agent authorization and observability
- When a deterministic service is better than another agent

### Experiment

Compare single-agent and multi-agent execution on the complex benchmark slice using quality, safety, latency, cost, and trajectory efficiency.

### Gate

The multi-agent version remains only if it produces a meaningful measured benefit. Otherwise the documented negative result and retained single-agent architecture complete the phase.

## Phase 20 — MCP operational interface

### Why this phase exists

The operational capabilities are now stable enough to expose through a standard protocol and reuse from another compatible AI host without weakening application controls.

### Ship

- An MCP server exposing the approved read tools and proposal workflow
- Resources for schemas, synthetic policy metadata, and capability documentation
- Local STDIO and remote Streamable HTTP modes
- Authentication, tenant context, tool filtering, rate limits, and audit correlation
- Approval requirements for consequential MCP tools
- Protocol, schema, permission, timeout, and malformed-client tests
- A demonstration using an external MCP-capable host
- An MCP diagnostics page showing capabilities, permissions, protocol checks, and audit correlation

### Learn to explain

- MCP host, client, server, tool, resource, and capability negotiation
- Protocol transport versus business authorization
- Local versus remote trust boundaries
- Tool discovery, schema evolution, and backward compatibility
- Approval and audit propagation across protocol boundaries

### Experiment

Run the same benchmark operations through the internal adapters and MCP interface, comparing correctness, latency, errors, and audit completeness.

### Gate

The MCP server passes protocol and authorization tests, exposes no capability beyond the caller's permissions, preserves approval requirements, and produces audit records traceable to the external request.

## Definition of done for the complete learning track

- Phases 0–20 each have a learning note and reproducible demonstration.
- The project retains a tested Phase 11 baseline and published advanced comparisons.
- Deterministic business and safety boundaries remain outside model control.
- Advanced features have measured benefits or documented negative results.
- The final UI makes state, plans, evidence, parallel work, memory, costs, approvals, and errors understandable to an operator.
- The README presents architecture, evaluation results, security boundaries, limitations, screenshots, and a short demo.

## Beyond Phase 20

Potential future products rather than committed phases:

- Real-time voice interface
- Multi-airline or multi-tenant deployment
- Hotel, meal-voucher, and ground-transport fulfillment
- Production cloud infrastructure and disaster recovery
- Integration with real airline systems under appropriate agreements

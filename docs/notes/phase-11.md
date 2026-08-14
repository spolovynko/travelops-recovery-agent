# Phase 11 notes — failure testing, evaluation, and first release

Phase 11 freezes the first portfolio baseline. Its completion gate is: the
documented stack starts, deterministic quality gates pass, benchmark results are
reproducible, and no benchmark booking write bypasses exact human approval and
fresh revalidation.

## Evaluation contract

The frozen dataset is `phase-11.0.0`, the package is `0.1.0`, and the default
seed is `42`. Every report records the Git revision, settings, prompt version,
provider/model identity, Python/platform metadata, dependency lock, thresholds,
and supported/unsupported claims. The deterministic benchmark uses recorded
application fixtures and makes no network or paid model call. It is therefore a
CI dependency. Live-model evaluation is optional, must identify its provider,
model and prompt, and must be published as a separate report.

Component evaluation checks schemas, classifiers, redaction, retries, API
translation, and the existing Phase 6–10 services in isolation. End-to-end
evaluation checks the final workflow outcome and safety counters across a whole
synthetic case. The Phase 11 harness deliberately stops short of Phase 17's
trajectory comparison and model grading.

## Dataset design and review

`phase_11_dataset.json` contains 22 minimal fictional cases covering successful
recovery, no safe option, incomplete evidence, bad connections, group seats,
ticket restrictions, policy conflict, stale availability, rejection, expiry,
provider failure, retries, restart, duplicate delivery, authorization, malformed
input, and injection text at passenger, policy, disruption, and tool-result
boundaries. Each case declares slices, allowed tools, prohibited actions,
required evidence, expected outcome, approval behavior, and acceptable
escalation reasons. Pydantic validates identifiers, relationships, slice
coverage, and the rule that an expected write always requires expected approval.

The benchmark is synthetic and small. It supports regression claims about these
declared cases; it cannot establish real-airline accuracy, production scale,
model semantic quality, or statistical generalization.

## Metrics and thresholds

The report includes completion, outcome, tool choice, argument validity,
repeated calls, recommendation validity, evidence completeness, escalation,
approval integrity, unauthorized attempts, booking writes, duplicates, retries,
latency, model calls, tokens, cost, and failure class. Results are also grouped
by routine, complex, failure-recovery, safety, authorization, and adversarial
slices.

Release thresholds are declared in code before a run: at least 95% completion;
100% outcome accuracy, valid arguments, and approval integrity; and exactly zero
unapproved writes, duplicate writes, and unauthorized execution attempts. The
last three are critical gates and cause exit code 2. Test-only seeded defects
prove that approval bypass and duplicate execution fail the gate.

Harness latency is observed wall-clock time and varies by machine. The
deterministic run makes zero model calls, so zero tokens and cost are genuinely
measured for that run. An unavailable live-provider value must remain `null` with
`not_available`; it must never silently become zero.

## Failure injection and recovery policy

`FailureInjector` enumerates provider timeout, malformed result, invalid tool
arguments, rate limit, transient provider failure, database rollback, lost
availability, missing/cancelled/changed flights, policy change, SSE disconnect,
workflow interruption, checkpoint/execution restarts, duplicate delivery,
retry, and replay. A seed and explicit test/development setting control it.
Pydantic rejects failure injection whenever the environment is production.

Errors are classified as retryable, non-retryable, authorization-related,
validation-related, stale evidence, or operator-action-required. One owning
layer may perform at most five attempts with explicit exponential backoff.
Validation, authorization, and stale-evidence failures stop immediately.
Consequential writes cannot use this retry helper without an explicit
idempotency proof; normal proposal execution retains the Phase 10 transaction,
row lock, unique constraints, and stored-result replay.

This avoids retry storms: the model, tool, workflow, API and UI do not each
silently retry the same failure. When a bounded retry exhausts, durable state and
safe evidence remain, while the operator receives a stable actionable message.

## Indirect injection and authorization boundaries

Passenger text, disruption descriptions, policy text, model output, and tool
results are untrusted data. They may be shown only through escaped React text or
bounded trace metadata. They cannot add tools, grant roles, approve a proposal,
change an itinerary fingerprint, or authorize execution. Pydantic and
deterministic services own validation; application/database code owns proposal
eligibility, exact approval, fresh revalidation, idempotency, and writes.

The demo still uses explicit actor headers and is not authentication. A real
deployment needs an identity provider, tenant/case authorization, governed role
assignment, and protection against identifier enumeration. Phase 11 tests the
application's existing role and exact-approval boundaries but does not claim
that synthetic headers are a production authorization system.

## Privacy-safe observability

`travelops.trace.v1` correlates request, workflow, case, proposal and evaluation
references with model/tool/node/retry/interrupt/terminal events. Events can
carry duration, status, error class, retry count, token count, and cost source.
Passenger-, prompt-, credential-, authorization-, token-, cookie-, secret-, and
raw-idempotency fields are recursively redacted; untrusted keys and strings are
bounded. Evaluation trace export is JSON Lines for per-case debugging.

The existing JSON logger remains sufficient for this local baseline: it already
adds server-generated request IDs and durations, while business/workflow records
provide durable correlation. No telemetry dependency was added without a
measured need. Production still requires a protected collector, access control,
retention/deletion policy, clock synchronization, alerting, sampling, and an
explicit policy for trace export. Local evaluation artifacts should be retained
only as long as needed for regression evidence; they contain identifiers and
safe diagnostics, never raw passenger or prompt content.

## UI and release reproducibility

`/evaluations` shows evaluated version, dataset, seed, status, timestamp,
completion, safety, latency, token/cost accounting, slices, failed cases, and
limitations. It labels the report deterministic and keeps live-model evidence
separate. The page uses semantic headings/tables, an announced status, visible
focus, keyboard-scrollable tables, escaped content, responsive layout, and safe
error/retry handling.

The backend and frontend have production-minded multi-stage images. Compose
starts PostgreSQL, runs Alembic once, waits for backend health, and then exposes
the frontend. Secrets remain environment variables. GitHub Actions runs locked
installs, lint/format/type checks, migrations, all backend tests, the frozen
benchmark, distributions, component tests, production build, Playwright, and
image builds without model credentials; reports and failure evidence are
artifacts.

## Reproduce the baseline

```powershell
uv lock --check
uv sync --locked --all-groups
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest -m "not integration"
uv run --locked python -m travelops_recovery_agent.evaluation.cli validate
uv run --locked python -m travelops_recovery_agent.evaluation.cli run --seed 42 --output-dir reports
uv run --locked python -m build --no-isolation

Set-Location frontend
npm.cmd ci
npm.cmd run format:check
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test -- --run
npm.cmd run build
npm.cmd run test:e2e
```

For the complete local stack, set a strong alphanumeric
`TRAVELOPS_POSTGRES_PASSWORD`, run `docker compose up --build -d`, seed once with
`docker compose --profile tools run --rm seed`, and open
`http://127.0.0.1:8080`. The demo path is Cases → CASE-0002 → prepare proposal →
approve exact version → execute → inspect immutable audit → Evaluation.

## Remaining production work

Production readiness still requires real authentication and tenant
authorization, external booking-provider idempotency and reconciliation,
inventory holds, durable distributed work queues, managed secrets, TLS/network
policy, backups and restore drills, high-availability deployment, load and chaos
testing, security review, dependency/container scanning, governed telemetry,
incident response, and live-model evaluation at representative scale.

Phase 11 is frozen because Phases 12–20 need a stable comparison point. Future
context, planning, concurrency, memory, routing, RAG, multi-agent, and MCP work
must preserve these safety gates and compare against dataset `phase-11.0.0`
instead of silently changing the baseline.

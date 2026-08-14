# Phase 12 notes — context engineering and tool governance

Phase 12 preserves the frozen v0.1.0 workflow and adds an explicit boundary for
what a model may see and which capability schemas may be advertised. The phase
gate is deterministic: every Phase 11 case still passes; every Phase 12 build
fits its declared budget or stops before a model call; mandatory evidence
coverage is complete; stale, unauthorized, cross-case, and prohibited content
is absent; and consequential tools never appear outside the approved execution
state.

## Three different kinds of state

- Durable business and workflow state is authoritative. PostgreSQL records,
  proposals, approval decisions, execution ledgers, graph checkpoints, and safe
  workflow events retain their existing ownership and lifecycle.
- Conversation history is an ordered interaction record. It may contain
  repetition, stale claims, hypotheses, or sensitive text and is not trusted
  merely because it appeared earlier.
- Constructed model context is a transient, versioned, derived view. It is
  rebuilt for one task and node, uses explicit evidence and capability policy,
  and is discarded after the model boundary.

`ContextItem` is intentionally not a database entity, graph-state member, raw
tool result, or provider message. It carries a stable evidence ID, source type,
case and authorization scope, task/node applicability, authority, creation/
observation/expiry times, freshness, sensitivity, labelled token estimate,
priority, relevance, conflict/supersession links, source version, and durable
fact IDs. `ContextBuildResult.canonical_json()` provides sorted, deterministic
serialization. Selection latency and cache-hit status are runtime observations;
the semantic build ID excludes them.

## Selection, ordering, compaction, and budget failure

The `phase-12.1` policy first rejects evidence that is cross-case,
out-of-scope, secret, untrusted, stale, expired, superseded, task-inapplicable,
node-inapplicable, or below the relevance threshold. Conflicts select the item
with higher authority, newer observation, higher priority, then stable evidence
ID. The surviving order is:

1. mandatory before optional;
2. higher priority;
3. higher authority;
4. higher relevance;
5. newer observation;
6. stable evidence ID.

Tool-schema estimates count against the same declared step budget. Values use
`estimated_characters_div_4`, are always labelled estimates, and are never
presented as provider-exact tokens. A matching tokenizer or provider usage
report would be needed for exact counts.

Optional oversized evidence may become a bounded derived view that retains its
source and durable fact references. Mandatory safety, authorization, approval,
and execution evidence is never truncated or compacted to force a call through.
Missing, invalid, conflicting, or oversized mandatory evidence returns
`safe_escalation` with no selected model context.

## Conversation compaction

The required CI path uses a deterministic compactor rather than a model. It
keeps facts, decisions, hypotheses, completed work, unresolved constraints, and
operator instructions in separate fields; only includes privacy-safe turns
that cite durable evidence; and records source versions. Validation rejects a
summary if a referenced fact disappears or changes version. A summary is always
a derived view and cannot override newer or more authoritative evidence.

An optional future model summarizer may improve prose, but it must produce this
contract, pass the same provenance and privacy validation, and retain the
deterministic CI path. Credentials, raw prompts, secrets, and unnecessary
passenger data are excluded before summarization.

## Dynamic capability exposure

`ToolGovernancePolicy` starts with no capabilities. It evaluates seven schemas:
the five Phase 4 reads, proposal preparation, and execution. A schema is exposed
only when task, workflow node, permission, role, workflow state, and approval
requirements match. An execution schema requires the `recovery_operator` role,
`rebooking:execute`, exact `approved` status, the proposal-approval node, the
execute task, and an executable paused/running state.

This is schema visibility, not authority. The Phase 4 adapters still validate
permissions and inputs. Proposal and execution services still require stored
state, exact attributable approval, fresh locked revalidation, an idempotency
key, database uniqueness, and transactional audit. Prompt or tool-output text
cannot add a capability or grant a role.

`build_governed_model_request` projects only selected context items, selected
safe observations, and exposed read schemas to the existing application-owned
provider boundary. The original `build_model_request` remains the frozen Phase
11 comparison path.

## Cache correctness

The in-memory cache is bounded and optional. Its SHA-256 key includes context,
policy, tool-policy and cache versions; case and operator identity; role,
permissions, authorization scopes; task and workflow node; workflow/approval
state; token budget; build time/freshness input; complete item fingerprints and
source versions; and summary versions. A case-scoped invalidation method removes
entries after evidence or authorization changes. Tests prove misses across
cases, roles, permissions, and source versions and prove a case invalidation
after a durable fact update.

This local cache does not claim distributed invalidation. A multi-process
deployment needs an event-driven or shared versioned invalidation mechanism.

## Inspector and observability

`GET /api/v1/developer/context-inspector` and `/developer/context` show schema/
policy version, budget and remaining estimate, evidence decisions, selected
safe text, authority/freshness, conflicts/supersession, cache, latency, and
exposed/denied tools with reasons. Production returns 404. React renders text,
uses labelled controls and a keyboard-scrollable evidence region, announces
status, and has responsive loading, error, empty, and safe-escalation states.

Phase 12 extends `travelops.trace.v1` with context-build, compaction, and
tool-governance kinds. Context events record versions, safe references, counts,
budget estimates, estimate method, cache status, conflicts, capability counts,
latency, and safe failure. The existing recursive redaction still applies; no
second telemetry system was introduced.

## Dataset and experiment

`phase_12_dataset.json` contains 13 reviewed cases: long conversation, repeated
tool results, oversized evidence, stale evidence, conflicting evidence,
superseded facts, unauthorized/cross-case evidence, permission changes,
tool-output prompt injection, excessive passenger data, mandatory evidence near
the limit, cache invalidation after evidence change, and state-dependent tools.
Each declares selected, mandatory, and prohibited evidence; exposed and
prohibited tools; expected compaction/escalation; and final workflow outcome.

The experiment compares:

- A: Phase 11-style full context and broad five-read-tool visibility.
- B: `travelops.context.v1` selection with `phase-12.1` capability governance.

The required run is a recorded deterministic fixture with no model call,
provider credential, provider tokenizer, or network dependency. It therefore
does not measure live-model semantic quality.

| Metric | Full context | Selective context |
| --- | ---: | ---: |
| Cases passed | 13/13 | 13/13 |
| Task/outcome accuracy | 100% / 100% | 100% / 100% |
| Mandatory-evidence coverage | not governed | 100% |
| Stale / unauthorized / cross-case included | 1 / 1 / 1 | 0 / 0 / 0 |
| Correct tool exposure | 23.08% | 100% |
| Prohibited tool exposure | 4 | 0 |
| Estimated context tokens | 21,127 | 8,721 |
| Estimated reduction | 0% | 58.72% |
| Cache hit / miss | not applicable | 1 / 14 |
| Compacted items | 0 | 2 |

Selection latency is machine-dependent and recorded in the generated JSON and
Markdown reports. It is evidence about this harness on the current machine,
not a production service-level objective.

Seeded `cross_case_cache`, `write_tool_leak`, and `mandatory_drop` defects each
make the matching gate fail. Phase 11 retains 22/22 cases, seven approved
synthetic writes, and zero unapproved, duplicate, or unauthorized writes.

## Reproduce and demonstrate

```powershell
uv lock --check
uv sync --locked --all-groups
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest -m "not integration"
uv run --locked pytest -m integration

uv run --locked python -m travelops_recovery_agent.evaluation.cli validate
uv run --locked python -m travelops_recovery_agent.evaluation.cli run --seed 42 --output-dir reports
uv run --locked python -m travelops_recovery_agent.context_evaluation.cli validate
uv run --locked python -m travelops_recovery_agent.context_evaluation.cli run --seed 42 --output-dir reports
uv run --locked python -m build --no-isolation

$env:TRAVELOPS_ENVIRONMENT = "development"
uv run --locked uvicorn travelops_recovery_agent.api.app:create_app --factory --host 127.0.0.1 --port 8000

Set-Location frontend
npm.cmd ci
npm.cmd run format:check
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test -- --run
npm.cmd run build
npm.cmd run test:e2e
```

For PostgreSQL, migration, seed, Compose, and proposal execution commands, use
the README's existing complete-stack instructions. Phase 12 adds no migration
or business-state table.

## Supported claims and production gaps

The reports support deterministic claims only for the reviewed fixtures: exact
selection order, safe mandatory-budget failure, rejection counts, tool-schema
governance, cache isolation, context reduction, and unchanged Phase 11 safety
counters. They do not support claims about live-model quality, provider token
use, cost, real passenger privacy, production identity, tenant isolation,
distributed cache coherence, external tool-schema drift, or real-airline
correctness.

Production still requires authenticated tenant-scoped identity, server-derived
roles and case scopes, distributed invalidation, protected inspector access if
one is ever deployed, governed telemetry storage/retention, provider-specific
token/cost measurement, representative live-model evaluation, scale/load tests,
and operational alerting. The developer inspector's synthetic safe preview is
not a production evidence browser.

## Portfolio screenshots

- [Context inspector and budget accounting](../screenshots/phase-12-context-budget.png)
- [Evidence inclusion and exclusion reasons](../screenshots/phase-12-evidence-reasons.png)
- [Governed tool exposure](../screenshots/phase-12-tool-governance.png)
- [Full-context versus selective-context comparison](../screenshots/phase-12-evaluation-comparison.png)

# Architecture boundaries

This document records the intended responsibility boundaries. It will become more concrete as phases replace assumptions with working code.

## Runtime view

```mermaid
flowchart TB
    subgraph Browser
        UI["React operator console"]
    end

    subgraph Application
        API["FastAPI routes"]
        STREAM["SSE progress stream"]
        GRAPH["LangGraph orchestration"]
        APPROVAL["Approval service"]
        TOOLS["Typed tool adapters"]
        DOMAIN["Deterministic domain services"]
    end

    subgraph Data
        BUSINESS[("Business database")]
        CHECKPOINTS[("Workflow checkpoints")]
        AUDIT[("Audit records")]
    end

    UI --> API
    API --> GRAPH
    GRAPH --> TOOLS
    TOOLS --> DOMAIN
    DOMAIN --> BUSINESS
    GRAPH --> CHECKPOINTS
    GRAPH --> STREAM
    STREAM --> UI
    UI --> APPROVAL
    APPROVAL --> DOMAIN
    APPROVAL --> AUDIT
```

## Boundary rules

1. The UI never decides whether an itinerary is valid.
2. The model never queries the database directly.
3. Tools call application services; they do not contain duplicated business rules.
4. Authorization is enforced inside the application boundary, not in a prompt.
5. The graph coordinates steps but is not the source of business truth.
6. Business records and graph checkpoints have different schemas and lifecycles.
7. A recommendation references stored evidence and validated candidate identifiers.
8. A write requires a stored proposal, explicit approval, a final validation, and an idempotency key.
9. Logs and traces exclude raw secrets and minimize synthetic passenger details.
10. External or retrieved text is treated as untrusted data, never as system instructions.

## Phase 4 operational read path

```mermaid
flowchart LR
    CALLER["Manual CLI or future agent"] --> CONTRACT["Typed input + execution context"]
    CONTRACT --> ADAPTER["Tool adapter: permission, deadline, safe errors, audit"]
    ADAPTER --> SERVICE["Application query service"]
    SERVICE --> REPOSITORY["Application-owned repository protocol"]
    REPOSITORY --> POSTGRES[("PostgreSQL")]
    SERVICE --> RULES["Deterministic domain validation"]
    ADAPTER --> RESULT["Typed success or failure"]
```

The registry publishes schemas but does not execute tools. The CLI is an outer
composition root that constructs persistence and injects an application service
into adapters. Adapters never receive an engine, session, repository, SQL string,
or write capability. `GET /health` remains the only current HTTP route involved;
tools are not API endpoints.

The detailed screen model, event contract, approval experience, accessibility requirements, and frontend testing strategy are in [ui.md](ui.md).

## Phase 5 manual dashboard path

```mermaid
flowchart LR
    BROWSER["React + TypeScript browser UI"] -->|"versioned JSON"| API["FastAPI /api/v1 recovery routes"]
    API --> VIEWS["Frontend-oriented Pydantic view models"]
    API --> SERVICE["OperationalQueryService"]
    SERVICE --> RULES["Deterministic domain rules"]
    SERVICE --> REPOSITORY["RecoveryDataRepository protocol"]
    REPOSITORY --> SQLA["SQLAlchemy adapter"]
    SQLA --> POSTGRES[("PostgreSQL")]
```

Phase 5 routes are browser APIs, not Phase 4 tools. They compose the same
application services for a different caller and return UI-specific views. React
never imports tool contracts, repository types or persistence records. Search
and validation use POST for typed query bodies but perform no business write.
The URL identifies the case; refresh reloads authoritative facts from the API.

## Agent state sketch

The exact schema belongs to Phase 7. The working hypothesis is:

```text
RecoveryState
├── case_id
├── operator_id
├── status
├── current_step
├── collected_evidence
├── tool_history
├── retry_counts
├── candidate_itinerary_ids
├── validated_itinerary_ids
├── recommendation
├── pending_proposal_id
├── approval_status
├── error
└── final_outcome
```

Store identifiers and structured facts in state. Do not use formatted prompt text as the durable source of truth.

## Initial tool catalogue

| Tool | Kind | Responsibility |
| --- | --- | --- |
| `get_booking` | Read | Return the authorized booking and itinerary view |
| `get_flight_status` | Read | Return the current synthetic operational status |
| `get_disruption_policy` | Read | Return relevant policy sections with references |
| `search_alternative_itineraries` | Read | Produce scheduled-flight candidates; inventory and ticket rules remain explicitly unevaluated |
| `validate_itinerary` | Read | Return structured rule results for a candidate |
| `prepare_rebooking` | Proposal | Store an immutable proposed change without executing it |
| `execute_rebooking` | Write | Execute one approved, current, idempotent proposal |

## Open architecture questions

- Which recovery rules belong in the first benchmark?
- Should policy lookup begin as deterministic section retrieval or keyword search?
- Which events must the UI receive live, and which can be loaded from the API?
- Should graph checkpoints share PostgreSQL with business data while remaining logically separated?
- What evidence is safe and useful to retain in traces?

Answers are recorded in [decisions.md](decisions.md) when the responsible phase reaches them.

Phase 4 resolved the read-tool boundary questions in D-022 through D-024.
Proposal and write tools remain future catalogue entries, not registered or
implemented capabilities.

## Advanced evolution

The Phase 11 architecture remains the baseline. [The advanced roadmap](roadmap.md) evolves it through controlled additions:

```mermaid
flowchart LR
    BASE["Phase 11 baseline"] --> CONTEXT["Context and tool governance"]
    CONTEXT --> PLAN["Planning and replanning"]
    PLAN --> PARALLEL["Parallel investigation"]
    PARALLEL --> MEMORY["Scoped memory"]
    MEMORY --> ROUTING["Model routing"]
    ROUTING --> EVAL["Trajectory evaluation"]
    EVAL --> RAG["Policy RAG tool"]
    RAG --> MULTI["Multi-agent experiment"]
    MULTI --> MCP["MCP interface"]
```

Each addition must preserve the boundary rules in this document and remain removable behind a stable interface or feature flag when the phase is experimental.

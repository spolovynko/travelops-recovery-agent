import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError, recoveryApi } from "../../api/client";
import type {
  AlternativeCandidate,
  ItineraryValidation,
  RecommendationOption,
  ProposalWithAudit,
  RecoveryCaseWorkspace,
} from "../../api/models";
import { ErrorState, LoadingState } from "../../components/AsyncState";
import { StatusBadge } from "../../components/StatusBadge";
import { WorkflowActivity } from "./WorkflowActivity";

const exactDate = (value: string) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
const duration = (minutes: number) =>
  `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
const label = (value: string) => value.replaceAll("_", " ");

export function RecoveryWorkspacePage() {
  const { caseId = "" } = useParams();
  const query = useQuery({
    queryKey: ["recovery-case", caseId],
    queryFn: () => recoveryApi.getCase(caseId),
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 404) && count < 1,
  });

  if (query.isPending)
    return (
      <div className="page">
        <LoadingState label={`Loading case ${caseId}`} />
      </div>
    );
  if (
    query.isError &&
    query.error instanceof ApiError &&
    query.error.status === 404
  )
    return <NotFound caseId={caseId} />;
  if (query.isError)
    return (
      <div className="page">
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </div>
    );
  return <Workspace data={query.data} />;
}

function NotFound({ caseId }: { caseId: string }) {
  return (
    <div className="page">
      <section className="state-card state-error">
        <p className="eyebrow">Not found</p>
        <h1>Case {caseId} is unavailable</h1>
        <p>The URL does not identify a recovery case returned by the server.</p>
        <Link className="button" to="/cases">
          Return to queue
        </Link>
      </section>
    </div>
  );
}

function Workspace({ data }: { data: RecoveryCaseWorkspace }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const workflowRunId = searchParams.get("run");
  const defaults = data.search_defaults;
  const [earliest, setEarliest] = useState(defaults.earliest_departure);
  const [latest, setLatest] = useState(defaults.latest_arrival);
  const [connections, setConnections] = useState<0 | 1>(
    defaults.max_connections,
  );
  const [validations, setValidations] = useState<
    Record<string, ItineraryValidation>
  >({});
  useEffect(() => {
    setEarliest(defaults.earliest_departure);
    setLatest(defaults.latest_arrival);
    setConnections(defaults.max_connections);
    setValidations({});
  }, [data.case_id, defaults]);
  const search = useMutation({ mutationFn: recoveryApi.search });
  const validate = useMutation({
    mutationFn: recoveryApi.validate,
    onSuccess: (result) =>
      setValidations((current) => ({
        ...current,
        [result.candidate_id]: result,
      })),
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setValidations({});
    search.mutate({
      case_id: data.case_id,
      earliest_departure: earliest,
      latest_arrival: latest,
      max_connections: connections,
    });
  };

  return (
    <div className="page workspace">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/cases">Disruption queue</Link>
        <span aria-hidden="true">/</span>
        <span>{data.case_id}</span>
      </nav>
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Recovery workspace · {data.case_id}</p>
          <h1>{data.title}</h1>
          <p>
            {data.itinerary[0]?.origin} → {data.itinerary.at(-1)?.destination} ·
            Booking {data.booking_id}
          </p>
        </div>
        <span className="readonly">
          <span aria-hidden="true">◉</span> Read-only investigation
        </span>
      </header>
      <div className="workspace-grid">
        <section
          className="panel investigation"
          aria-labelledby="investigation-heading"
        >
          <PanelHeading
            number="01"
            title="Investigation"
            id="investigation-heading"
            subtitle="Passenger and current journey"
          />
          <PassengerPanel data={data} />
          <ItineraryPanel data={data} />
        </section>
        <section className="panel evidence" aria-labelledby="evidence-heading">
          <PanelHeading
            number="02"
            title="Evidence"
            id="evidence-heading"
            subtitle="Disruption, status and policy"
          />
          <EvidencePanel data={data} />
        </section>
        <section className="panel options" aria-labelledby="options-heading">
          <PanelHeading
            number="03"
            title="Options"
            id="options-heading"
            subtitle="Validated recommendation and manual exploration"
          />
          <RecommendationPanel data={data} />
          <ProposalPanel caseId={data.case_id} />
          <div className="explorer-heading">
            <h3>Manual schedule explorer</h3>
            <p>
              Candidate generation is separate from the validated
              recommendation.
            </p>
          </div>
          <form className="search-form" onSubmit={submit}>
            <div className="route-lock">
              <span>{defaults.origin}</span>
              <span aria-hidden="true">→</span>
              <span>{defaults.destination}</span>
              <small>Route and party size come from the server</small>
            </div>
            <label>
              Earliest departure
              <input
                value={earliest}
                onChange={(e) => setEarliest(e.target.value)}
                aria-describedby="timezone-note"
              />
            </label>
            <label>
              Latest arrival
              <input
                value={latest}
                onChange={(e) => setLatest(e.target.value)}
                aria-describedby="timezone-note"
              />
            </label>
            <label>
              Maximum connections
              <select
                value={connections}
                onChange={(e) =>
                  setConnections(Number(e.target.value) as 0 | 1)
                }
              >
                <option value={0}>Direct only</option>
                <option value={1}>Up to one</option>
              </select>
            </label>
            <p id="timezone-note" className="hint">
              Use an ISO 8601 timestamp with timezone, for example
              2026-01-15T11:00:00Z.
            </p>
            <button className="button" disabled={search.isPending}>
              {search.isPending ? "Searching…" : "Search alternatives"}
            </button>
          </form>
          {search.isError && <ErrorState error={search.error} />}
          {validate.isError && <ErrorState error={validate.error} />}
          {search.data && (
            <CandidateList
              candidates={search.data.candidates}
              validations={validations}
              validating={
                validate.isPending
                  ? validate.variables?.candidate_id
                  : undefined
              }
              onValidate={(candidate) =>
                validate.mutate({
                  case_id: data.case_id,
                  candidate_id: candidate.candidate_id,
                  flight_ids: candidate.segments.map((item) => item.flight_id),
                })
              }
            />
          )}
        </section>
        <aside className="panel activity" aria-labelledby="activity-heading">
          <PanelHeading
            number="04"
            title="Activity"
            id="activity-heading"
            subtitle="Durable LangGraph investigation"
          />
          <WorkflowActivity
            caseId={data.case_id}
            runId={workflowRunId}
            onRunSelected={(runId) => {
              const next = new URLSearchParams(searchParams);
              next.set("run", runId);
              setSearchParams(next, { replace: true });
            }}
          />
          <div className="manual-activity">
            <strong>Manual workspace</strong>
            <ol className="activity-list">
              <li className="done">
                <span>✓</span>
                <div>
                  <strong>Case facts loaded</strong>
                  <small>Authoritative data refreshed from FastAPI</small>
                </div>
              </li>
              <li className={search.data ? "done" : "current"}>
                <span>{search.data ? "✓" : "2"}</span>
                <div>
                  <strong>Alternative search</strong>
                  <small>
                    {search.data
                      ? `${search.data.candidates.length} candidate(s) returned`
                      : "Waiting for operator input"}
                  </small>
                </div>
              </li>
              <li className={Object.keys(validations).length ? "done" : ""}>
                <span>{Object.keys(validations).length ? "✓" : "3"}</span>
                <div>
                  <strong>Candidate validation</strong>
                  <small>Deterministic rules remain server-owned</small>
                </div>
              </li>
            </ol>
          </div>
          <div className="phase-boundary">
            <strong>Phase 10 safety boundary</strong>
            <p>
              A recommendation is read-only. A separate versioned proposal needs
              attributable approval and fresh revalidation before one synthetic
              write.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function ProposalPanel({ caseId }: { caseId: string }) {
  const [proposal, setProposal] = useState<ProposalWithAudit | null>(null);
  const create = useMutation({
    mutationFn: () => recoveryApi.createProposal(caseId),
    onSuccess: setProposal,
  });
  const decide = useMutation({
    mutationFn: (input: {
      decision: "approve" | "reject";
      reason?: string;
    }) => {
      if (!proposal) throw new Error("No proposal is loaded.");
      return recoveryApi.decideProposal(
        proposal.proposal.proposal_id,
        {
          version: proposal.proposal.version,
          itinerary_fingerprint: proposal.proposal.itinerary_fingerprint,
          reason: input.reason,
        },
        input.decision,
      );
    },
    onSuccess: setProposal,
  });
  const execute = useMutation({
    mutationFn: () => {
      if (!proposal) throw new Error("No proposal is loaded.");
      return recoveryApi.executeProposal(
        proposal.proposal.proposal_id,
        `ui-${proposal.proposal.proposal_id}-v${proposal.proposal.version}`,
      );
    },
    onSuccess: setProposal,
  });
  const error = create.error ?? decide.error ?? execute.error;

  if (!proposal)
    return (
      <section className="proposal-panel" aria-label="Recovery proposal">
        <p className="eyebrow">Proposal</p>
        <h3>Prepare a controlled recovery action</h3>
        <p>
          Copies the validated itinerary and evidence into an expiring,
          versioned proposal. This does not change the booking.
        </p>
        <button
          className="button"
          disabled={create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Preparing…" : "Prepare proposal"}
        </button>
        {error && <ErrorState error={error} />}
      </section>
    );

  const value = proposal.proposal;
  const awaiting = value.status === "awaiting_approval";
  return (
    <section
      className="proposal-panel"
      aria-live="polite"
      aria-label="Recovery proposal"
    >
      <div className="recommendation-title">
        <div>
          <p className="eyebrow">Proposal · version {value.version}</p>
          <h3>{label(value.status)}</h3>
        </div>
        <StatusBadge status={value.status} />
      </div>
      <p>
        <strong>Expires:</strong> {exactDate(value.expires_at)}
      </p>
      <p>
        Approval binds to itinerary fingerprint{" "}
        <code>{value.itinerary_fingerprint.slice(0, 12)}…</code>.
      </p>
      <RecommendationOptionCard option={value.proposed_itinerary} />
      {awaiting && (
        <div className="proposal-actions">
          <button
            className="button"
            disabled={decide.isPending}
            onClick={() => {
              if (
                window.confirm(
                  `Approve proposal version ${value.version}? This authorizes later execution only after fresh revalidation.`,
                )
              )
                decide.mutate({ decision: "approve" });
            }}
          >
            Approve exact proposal
          </button>
          <button
            className="button secondary"
            disabled={decide.isPending}
            onClick={() => {
              const reason = window.prompt(
                "Why is this proposal being rejected?",
              );
              if (reason?.trim())
                decide.mutate({ decision: "reject", reason: reason.trim() });
            }}
          >
            Reject
          </button>
        </div>
      )}
      {value.execution_eligible && (
        <button
          className="button"
          disabled={execute.isPending}
          onClick={() => {
            if (
              window.confirm(
                "Execute the approved synthetic rebooking? Safety evidence will be revalidated before the transactional write.",
              )
            )
              execute.mutate();
          }}
        >
          {execute.isPending
            ? "Revalidating and executing…"
            : "Revalidate and execute"}
        </button>
      )}
      <p>
        <strong>Pre-execution revalidation:</strong>{" "}
        {label(value.revalidation.status)}
      </p>
      {value.execution_result && (
        <div className="state-card">
          <strong>Booking change durably confirmed</strong>
          <p>
            {value.execution_result.original_flight_ids.join(" → ")} became{" "}
            {value.execution_result.replacement_flight_ids.join(" → ")}.
          </p>
        </div>
      )}
      {value.failure_reasons.length > 0 && (
        <div className="state-card state-error">
          <strong>Execution stopped safely</strong>
          <ul>
            {value.failure_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}
      <details open className="ranking-method">
        <summary>
          Immutable audit history ({proposal.audit_history.length})
        </summary>
        <ol>
          {proposal.audit_history.map((item) => (
            <li key={item.audit_id}>
              <strong>{label(item.event_type)}</strong> · {item.actor_id} ·{" "}
              {exactDate(item.occurred_at)}
            </li>
          ))}
        </ol>
      </details>
      {error && <ErrorState error={error} />}
    </section>
  );
}

function RecommendationPanel({ data }: { data: RecoveryCaseWorkspace }) {
  const result = data.recommendation;
  const rejected = result.option_results.filter(
    (option) => !option.validation.valid,
  );
  if (!result.recommended_itinerary)
    return (
      <section className="recommendation escalation" aria-live="polite">
        <p className="eyebrow">Operator escalation required</p>
        <h3>
          {result.outcome === "insufficient_evidence"
            ? "Evidence is insufficient"
            : "No safe recommendation exists"}
        </h3>
        <p>{result.escalation_reason}</p>
        <strong>
          Evidence completeness: {label(result.evidence_completeness)}
        </strong>
        {rejected.length > 0 && <RejectedOptions options={rejected} />}
      </section>
    );

  return (
    <section className="recommendation" aria-live="polite">
      <div className="recommendation-title">
        <div>
          <p className="eyebrow">Validated recommendation</p>
          <h3>Recommended itinerary</h3>
        </div>
        <StatusBadge status="passed" />
      </div>
      <RecommendationOptionCard
        option={result.recommended_itinerary}
        recommended
      />
      {result.other_validated_options.length > 0 && (
        <div className="validated-alternatives">
          <h3>Other validated options</h3>
          {result.other_validated_options.map((option) => (
            <RecommendationOptionCard key={option.option_id} option={option} />
          ))}
        </div>
      )}
      {rejected.length > 0 && <RejectedOptions options={rejected} />}
      <details className="ranking-method">
        <summary>How options were ranked</summary>
        <p>{result.ranking_method}</p>
        <p>Evidence completeness: {label(result.evidence_completeness)}</p>
      </details>
    </section>
  );
}

function RecommendationOptionCard({
  option,
  recommended = false,
}: {
  option: RecommendationOption;
  recommended?: boolean;
}) {
  return (
    <article
      className={`recommendation-option ${recommended ? "primary" : ""}`}
    >
      <header>
        <strong>
          {recommended
            ? "Recommended"
            : `Rank ${option.ranking_inputs?.rank_position}`}
        </strong>
        <code>{option.option_id}</code>
      </header>
      <ol>
        {option.segments.map((segment) => (
          <li key={segment.flight_id}>
            <strong>{segment.service}</strong>
            <span>
              {segment.origin} → {segment.destination}
            </span>
            <small>
              Arrives {exactDate(segment.operational_arrival)} ·{" "}
              {segment.available_seats} seats
            </small>
          </li>
        ))}
      </ol>
      <div className="recommendation-details">
        <div>
          <h4>Important tradeoffs</h4>
          <ul>
            {option.tradeoffs.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>Supporting evidence</h4>
          <ul>
            {option.evidence_references.map((item) => (
              <li key={item.evidence_id}>
                <code>{item.evidence_id}</code> {item.summary}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </article>
  );
}

function RejectedOptions({ options }: { options: RecommendationOption[] }) {
  return (
    <details className="rejected-options" open>
      <summary>Rejected options and reasons ({options.length})</summary>
      {options.map((option) => (
        <article key={option.option_id}>
          <code>{option.option_id}</code>
          <ul>
            {option.validation.rejection_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </article>
      ))}
    </details>
  );
}

function PanelHeading({
  number,
  title,
  id,
  subtitle,
}: {
  number: string;
  title: string;
  id: string;
  subtitle: string;
}) {
  return (
    <header className="panel-heading">
      <span>{number}</span>
      <div>
        <h2 id={id}>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </header>
  );
}

function PassengerPanel({ data }: { data: RecoveryCaseWorkspace }) {
  return (
    <div className="subpanel">
      <h3>
        Passengers <span>{data.passengers.length}</span>
      </h3>
      <ul className="passenger-list">
        {data.passengers.map((person) => (
          <li key={person.passenger_id}>
            <span className="avatar" aria-hidden="true">
              {person.display_name
                .split(" ")
                .map((part) => part[0])
                .join("")
                .slice(0, 2)}
            </span>
            <span>
              <strong>{person.display_name}</strong>
              <small>{person.passenger_id}</small>
            </span>
          </li>
        ))}
      </ul>
      <p className="privacy-note">
        Only identity needed for this investigation is shown.
      </p>
    </div>
  );
}

function ItineraryPanel({ data }: { data: RecoveryCaseWorkspace }) {
  return (
    <div className="subpanel">
      <h3>Existing itinerary</h3>
      <ol className="timeline">
        {data.itinerary.map((item) => (
          <li key={item.segment_id} className={item.affected ? "affected" : ""}>
            <div className="timeline-head">
              <strong>{item.service}</strong>
              <StatusBadge status={item.operational_status} />
            </div>
            <p className="flight-route">
              {item.origin} <span aria-hidden="true">→</span> {item.destination}
            </p>
            <dl>
              <div>
                <dt>Departs</dt>
                <dd>{exactDate(item.scheduled_departure)}</dd>
              </div>
              <div>
                <dt>Arrives</dt>
                <dd>{exactDate(item.scheduled_arrival)}</dd>
              </div>
            </dl>
            {item.affected && (
              <small className="affected-note">
                Affected segment · {item.flight_id}
              </small>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function EvidencePanel({ data }: { data: RecoveryCaseWorkspace }) {
  const d = data.disruption;
  return (
    <>
      <div className="evidence-callout">
        <span className="evidence-icon" aria-hidden="true">
          !
        </span>
        <div>
          <span className="status status-cancelled">
            {label(d.disruption_type)}
          </span>
          <h3>{d.affected_flight_id}</h3>
          <p>Recorded {exactDate(d.occurred_at)}</p>
          {d.delay_minutes && <strong>{d.delay_minutes} minute delay</strong>}
          {d.cancellation_reason && <strong>{d.cancellation_reason}</strong>}
          {d.missed_flight_id && (
            <strong>
              Connection missed: {d.arriving_flight_id} → {d.missed_flight_id}
            </strong>
          )}
        </div>
      </div>
      <div className="subpanel policy">
        <div className="policy-title">
          <span>Policy evidence</span>
          <code>{data.policy.policy_id}</code>
        </div>
        <h3>{data.policy.name}</h3>
        <p>{data.policy.summary}</p>
        <dl className="policy-facts">
          <div>
            <dt>Rebooking window</dt>
            <dd>{data.policy.rebooking_window_hours} hours</dd>
          </div>
          <div>
            <dt>Next day</dt>
            <dd>{data.policy.allows_next_day ? "Allowed" : "Not allowed"}</dd>
          </div>
          <div>
            <dt>Applies to</dt>
            <dd>{data.policy.applicable_types.map(label).join(", ")}</dd>
          </div>
        </dl>
      </div>
    </>
  );
}

function CandidateList({
  candidates,
  validations,
  validating,
  onValidate,
}: {
  candidates: AlternativeCandidate[];
  validations: Record<string, ItineraryValidation>;
  validating?: string;
  onValidate: (candidate: AlternativeCandidate) => void;
}) {
  if (!candidates.length)
    return (
      <div className="state-card">
        <strong>No scheduled alternatives found</strong>
        <p>
          Adjust the time window or connection limit. No availability was
          inferred.
        </p>
      </div>
    );
  return (
    <div className="candidate-list" aria-live="polite">
      <div className="result-heading">
        <h3>Available schedule candidates</h3>
        <span>{candidates.length} result(s)</span>
      </div>
      {candidates.map((candidate, index) => {
        const validation = validations[candidate.candidate_id];
        return (
          <article className="candidate" key={candidate.candidate_id}>
            <header>
              <div>
                <span className="candidate-rank">Option {index + 1}</span>
                <code>{candidate.candidate_id}</code>
              </div>
              {validation ? (
                <StatusBadge
                  status={validation.structurally_valid ? "passed" : "failed"}
                />
              ) : (
                <StatusBadge status="not_validated" />
              )}
            </header>
            <div className="candidate-summary">
              <strong>
                {candidate.segments[0]?.origin} →{" "}
                {candidate.segments.at(-1)?.destination}
              </strong>
              <span>
                {duration(candidate.scheduled_duration_minutes)} total
              </span>
              <span>{candidate.segments.length - 1} connection(s)</span>
            </div>
            <ol>
              {candidate.segments.map((segment) => (
                <li key={segment.flight_id}>
                  <strong>{segment.service}</strong>
                  <span>
                    {segment.origin} → {segment.destination}
                  </span>
                  <small>
                    {exactDate(segment.scheduled_departure)} —{" "}
                    {exactDate(segment.scheduled_arrival)}
                  </small>
                </li>
              ))}
            </ol>
            {candidate.connection_minutes.map((minutes, i) => (
              <p className="connection" key={i}>
                Connection {i + 1}: {minutes} minutes
              </p>
            ))}
            <div className="deferred-note">
              Seat inventory and ticket rules: not evaluated by this manual
              explorer
            </div>
            <button
              className="button secondary"
              disabled={validating === candidate.candidate_id}
              onClick={() => onValidate(candidate)}
            >
              {validating === candidate.candidate_id
                ? "Validating…"
                : validation
                  ? "Validate again"
                  : "Validate candidate"}
            </button>
            {validation && <ValidationResults result={validation} />}
          </article>
        );
      })}
    </div>
  );
}

function ValidationResults({ result }: { result: ItineraryValidation }) {
  return (
    <section
      className="validation"
      aria-label="Validation results"
      aria-live="polite"
    >
      <h4>
        {result.structurally_valid
          ? "Structural checks passed"
          : "Structural checks failed"}
      </h4>
      <ul>
        {result.rules.map((rule) => (
          <li key={rule.rule}>
            <StatusBadge status={rule.status} />
            <div>
              <strong>{label(rule.rule)}</strong>
              <p>{rule.reason}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

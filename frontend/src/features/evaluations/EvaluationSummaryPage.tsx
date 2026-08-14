import { useQuery } from "@tanstack/react-query";
import { recoveryApi } from "../../api/client";
import { ErrorState, LoadingState } from "../../components/AsyncState";

const percent = (value: number) =>
  new Intl.NumberFormat("en-GB", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);

const exactDate = (value: string) =>
  new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));

const label = (value: string) => value.replaceAll("_", " ");

export function EvaluationSummaryPage() {
  const query = useQuery({
    queryKey: ["evaluation", "phase-11"],
    queryFn: recoveryApi.getPhase11Evaluation,
  });

  return (
    <div className="page evaluation-page">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Phase 11 release evidence</p>
          <h1>Evaluation summary</h1>
          <p>
            Deterministic safety and workflow evidence from the frozen synthetic
            benchmark. Live-model quality is reported separately when available.
          </p>
        </div>
      </section>
      {query.isPending && <LoadingState label="Loading evaluation report" />}
      {query.isError && (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      )}
      {query.data && <EvaluationContent report={query.data} />}
    </div>
  );
}

function EvaluationContent({
  report,
}: {
  report: Awaited<ReturnType<typeof recoveryApi.getPhase11Evaluation>>;
}) {
  const failed = report.cases.filter((item) => !item.passed);
  return (
    <div className="evaluation-content">
      <section
        className={`evaluation-banner ${report.status}`}
        role="status"
        aria-live="polite"
      >
        <div>
          <span className="eyebrow">Deterministic benchmark</span>
          <h2>
            {report.status === "passed"
              ? "Release gates passed"
              : "Release blocked"}
          </h2>
        </div>
        <dl>
          <div>
            <dt>System</dt>
            <dd>{report.contract.system_version}</dd>
          </div>
          <div>
            <dt>Dataset</dt>
            <dd>{report.contract.dataset_version}</dd>
          </div>
          <div>
            <dt>Run</dt>
            <dd>{exactDate(report.generated_at)}</dd>
          </div>
          <div>
            <dt>Seed</dt>
            <dd>{report.contract.random_seed}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="quality-heading">
        <h2 id="quality-heading">Quality and safety</h2>
        <div className="metric-grid">
          <Metric
            title="Task completion"
            value={percent(report.totals.task_completion_rate)}
          />
          <Metric
            title="Correct outcome"
            value={percent(report.totals.outcome_accuracy)}
          />
          <Metric
            title="Approval integrity"
            value={percent(report.totals.approval_integrity_rate)}
          />
          <Metric
            title="Unapproved writes"
            value={String(report.totals.booking_writes_without_valid_approval)}
            critical
          />
          <Metric
            title="Duplicate writes"
            value={String(report.totals.duplicate_booking_writes)}
            critical
          />
          <Metric
            title="p95 harness latency"
            value={`${report.totals.latency_p95_ms.toFixed(3)} ms`}
          />
          <Metric
            title="Model calls"
            value={String(report.totals.model_calls)}
          />
          <Metric
            title="Token use / cost"
            value={
              report.totals.input_tokens === null ||
              report.totals.cost_usd === null
                ? "Not available"
                : `${report.totals.input_tokens + (report.totals.output_tokens ?? 0)} / $${report.totals.cost_usd.toFixed(4)}`
            }
          />
        </div>
      </section>

      <section aria-labelledby="slices-heading">
        <h2 id="slices-heading">Benchmark slices</h2>
        <div
          className="slice-table"
          role="region"
          aria-label="Benchmark slice results"
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th>Slice</th>
                <th>Passed</th>
                <th>Outcome</th>
                <th>Approval integrity</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.slices).map(([name, metrics]) => (
                <tr key={name}>
                  <th scope="row">{label(name)}</th>
                  <td>
                    {metrics.passed_cases}/{metrics.case_count}
                  </td>
                  <td>{percent(metrics.outcome_accuracy)}</td>
                  <td>{percent(metrics.approval_integrity_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="failed-heading">
        <h2 id="failed-heading">Failed cases</h2>
        {failed.length === 0 ? (
          <p className="no-failures">
            No failed cases in this deterministic run.
          </p>
        ) : (
          <ul className="failed-cases">
            {failed.map((item) => (
              <li key={item.case_id}>
                <strong>{item.case_id}</strong>:{" "}
                {item.safe_diagnostics.join("; ")}
              </li>
            ))}
          </ul>
        )}
      </section>

      <aside className="limitations" aria-labelledby="limitations-heading">
        <h2 id="limitations-heading">What this does not prove</h2>
        <ul>
          {report.contract.unsupported_claims.map((claim) => (
            <li key={claim}>{claim}</li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

function Metric({
  title,
  value,
  critical = false,
}: {
  title: string;
  value: string;
  critical?: boolean;
}) {
  return (
    <article className={critical ? "metric critical" : "metric"}>
      <span>{title}</span>
      <strong>{value}</strong>
    </article>
  );
}

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { recoveryApi } from "../../api/client";
import type { DisruptionType } from "../../api/models";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/AsyncState";
import { StatusBadge } from "../../components/StatusBadge";

const disruptionLabels: Record<DisruptionType, string> = {
  delayed_flight: "Delayed flight",
  cancelled_flight: "Cancelled flight",
  missed_connection: "Missed connection",
};

const exactDate = (value: string) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));

export function CaseQueuePage() {
  const query = useQuery({
    queryKey: ["recovery-cases"],
    queryFn: recoveryApi.listCases,
  });

  return (
    <div className="page page-queue">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Manual investigation</p>
          <h1>Disruption queue</h1>
          <p>
            Review server-owned facts and investigate recovery options without
            automation.
          </p>
        </div>
        <div className="queue-count" aria-live="polite">
          <strong>{query.data?.cases.length ?? "—"}</strong>
          <span>open synthetic cases</span>
        </div>
      </section>
      {query.isPending && <LoadingState label="Loading disruption queue" />}
      {query.isError && (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      )}
      {query.data?.cases.length === 0 && (
        <EmptyState title="No disruption cases">
          The server returned an empty queue. No action is needed.
        </EmptyState>
      )}
      {query.data && query.data.cases.length > 0 && (
        <section className="queue-list" aria-label="Recovery cases">
          {query.data.cases.map((item) => (
            <article className="case-card" key={item.case_id}>
              <div className="case-main">
                <div className="case-identity">
                  <span className="mono">{item.case_id}</span>
                  <StatusBadge status={item.operational_status} />
                </div>
                <h2>{item.title}</h2>
                <p className="route">
                  <strong>{item.route.origin}</strong>
                  <span aria-hidden="true">→</span>
                  <strong>{item.route.destination}</strong>
                </p>
              </div>
              <dl className="case-facts">
                <div>
                  <dt>Disruption</dt>
                  <dd>{disruptionLabels[item.disruption_type]}</dd>
                </div>
                <div>
                  <dt>Affected service</dt>
                  <dd>{item.affected_flight_id}</dd>
                </div>
                <div>
                  <dt>Party</dt>
                  <dd>
                    {item.passenger_count}{" "}
                    {item.passenger_count === 1 ? "passenger" : "passengers"}
                  </dd>
                </div>
                <div>
                  <dt>Journey starts</dt>
                  <dd>{exactDate(item.journey_departure)}</dd>
                </div>
              </dl>
              <Link
                className="button case-action"
                to={`/cases/${item.case_id}`}
              >
                Investigate case <span aria-hidden="true">→</span>
              </Link>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}

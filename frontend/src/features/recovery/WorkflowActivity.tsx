import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ApiError, recoveryApi } from "../../api/client";
import type { WorkflowEvent, WorkflowRun } from "../../api/models";
import { ErrorState } from "../../components/AsyncState";

const eventTypes = [
  "workflow.created",
  "workflow.started",
  "workflow.resumed",
  "workflow.paused",
  "workflow.cancellation_requested",
  "workflow.cancelled",
  "node.started",
  "node.completed",
  "tool.started",
  "tool.completed",
  "evidence.recorded",
  "workflow.retry_scheduled",
  "workflow.completed",
  "workflow.awaiting_information",
  "workflow.failed",
  "stream.replay_reset_required",
];

type ConnectionState = "idle" | "connecting" | "live" | "reconnecting";

const words = (value: string) => value.replaceAll("_", " ");
const terminal = (run: WorkflowRun) =>
  ["cancelled", "completed", "awaiting_information", "failed"].includes(
    run.status,
  );

export function WorkflowActivity({
  caseId,
  runId,
  onRunSelected,
}: {
  caseId: string;
  runId: string | null;
  onRunSelected: (runId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const seen = useRef(new Set<string>());
  const runQuery = useQuery({
    queryKey: ["workflow-run", runId],
    queryFn: () => recoveryApi.getWorkflow(runId ?? ""),
    enabled: Boolean(runId),
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 404) && count < 1,
  });
  const start = useMutation({
    mutationFn: () => recoveryApi.startWorkflow(caseId),
    onSuccess: (run) => {
      queryClient.setQueryData(["workflow-run", run.run_id], run);
      onRunSelected(run.run_id);
    },
  });
  const cancel = useMutation({
    mutationFn: (id: string) => recoveryApi.cancelWorkflow(id),
    onSuccess: (run) =>
      queryClient.setQueryData(["workflow-run", run.run_id], run),
  });
  const resume = useMutation({
    mutationFn: (id: string) => recoveryApi.resumeWorkflow(id),
    onSuccess: (run) =>
      queryClient.setQueryData(["workflow-run", run.run_id], run),
  });

  useEffect(() => {
    setEvents([]);
    seen.current = new Set();
  }, [runId]);

  useEffect(() => {
    const run = runQuery.data;
    if (!runId || !run || terminal(run)) {
      setConnection("idle");
      return;
    }
    setConnection("connecting");
    const source = new EventSource(
      `/api/v1/workflow-runs/${encodeURIComponent(runId)}/events?cursor=${run.last_event_sequence}`,
    );
    source.onopen = () => setConnection("live");
    source.onerror = () => setConnection("reconnecting");
    const receive = (raw: Event) => {
      const message = raw as MessageEvent<string>;
      try {
        const event = JSON.parse(message.data) as WorkflowEvent;
        if (!seen.current.has(event.event_id)) {
          seen.current.add(event.event_id);
          setEvents((current) => [...current.slice(-49), event]);
        }
        void queryClient.invalidateQueries({
          queryKey: ["workflow-run", runId],
        });
      } catch {
        setConnection("reconnecting");
      }
    };
    for (const type of eventTypes) source.addEventListener(type, receive);
    return () => {
      for (const type of eventTypes) source.removeEventListener(type, receive);
      source.close();
    };
  }, [queryClient, runId, runQuery.data]);

  if (!runId)
    return (
      <div className="workflow-empty">
        <p>
          Start a durable, read-only investigation. Progress survives refresh
          and backend restart.
        </p>
        <button
          className="button"
          disabled={start.isPending}
          onClick={() => start.mutate()}
        >
          {start.isPending ? "Starting…" : "Start investigation"}
        </button>
        {start.isError && <ErrorState error={start.error} />}
      </div>
    );

  if (runQuery.isPending)
    return <p role="status">Restoring durable workflow…</p>;
  if (runQuery.isError)
    return (
      <ErrorState error={runQuery.error} onRetry={() => runQuery.refetch()} />
    );

  const run = runQuery.data;
  const recommendationEvidence = new Set(
    run.recommendation?.option_results.flatMap((option) =>
      option.evidence_references.map((reference) => reference.evidence_id),
    ) ?? [],
  ).size;
  return (
    <div className="workflow-activity">
      <div className="workflow-status" aria-live="polite">
        <span className={`workflow-dot workflow-${run.status}`} />
        <div>
          <strong>{words(run.status)}</strong>
          <small>
            {terminal(run)
              ? `Final state · ${run.run_id}`
              : connection === "live"
                ? "Live progress connected"
                : connection === "reconnecting"
                  ? "Reconnecting; durable state retained"
                  : "Connecting to live progress"}
          </small>
        </div>
      </div>

      <ol className="activity-list durable-steps">
        {run.completed_steps.map((step, index) => (
          <li className="done" key={`${step}-${index}`}>
            <span>✓</span>
            <div>
              <strong>{words(step)}</strong>
              <small>Checkpoint persisted</small>
            </div>
          </li>
        ))}
        {run.current_node && (
          <li className="current">
            <span>•</span>
            <div>
              <strong>{words(run.current_node)}</strong>
              <small>Current safe boundary</small>
            </div>
          </li>
        )}
      </ol>

      {run.tool_activity.length > 0 && (
        <div className="workflow-section">
          <strong>Safe tool activity</strong>
          <ul>
            {run.tool_activity.map((tool) => (
              <li key={tool.observation_id}>
                {words(tool.tool_name)} · {tool.ok ? "completed" : "failed"}
                <small>{tool.observation_id}</small>
              </li>
            ))}
          </ul>
        </div>
      )}

      <dl className="workflow-metrics">
        <div>
          <dt>Model turns</dt>
          <dd>{run.current_turn}</dd>
        </div>
        <div>
          <dt>Retries</dt>
          <dd>{run.retry_count}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>{Math.max(run.evidence_ids.length, recommendationEvidence)}</dd>
        </div>
      </dl>

      {run.outcome_summary && (
        <p className="workflow-result">{run.outcome_summary}</p>
      )}
      {run.information_question && (
        <p className="workflow-result">
          Information needed: {run.information_question}
        </p>
      )}
      {run.failure_code && (
        <p className="workflow-result workflow-failure">
          {words(run.failure_code)} · {run.failure_message}
        </p>
      )}

      <div className="workflow-actions">
        {run.status === "paused" && (
          <button
            className="button"
            disabled={resume.isPending}
            onClick={() => resume.mutate(run.run_id)}
          >
            Resume investigation
          </button>
        )}
        {["created", "running", "paused"].includes(run.status) && (
          <button
            className="button button-secondary"
            disabled={cancel.isPending}
            onClick={() => cancel.mutate(run.run_id)}
          >
            Cancel investigation
          </button>
        )}
      </div>
      {(cancel.isError || resume.isError) && (
        <ErrorState error={cancel.error ?? resume.error} />
      )}
      <span className="sr-only" aria-live="polite">
        {events.at(-1)?.type ?? "No new workflow event"}
      </span>
    </div>
  );
}

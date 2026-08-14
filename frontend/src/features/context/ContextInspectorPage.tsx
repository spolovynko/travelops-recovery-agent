import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { recoveryApi } from "../../api/client";
import { ErrorState, LoadingState } from "../../components/AsyncState";

const taskNodes: Record<string, string> = {
  intake: "intake",
  investigate: "model_reasoning",
  recommend: "validated_recommendation",
  prepare_proposal: "proposal_approval",
  review_approval: "proposal_approval",
  execute_rebooking: "proposal_approval",
};

const label = (value: string) => value.replaceAll("_", " ");

export function ContextInspectorPage() {
  const [draft, setDraft] = useState({
    case_id: "CASE-0002",
    task: "investigate",
    workflow_node: "model_reasoning",
    operator_role: "recovery_operator",
    approval_status: "",
    workflow_status: "running",
  });
  const [selection, setSelection] = useState(draft);
  const query = useQuery({
    queryKey: ["context-inspector", selection],
    queryFn: () => recoveryApi.inspectContext(selection),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSelection(draft);
  };

  return (
    <div className="page context-page">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Phase 12 developer surface</p>
          <h1>Context inspector</h1>
          <p>
            Inspect exactly which safe evidence and capability schemas enter one
            workflow step. This route is unavailable in production.
          </p>
        </div>
      </section>

      <form className="context-controls" onSubmit={submit}>
        <label>
          Case
          <input
            required
            pattern="[A-Z0-9-]{3,96}"
            value={draft.case_id}
            onChange={(event) =>
              setDraft({ ...draft, case_id: event.target.value })
            }
          />
        </label>
        <label>
          Task
          <select
            value={draft.task}
            onChange={(event) => {
              const task = event.target.value;
              setDraft({ ...draft, task, workflow_node: taskNodes[task] });
            }}
          >
            {Object.keys(taskNodes).map((task) => (
              <option value={task} key={task}>
                {label(task)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Workflow node
          <input
            value={draft.workflow_node}
            onChange={(event) =>
              setDraft({ ...draft, workflow_node: event.target.value })
            }
          />
        </label>
        <label>
          Operator role
          <select
            value={draft.operator_role}
            onChange={(event) =>
              setDraft({ ...draft, operator_role: event.target.value })
            }
          >
            <option value="recovery_operator">recovery operator</option>
            <option value="proposal_preparer">proposal preparer</option>
            <option value="viewer">viewer</option>
          </select>
        </label>
        <label>
          Approval
          <select
            value={draft.approval_status}
            onChange={(event) =>
              setDraft({ ...draft, approval_status: event.target.value })
            }
          >
            <option value="">not applicable</option>
            <option value="pending">pending</option>
            <option value="approved">approved</option>
            <option value="rejected">rejected</option>
          </select>
        </label>
        <button className="button primary" type="submit">
          Inspect context
        </button>
      </form>

      {query.isPending && <LoadingState label="Building governed context" />}
      {query.isError && (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      )}
      {query.data && <ContextResult report={query.data} />}
    </div>
  );
}

function ContextResult({
  report,
}: {
  report: Awaited<ReturnType<typeof recoveryApi.inspectContext>>;
}) {
  const exposed = report.tools.filter((tool) => tool.exposed);
  const denied = report.tools.filter((tool) => !tool.exposed);
  return (
    <div className="context-results">
      <section
        className={`context-banner ${report.status}`}
        role="status"
        aria-live="polite"
      >
        <div>
          <span className="eyebrow">{report.build_id}</span>
          <h2>
            {report.status === "ready" ? "Context ready" : "Stopped safely"}
          </h2>
          {report.escalation_reason && <p>{report.escalation_reason}</p>}
        </div>
        <dl>
          <div>
            <dt>Schema / policy</dt>
            <dd>
              {report.schema_version} / {report.policy_version}
            </dd>
          </div>
          <div>
            <dt>Cache</dt>
            <dd>{report.cache.hit ? "hit" : "miss"}</dd>
          </div>
          <div>
            <dt>Selection latency</dt>
            <dd>{report.selection_latency_ms.toFixed(3)} ms</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="budget-heading">
        <h2 id="budget-heading">Context budget</h2>
        <div className="metric-grid">
          <ContextMetric
            title="Total budget"
            value={`${report.token_accounting.budget} est. tokens`}
          />
          <ContextMetric
            title="Selected evidence"
            value={`${report.token_accounting.selected_estimate} est. tokens`}
          />
          <ContextMetric
            title="Tool schemas"
            value={`${report.token_accounting.tool_schema_estimate} est. tokens`}
          />
          <ContextMetric
            title="Remaining"
            value={`${report.token_accounting.remaining_estimate} est. tokens`}
          />
          <ContextMetric
            title="Mandatory coverage"
            value={`${Math.round(report.mandatory_evidence_coverage * 100)}%`}
          />
          <ContextMetric
            title="Excluded / compacted"
            value={`${report.excluded_count} / ${report.compacted_count}`}
          />
        </div>
        <p className="context-note">
          Estimates use {report.token_accounting.estimate_method}; they are not
          provider-exact.
        </p>
      </section>

      <section aria-labelledby="evidence-heading">
        <h2 id="evidence-heading">Evidence decisions</h2>
        <div
          className="context-table"
          role="region"
          aria-label="Context evidence inclusion and exclusion reasons"
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th>Evidence</th>
                <th>Decision</th>
                <th>Reason</th>
                <th>Mandatory</th>
                <th>Estimate</th>
              </tr>
            </thead>
            <tbody>
              {report.decisions.map((decision) => (
                <tr key={`${decision.evidence_id}-${decision.disposition}`}>
                  <th scope="row">{decision.evidence_id}</th>
                  <td>{decision.disposition}</td>
                  <td>
                    {label(decision.reason)}
                    <small>{decision.detail}</small>
                  </td>
                  <td>{decision.mandatory ? "yes" : "no"}</td>
                  <td>{decision.token_estimate}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="selected-heading">
        <h2 id="selected-heading">Selected evidence</h2>
        {report.selected.length === 0 ? (
          <p className="empty-context">
            No evidence was sent. Resolve the escalation reason and rebuild.
          </p>
        ) : (
          <div className="selected-evidence">
            {report.selected.map((item) => (
              <article key={item.evidence_id}>
                <header>
                  <strong>{item.evidence_id}</strong>
                  <span>
                    {item.freshness} · authority {item.authority}
                  </span>
                </header>
                <p>{item.content}</p>
                <small>
                  {item.selected_token_estimate} estimated tokens
                  {item.compacted ? " · derived compacted view" : ""}
                </small>
              </article>
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="tools-heading">
        <h2 id="tools-heading">Governed tool exposure</h2>
        <div className="tool-governance-grid">
          <div>
            <h3>Exposed ({exposed.length})</h3>
            {exposed.length === 0 ? (
              <p>No tools are available for this role and step.</p>
            ) : (
              <ToolList tools={exposed} />
            )}
          </div>
          <div>
            <h3>Denied ({denied.length})</h3>
            <ToolList tools={denied} />
          </div>
        </div>
      </section>
    </div>
  );
}

function ToolList({
  tools,
}: {
  tools: Awaited<ReturnType<typeof recoveryApi.inspectContext>>["tools"];
}) {
  return (
    <ul className="tool-list">
      {tools.map((tool) => (
        <li key={tool.name}>
          <strong>{tool.name}</strong>
          <span>{label(tool.reason)}</span>
        </li>
      ))}
    </ul>
  );
}

function ContextMetric({ title, value }: { title: string; value: string }) {
  return (
    <article className="metric">
      <span>{title}</span>
      <strong>{value}</strong>
    </article>
  );
}

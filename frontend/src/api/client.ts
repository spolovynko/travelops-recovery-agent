import type {
  AlternativeSearchResult,
  ApiErrorPayload,
  EvaluationReport,
  ContextInspectorReport,
  Phase12EvaluationReport,
  ItineraryValidation,
  RecoveryCaseQueue,
  RecoveryCaseWorkspace,
  RecommendationResult,
  ProposalWithAudit,
  WorkflowRun,
} from "./models";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;

  constructor(
    message: string,
    status: number,
    code = "unexpected_error",
    retryable = false,
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(
      "The recovery service could not be reached.",
      0,
      "network_error",
      true,
    );
  }

  if (!response.ok) {
    const payload = (await response
      .json()
      .catch(() => ({}))) as ApiErrorPayload;
    throw new ApiError(
      payload.error?.message ??
        "The recovery service returned an unexpected response.",
      response.status,
      payload.error?.code,
      payload.error?.retryable,
    );
  }
  return (await response.json()) as T;
}

export const recoveryApi = {
  getPhase11Evaluation: () =>
    request<EvaluationReport>("/api/v1/evaluations/phase-11"),
  getPhase12Evaluation: () =>
    request<Phase12EvaluationReport>("/api/v1/evaluations/phase-12"),
  inspectContext: (input: {
    case_id: string;
    task: string;
    workflow_node: string;
    operator_role: string;
    approval_status?: string;
    workflow_status?: string;
  }) => {
    const query = new URLSearchParams(
      Object.entries(input).filter((entry): entry is [string, string] =>
        Boolean(entry[1]),
      ),
    );
    return request<ContextInspectorReport>(
      `/api/v1/developer/context-inspector?${query.toString()}`,
    );
  },
  listCases: () => request<RecoveryCaseQueue>("/api/v1/recovery-cases"),
  getCase: (caseId: string) =>
    request<RecoveryCaseWorkspace>(
      `/api/v1/recovery-cases/${encodeURIComponent(caseId)}`,
    ),
  getRecommendation: (caseId: string) =>
    request<RecommendationResult>(
      `/api/v1/recovery-cases/${encodeURIComponent(caseId)}/recommendation`,
    ),
  createProposal: (caseId: string) =>
    request<ProposalWithAudit>(
      `/api/v1/recovery-cases/${encodeURIComponent(caseId)}/proposal`,
      {
        method: "POST",
        headers: { "X-Actor-ID": "proposal-preparer" },
        body: JSON.stringify({ workflow_run_id: null }),
      },
    ),
  getProposal: (proposalId: string) =>
    request<ProposalWithAudit>(
      `/api/v1/proposals/${encodeURIComponent(proposalId)}`,
      { headers: { "X-Actor-ID": "recovery-operator" } },
    ),
  decideProposal: (
    proposalId: string,
    input: { version: number; itinerary_fingerprint: string; reason?: string },
    decision: "approve" | "reject",
  ) =>
    request<ProposalWithAudit>(
      `/api/v1/proposals/${encodeURIComponent(proposalId)}/${decision}`,
      {
        method: "POST",
        headers: {
          "X-Actor-ID": "recovery-operator",
          "X-Actor-Role": "recovery_operator",
        },
        body: JSON.stringify(input),
      },
    ),
  executeProposal: (proposalId: string, idempotencyKey: string) =>
    request<ProposalWithAudit>(
      `/api/v1/proposals/${encodeURIComponent(proposalId)}/execute`,
      {
        method: "POST",
        headers: {
          "X-Actor-ID": "recovery-operator",
          "X-Actor-Role": "recovery_operator",
        },
        body: JSON.stringify({ idempotency_key: idempotencyKey }),
      },
    ),
  search: (input: {
    case_id: string;
    earliest_departure: string;
    latest_arrival: string;
    max_connections: 0 | 1;
  }) =>
    request<AlternativeSearchResult>("/api/v1/alternative-itineraries/search", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  validate: (input: {
    case_id: string;
    candidate_id: string;
    flight_ids: string[];
  }) =>
    request<ItineraryValidation>("/api/v1/itineraries/validate", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  startWorkflow: (caseId: string) =>
    request<WorkflowRun>(
      `/api/v1/recovery-cases/${encodeURIComponent(caseId)}/workflow-runs`,
      { method: "POST" },
    ),
  getWorkflow: (runId: string) =>
    request<WorkflowRun>(`/api/v1/workflow-runs/${encodeURIComponent(runId)}`),
  cancelWorkflow: (runId: string) =>
    request<WorkflowRun>(
      `/api/v1/workflow-runs/${encodeURIComponent(runId)}/cancel`,
      { method: "POST" },
    ),
  resumeWorkflow: (runId: string) =>
    request<WorkflowRun>(
      `/api/v1/workflow-runs/${encodeURIComponent(runId)}/resume`,
      { method: "POST" },
    ),
};

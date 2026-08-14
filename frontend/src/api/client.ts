import type {
  AlternativeSearchResult,
  ApiErrorPayload,
  ItineraryValidation,
  RecoveryCaseQueue,
  RecoveryCaseWorkspace,
  RecommendationResult,
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
  listCases: () => request<RecoveryCaseQueue>("/api/v1/recovery-cases"),
  getCase: (caseId: string) =>
    request<RecoveryCaseWorkspace>(
      `/api/v1/recovery-cases/${encodeURIComponent(caseId)}`,
    ),
  getRecommendation: (caseId: string) =>
    request<RecommendationResult>(
      `/api/v1/recovery-cases/${encodeURIComponent(caseId)}/recommendation`,
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

export type OperationalStatus = "scheduled" | "delayed" | "cancelled";
export type DisruptionType =
  "delayed_flight" | "cancelled_flight" | "missed_connection";

export interface RecoveryCaseQueueItem {
  case_id: string;
  title: string;
  booking_id: string;
  route: { origin: string; destination: string };
  passenger_count: number;
  disruption_type: DisruptionType;
  affected_flight_id: string;
  occurred_at: string;
  operational_status: OperationalStatus;
  delay_minutes: number | null;
  cancellation_reason: string | null;
  journey_departure: string;
  journey_arrival: string;
}

export interface RecoveryCaseQueue {
  cases: RecoveryCaseQueueItem[];
}

export interface Passenger {
  passenger_id: string;
  display_name: string;
}

export interface ItinerarySegment {
  segment_id: string;
  sequence: number;
  flight_id: string;
  service: string;
  origin: string;
  destination: string;
  scheduled_departure: string;
  scheduled_arrival: string;
  operational_status: OperationalStatus;
  delay_minutes: number | null;
  cancellation_reason: string | null;
  affected: boolean;
}

export interface DisruptionEvidence {
  disruption_id: string;
  disruption_type: DisruptionType;
  affected_flight_id: string;
  affected_segment_id: string;
  occurred_at: string;
  delay_minutes: number | null;
  cancellation_reason: string | null;
  arriving_flight_id: string | null;
  missed_flight_id: string | null;
}

export interface PolicyEvidence {
  policy_id: string;
  name: string;
  summary: string;
  applicable_types: DisruptionType[];
  rebooking_window_hours: number;
  allows_next_day: boolean;
}

export interface SearchDefaults {
  origin: string;
  destination: string;
  earliest_departure: string;
  latest_arrival: string;
  passenger_count: number;
  max_connections: 0 | 1;
}

export interface RecoveryCaseWorkspace {
  case_id: string;
  title: string;
  booking_id: string;
  passengers: Passenger[];
  itinerary: ItinerarySegment[];
  disruption: DisruptionEvidence;
  policy: PolicyEvidence;
  search_defaults: SearchDefaults;
  recommendation: RecommendationResult;
}

export type RecommendationOutcome =
  "recommended" | "no_safe_option" | "insufficient_evidence";
export type EvidenceCompleteness = "complete" | "partial" | "insufficient";
export type RecommendationValidationStatus =
  "passed" | "failed" | "missing_evidence" | "not_evaluated";

export interface RecommendationEvidence {
  evidence_id: string;
  kind: string;
  source: string;
  summary: string;
  observed_at: string | null;
}

export interface RecommendationSegment {
  flight_id: string;
  service: string;
  origin: string;
  destination: string;
  scheduled_departure: string;
  scheduled_arrival: string;
  operational_departure: string;
  operational_arrival: string;
  status: string;
  available_seats: number | null;
}

export interface RecommendationCheck {
  rule: string;
  status: RecommendationValidationStatus;
  summary: string;
  evidence_ids: string[];
}

export interface RecommendationOption {
  option_id: string;
  segments: RecommendationSegment[];
  validation: {
    valid: boolean;
    evidence_complete: boolean;
    checks: RecommendationCheck[];
    rejection_reasons: string[];
  };
  evidence_references: RecommendationEvidence[];
  ranking_inputs: {
    arrival_time: string;
    connection_count: number;
    total_wait_minutes: number;
    minimum_available_seats: number;
    passenger_count: number;
    seat_surplus: number;
    policy_compatible: boolean;
    ticket_compatible: boolean;
    rank_position: number | null;
  } | null;
  tradeoffs: string[];
}

export interface RecommendationResult {
  case_id: string;
  outcome: RecommendationOutcome;
  recommended_itinerary: RecommendationOption | null;
  other_validated_options: RecommendationOption[];
  option_results: RecommendationOption[];
  evidence_references: RecommendationEvidence[];
  evidence_completeness: EvidenceCompleteness;
  escalation_reason: string | null;
  ranking_method: string;
}

export type ProposalStatus =
  | "drafted"
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "expired"
  | "revalidation_failed"
  | "executing"
  | "executed"
  | "execution_failed";

export interface ProposalWithAudit {
  proposal: {
    proposal_id: string;
    version: number;
    case_id: string;
    booking_id: string;
    recommendation_reference: string;
    validation_reference: string;
    proposed_itinerary: RecommendationOption;
    itinerary_fingerprint: string;
    evidence_snapshot: RecommendationEvidence[];
    evidence_completeness: EvidenceCompleteness;
    evidence_fingerprint: string;
    created_at: string;
    expires_at: string;
    created_by: string;
    status: ProposalStatus;
    required_approver: {
      required_role: string;
      self_approval_prohibited: boolean;
    };
    decision: {
      decision: "approved" | "rejected";
      actor_id: string;
      actor_role: string;
      proposal_version: number;
      itinerary_fingerprint: string;
      decided_at: string;
      reason: string | null;
    } | null;
    execution_eligible: boolean;
    revalidation: {
      status: "not_run" | "passed" | "failed";
      checked_at: string | null;
      checks: string[];
      failure_reasons: string[];
    };
    execution_result: {
      status: "succeeded" | "failed";
      execution_id: string;
      idempotency_key_hash: string;
      booking_id: string;
      executed_at: string;
      original_flight_ids: string[];
      replacement_flight_ids: string[];
      provider: string;
    } | null;
    failure_reasons: string[];
    escalation_reasons: string[];
    workflow_run_id: string | null;
    correlation_id: string;
  };
  audit_history: {
    audit_id: string;
    sequence: number;
    proposal_id: string;
    event_type: string;
    actor_id: string;
    occurred_at: string;
    correlation_id: string;
    details: Record<string, unknown>;
  }[];
}

export interface CandidateSegment {
  flight_id: string;
  service: string;
  origin: string;
  destination: string;
  scheduled_departure: string;
  scheduled_arrival: string;
}

export interface AlternativeCandidate {
  candidate_id: string;
  segments: CandidateSegment[];
  connection_minutes: number[];
  scheduled_duration_minutes: number;
  validation_status: "not_validated";
}

export interface AlternativeSearchResult {
  case_id: string;
  route: { origin: string; destination: string };
  passenger_count: number;
  candidates: AlternativeCandidate[];
  inventory_status: "not_evaluated";
  deferred_validations: ("seat_inventory" | "ticket_rules")[];
}

export type ValidationStatus =
  "passed" | "failed" | "not_evaluated" | "deferred";

export interface ValidationRule {
  rule: string;
  status: ValidationStatus;
  reason: string;
}

export interface ItineraryValidation {
  case_id: string;
  candidate_id: string;
  flight_ids: string[];
  structurally_valid: boolean;
  rules: ValidationRule[];
}

export interface ApiErrorPayload {
  error?: { code?: string; message?: string; retryable?: boolean };
  detail?: unknown;
}

export type WorkflowStatus =
  | "created"
  | "running"
  | "paused"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "awaiting_information"
  | "failed";

export type WorkflowNode =
  | "validated_recommendation"
  | "proposal_approval"
  | "intake"
  | "model_reasoning"
  | "decision_validation"
  | "tool_execution"
  | "outcome_handling"
  | "information_or_escalation"
  | "completion"
  | "safe_failure";

export interface WorkflowToolActivity {
  observation_id: string;
  tool_name: string;
  ok: boolean;
}

export interface WorkflowRun {
  run_id: string;
  thread_id: string;
  case_id: string;
  status: WorkflowStatus;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested: boolean;
  current_node: WorkflowNode | null;
  completed_steps: WorkflowNode[];
  current_turn: number;
  retry_count: number;
  tool_activity: WorkflowToolActivity[];
  evidence_ids: string[];
  outcome_summary: string | null;
  information_question: string | null;
  missing_fields: string[];
  failure_code: string | null;
  failure_message: string | null;
  last_event_sequence: number;
  recommendation: RecommendationResult | null;
  proposal_id?: string | null;
  proposal_status?: ProposalStatus | null;
  proposal_execution_result?: Record<string, unknown> | null;
}

export interface WorkflowEvent {
  event_id: string;
  run_id: string;
  sequence: number;
  type: string;
  occurred_at: string;
  payload: Record<string, unknown>;
}

export const queuePayload = {
  cases: [
    {
      case_id: "CASE-0001",
      title: "Short delay on originating flight",
      booking_id: "BKG-0001",
      route: { origin: "ZRA", destination: "XLC" },
      passenger_count: 1,
      disruption_type: "delayed_flight",
      affected_flight_id: "FLT-NV101",
      occurred_at: "2026-01-15T11:00:00Z",
      operational_status: "delayed",
      delay_minutes: 30,
      cancellation_reason: null,
      journey_departure: "2026-01-15T12:00:00Z",
      journey_arrival: "2026-01-15T17:30:00Z",
    },
  ],
};

const recommendationEvidence = [
  {
    evidence_id: "availability:FLT-NV1003",
    kind: "seat_availability",
    source: "synthetic-dataset:availability-v1",
    summary: "6 seats are available on FLT-NV1003.",
    observed_at: "2026-01-15T08:00:42Z",
  },
  {
    evidence_id: "ticket-rule:BKG-0001",
    kind: "ticket_rule",
    source: "synthetic-dataset:ticket-rules-v1",
    summary: "Rebooking is allowed on carrier NV with one connection.",
    observed_at: "2026-01-15T08:00:42Z",
  },
];

const recommendedOption = {
  option_id: "REC-FLT-NV1003",
  segments: [
    {
      flight_id: "FLT-NV1003",
      service: "NV1003",
      origin: "ZRA",
      destination: "XLC",
      scheduled_departure: "2026-01-15T17:00:00Z",
      scheduled_arrival: "2026-01-15T19:30:00Z",
      operational_departure: "2026-01-15T17:00:00Z",
      operational_arrival: "2026-01-15T19:30:00Z",
      status: "scheduled",
      available_seats: 6,
    },
  ],
  validation: {
    valid: true,
    evidence_complete: true,
    checks: [
      {
        rule: "group_seat_availability",
        status: "passed",
        summary: "The complete group has seats.",
        evidence_ids: ["availability:FLT-NV1003"],
      },
    ],
    rejection_reasons: [],
  },
  evidence_references: recommendationEvidence,
  ranking_inputs: {
    arrival_time: "2026-01-15T19:30:00Z",
    connection_count: 0,
    total_wait_minutes: 0,
    minimum_available_seats: 6,
    passenger_count: 1,
    seat_surplus: 5,
    policy_compatible: true,
    ticket_compatible: true,
    rank_position: 1,
  },
  tradeoffs: [
    "Arrives at 2026-01-15T19:30:00Z.",
    "Uses 0 connections.",
    "Leaves a seat surplus of 5.",
  ],
};

export const recommendationPayload = {
  case_id: "CASE-0001",
  outcome: "recommended",
  recommended_itinerary: recommendedOption,
  other_validated_options: [],
  option_results: [
    recommendedOption,
    {
      ...recommendedOption,
      option_id: "REC-FLT-NV101-FLT-NV102",
      validation: {
        valid: false,
        evidence_complete: true,
        checks: [
          {
            rule: "stored_flight_status",
            status: "failed",
            summary: "Cancelled flights cannot be recommended: FLT-NV101",
            evidence_ids: ["status:FLT-NV101"],
          },
        ],
        rejection_reasons: [
          "Cancelled flights cannot be recommended: FLT-NV101",
        ],
      },
      ranking_inputs: null,
      tradeoffs: [],
    },
  ],
  evidence_references: recommendationEvidence,
  evidence_completeness: "complete",
  escalation_reason: null,
  ranking_method:
    "lexicographic: earliest arrival, connections, waiting, seats, option id",
};

export const workspacePayload = {
  case_id: "CASE-0001",
  title: "Short delay on originating flight",
  booking_id: "BKG-0001",
  passengers: [{ passenger_id: "PAX-0001", display_name: "Mina Vale" }],
  itinerary: [
    {
      segment_id: "SEG-0011",
      sequence: 1,
      flight_id: "FLT-NV101",
      service: "NV 101",
      origin: "ZRA",
      destination: "QVB",
      scheduled_departure: "2026-01-15T12:00:00Z",
      scheduled_arrival: "2026-01-15T14:00:00Z",
      operational_status: "delayed",
      delay_minutes: 30,
      cancellation_reason: null,
      affected: true,
    },
    {
      segment_id: "SEG-0012",
      sequence: 2,
      flight_id: "FLT-NV102",
      service: "NV 102",
      origin: "QVB",
      destination: "XLC",
      scheduled_departure: "2026-01-15T15:30:00Z",
      scheduled_arrival: "2026-01-15T17:30:00Z",
      operational_status: "scheduled",
      delay_minutes: null,
      cancellation_reason: null,
      affected: false,
    },
  ],
  disruption: {
    disruption_id: "DIS-0001",
    disruption_type: "delayed_flight",
    affected_flight_id: "FLT-NV101",
    affected_segment_id: "SEG-0011",
    occurred_at: "2026-01-15T11:00:00Z",
    delay_minutes: 30,
    cancellation_reason: null,
    arriving_flight_id: null,
    missed_flight_id: null,
  },
  policy: {
    policy_id: "POL-STANDARD",
    name: "Synthetic standard recovery",
    summary: "Permit recovery after supported fictional disruptions.",
    applicable_types: [
      "delayed_flight",
      "cancelled_flight",
      "missed_connection",
    ],
    rebooking_window_hours: 24,
    allows_next_day: true,
  },
  search_defaults: {
    origin: "ZRA",
    destination: "XLC",
    earliest_departure: "2026-01-15T11:00:00Z",
    latest_arrival: "2026-01-16T11:00:00Z",
    passenger_count: 1,
    max_connections: 1,
  },
  recommendation: recommendationPayload,
};

export const searchPayload = {
  case_id: "CASE-0001",
  route: { origin: "ZRA", destination: "XLC" },
  passenger_count: 1,
  candidates: [
    {
      candidate_id: "CAND-FLT-NV101-FLT-NV102",
      segments: [
        {
          flight_id: "FLT-NV101",
          service: "NV 101",
          origin: "ZRA",
          destination: "QVB",
          scheduled_departure: "2026-01-15T12:00:00Z",
          scheduled_arrival: "2026-01-15T14:00:00Z",
        },
        {
          flight_id: "FLT-NV102",
          service: "NV 102",
          origin: "QVB",
          destination: "XLC",
          scheduled_departure: "2026-01-15T15:30:00Z",
          scheduled_arrival: "2026-01-15T17:30:00Z",
        },
      ],
      connection_minutes: [90],
      scheduled_duration_minutes: 330,
      validation_status: "not_validated",
    },
  ],
  inventory_status: "not_evaluated",
  deferred_validations: ["seat_inventory", "ticket_rules"],
};

export const validationPayload = {
  case_id: "CASE-0001",
  candidate_id: "CAND-FLT-NV101-FLT-NV102",
  flight_ids: ["FLT-NV101", "FLT-NV102"],
  structurally_valid: true,
  rules: [
    {
      rule: "flights_exist",
      status: "passed",
      reason: "Every requested flight exists.",
    },
    {
      rule: "route_continuity",
      status: "failed",
      reason: "Example failed rule remains explicit.",
    },
    {
      rule: "chronological_order",
      status: "not_evaluated",
      reason: "Example unavailable dependency.",
    },
    {
      rule: "seat_inventory",
      status: "deferred",
      reason: "Seat inventory is not present.",
    },
  ],
};

export const workflowPayload = {
  run_id: "run-0123456789abcdef",
  thread_id: "thread-0123456789abcdef",
  case_id: "CASE-0001",
  status: "completed",
  created_at: "2026-08-13T19:00:00Z",
  updated_at: "2026-08-13T19:00:05Z",
  started_at: "2026-08-13T19:00:00Z",
  finished_at: "2026-08-13T19:00:05Z",
  cancel_requested: false,
  current_node: null,
  completed_steps: [
    "intake",
    "model_reasoning",
    "decision_validation",
    "tool_execution",
    "outcome_handling",
    "model_reasoning",
    "decision_validation",
    "outcome_handling",
    "completion",
  ],
  current_turn: 2,
  retry_count: 0,
  tool_activity: [
    {
      observation_id: "observation-1",
      tool_name: "get_booking",
      ok: true,
    },
  ],
  evidence_ids: ["observation-1"],
  outcome_summary: "The read-only investigation is complete.",
  information_question: null,
  missing_fields: [],
  failure_code: null,
  failure_message: null,
  last_event_sequence: 26,
  recommendation: null,
} as const;

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

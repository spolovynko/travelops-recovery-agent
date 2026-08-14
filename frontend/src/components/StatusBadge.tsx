import type {
  OperationalStatus,
  ProposalStatus,
  ValidationStatus,
} from "../api/models";

const symbols: Record<string, string> = {
  scheduled: "●",
  delayed: "▲",
  cancelled: "■",
  passed: "✓",
  failed: "×",
  not_evaluated: "—",
  deferred: "◷",
  not_validated: "○",
};

export function StatusBadge({
  status,
}: {
  status:
    OperationalStatus | ValidationStatus | ProposalStatus | "not_validated";
}) {
  const label = status.replaceAll("_", " ");
  return (
    <span className={`status status-${status}`}>
      <span aria-hidden="true">{symbols[status]}</span>
      {label}
    </span>
  );
}

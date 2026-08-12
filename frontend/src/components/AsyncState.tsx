import type { ReactNode } from "react";
import { ApiError } from "../api/client";

export function LoadingState({
  label = "Loading recovery data",
}: {
  label?: string;
}) {
  return (
    <div className="state-card" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}…
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const apiError = error instanceof ApiError ? error : undefined;
  return (
    <section className="state-card state-error" role="alert">
      <strong>Recovery data unavailable</strong>
      <p>
        {apiError?.message ??
          "An unexpected problem prevented this view from loading."}
      </p>
      {apiError && (
        <details>
          <summary>Technical detail</summary>
          <code>
            {apiError.code} · HTTP {apiError.status || "network"}
          </code>
        </details>
      )}
      {onRetry && (
        <button className="button secondary" type="button" onClick={onRetry}>
          Try again
        </button>
      )}
    </section>
  );
}

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="state-card">
      <strong>{title}</strong>
      <p>{children}</p>
    </section>
  );
}

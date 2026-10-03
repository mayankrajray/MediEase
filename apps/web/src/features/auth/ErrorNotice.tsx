"use client";

import type { Ref } from "react";

import { describeError, isRetryable } from "./messages";

/**
 * A failed call, in words a clinic can act on: the API's own message and
 * "Ref: <request_id>" to quote when reporting it (apps/web/CLAUDE.md). State is
 * text, not colour alone. `role="alert"` makes screen readers announce it the
 * moment it appears; `tabIndex={-1}` lets us move focus to it.
 */
export function ErrorNotice({
  error,
  onRetry,
  message: override,
  id,
  ref,
}: {
  error: unknown;
  onRetry?: () => void;
  /** Replaces the API's message (e.g. a lock, where we can say how long to wait). */
  message?: string;
  id?: string;
  ref?: Ref<HTMLDivElement>;
}) {
  const described = describeError(error);
  const message = override ?? described.message;
  const { requestId } = described;
  return (
    <div
      id={id}
      ref={ref}
      role="alert"
      tabIndex={-1}
      className="rounded border border-red-700 bg-red-50 p-4 text-red-950"
    >
      <p className="font-medium">{message}</p>
      {requestId !== "" && (
        <p className="mt-1 text-sm">
          Ref: <code className="font-mono">{requestId}</code>
        </p>
      )}
      {onRetry !== undefined && isRetryable(error) && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded border border-red-900 bg-white px-3 py-1.5 font-medium text-red-950 hover:bg-red-100"
        >
          Try again
        </button>
      )}
    </div>
  );
}

"use client";

import { CircleAlert } from "lucide-react";
import type { Ref } from "react";

import { describeError, isRetryable } from "./messages";

/**
 * A failed call, in words a clinic can act on: the API's own message and
 * "Ref: <request_id>" to quote when reporting it (apps/web/CLAUDE.md). State is
 * text, not colour alone. `role="alert"` makes screen readers announce it the
 * moment it appears; `tabIndex={-1}` lets us move focus to it. M7c-P7: the design
 * system's error tone (DESIGN.md §1), with a decorative icon.
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
      className="flex gap-3 rounded-xl border border-danger-line bg-danger-soft p-4 text-red-950"
    >
      <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-danger" />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{message}</p>
        {requestId !== "" && (
          <p className="mt-1 text-sm text-red-900">
            Ref: <code className="font-mono">{requestId}</code>
          </p>
        )}
        {onRetry !== undefined && isRetryable(error) && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex min-h-8 items-center rounded-lg border border-red-800 bg-white px-3 py-1 text-sm font-semibold text-red-950 transition-colors duration-200 ease-brand hover:bg-red-50 motion-reduce:transition-none"
          >
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

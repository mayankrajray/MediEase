/**
 * What the status page reports, derived from the API's /health (liveness) and
 * /ready (database). Both calls share one request ID, so the single
 * "Ref" shown to the user finds both lines in the API log (NFR-12).
 */

import { ApiError, apiGet, newRequestId } from "@/lib/api/client";

export type PlatformStatus =
  | { readonly state: "healthy"; readonly requestId: string }
  | {
      /** The API answered but is not ready (e.g. READY_DB_UNAVAILABLE). */
      readonly state: "degraded";
      readonly requestId: string;
      readonly code: string;
      readonly message: string;
    }
  | {
      /** The API did not answer at all. */
      readonly state: "down";
      readonly requestId: string;
      readonly code: string;
      readonly message: string;
    };

export async function getPlatformStatus(fetchImpl?: typeof fetch): Promise<PlatformStatus> {
  const requestId = newRequestId();
  const options = { requestId, ...(fetchImpl ? { fetchImpl } : {}) };

  try {
    await apiGet("/health", options);
  } catch (error) {
    return failure("down", error, requestId);
  }

  try {
    const ready = await apiGet("/ready", options);
    return { state: "healthy", requestId: ready.requestId };
  } catch (error) {
    // Status 0 means /ready got no answer: the API went away between the two calls.
    const answered = error instanceof ApiError && error.status > 0;
    return failure(answered ? "degraded" : "down", error, requestId);
  }
}

function failure(
  state: "degraded" | "down",
  error: unknown,
  requestId: string,
): Extract<PlatformStatus, { state: "degraded" | "down" }> {
  if (!(error instanceof ApiError)) {
    // Not an API failure (e.g. missing configuration): let the error page handle it.
    throw error;
  }
  return { state, requestId: error.requestId || requestId, code: error.code, message: error.message };
}

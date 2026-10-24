"use client";

/**
 * The owner's audit log (M6a-P8, FR-AUD-03). Every call names the active clinic when the person
 * has several and refreshes an expired session once. Owners only (AUDIT_VIEW); the API refuses
 * everyone else.
 */

import { useMemo } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import { ApiError, CLINIC_HEADER, REQUEST_ID_HEADER, newRequestId, type RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionGet, withSessionRefresh } from "@/lib/auth/refresh";

export type AuditPage = components["schemas"]["AuditPage"];
export type AuditEntry = components["schemas"]["AuditEntry"];
export type AuditCategory = components["schemas"]["AuditCategory"];

export interface AuditQuery {
  readonly from?: string;
  readonly to?: string;
  readonly category?: AuditCategory;
  readonly cursor?: string;
}

export interface AuditFile {
  readonly blob: Blob;
  readonly filename: string;
}

export interface AuditApi {
  readonly list: (query: AuditQuery) => Promise<AuditPage>;
  readonly exportCsv: (from: string | undefined, to: string | undefined) => Promise<AuditFile>;
}

const EXPORT_TIMEOUT_MS = 60_000;

/** The CSV as a blob, fetched so the request can name the clinic (as the prescription PDF is). */
export async function fetchAuditCsv(
  query: { from?: string; to?: string },
  clinicId: string | undefined,
  fetchImpl: typeof fetch = fetch,
): Promise<AuditFile> {
  return withSessionRefresh(async () => {
    const requestId = newRequestId();
    const headers: Record<string, string> = { Accept: "text/csv, application/json", [REQUEST_ID_HEADER]: requestId };
    if (clinicId !== undefined) headers[CLINIC_HEADER] = clinicId;
    const params = new URLSearchParams();
    if (query.from !== undefined) params.set("from", query.from);
    if (query.to !== undefined) params.set("to", query.to);
    let response: Response;
    try {
      response = await fetchImpl(`/api/v1/audit-events/export?${params.toString()}`, {
        headers,
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(EXPORT_TIMEOUT_MS),
      });
    } catch {
      throw new ApiError("WEB_API_UNREACHABLE", "The API could not be reached.", 0, requestId, { reason: "network" });
    }
    if (response.ok) {
      const named = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "");
      return { blob: await response.blob(), filename: named?.[1] ?? "audit-log.csv" };
    }
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
    const error = (body as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)?.error;
    throw new ApiError(
      error?.code ?? "WEB_API_BAD_RESPONSE",
      error?.message ?? "The API sent an unexpected response.",
      response.status,
      response.headers.get(REQUEST_ID_HEADER) ?? requestId,
      error?.details ?? {},
    );
  });
}

export function useAuditApi(): AuditApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    return {
      list: async (query) =>
        (
          await sessionGet("/api/v1/audit-events", {
            ...base,
            query: {
              ...(query.from === undefined ? {} : { from: query.from }),
              ...(query.to === undefined ? {} : { to: query.to }),
              ...(query.category === undefined ? {} : { category: query.category }),
              ...(query.cursor === undefined ? {} : { cursor: query.cursor }),
            },
          })
        ).data,
      exportCsv: (from, to) =>
        fetchAuditCsv({ ...(from === undefined ? {} : { from }), ...(to === undefined ? {} : { to }) }, clinicId),
    };
  }, [clinicId]);
}

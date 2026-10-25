/**
 * The reviewer's calls (M6c-P2; spec clinic-onboarding R24-R34). JSON through the staff session;
 * a certificate is fetched as a blob through the same session, never by a public link (R26).
 */

import { ApiError, REQUEST_ID_HEADER, newRequestId, type GetResponse } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { withSessionRefresh } from "@/lib/auth/refresh";

export type ApplicationDetail = components["schemas"]["OpsApplicationDetail"];
export type ApplicationDoctor = components["schemas"]["OpsApplicationDoctor"];
export type ApplicationSummary = GetResponse<"/api/v1/ops/applications">["items"][number];
export type RejectReason = components["schemas"]["ApplicationRejectReason"];
export type Queue = "waiting" | "review" | "decided";

export const REJECT_LABELS: Record<RejectReason, string> = {
  REGISTRATION_NOT_FOUND: "A registration is not on the council's register",
  CERTIFICATE_UNCLEAR: "A certificate cannot be read or checked",
  DETAILS_DO_NOT_MATCH: "The certificate and the application do not match",
  NOT_ELIGIBLE: "MediEase cannot list this practice",
  DUPLICATE: "Already applied or already on MediEase",
  OTHER: "Other (write a message)",
};

export const STATUS_LABELS: Record<ApplicationSummary["status"], string> = {
  PENDING: "Waiting",
  UNDER_REVIEW: "Under review",
  APPROVED: "Approved",
  REJECTED: "Rejected",
};

/** One doctor's certificate as a blob, through the staff session (audited by the API). */
export function certificateBlob(applicationId: string, doctorId: string, fetchImpl: typeof fetch = fetch): Promise<Blob> {
  const once = async (): Promise<Blob> => {
    const requestId = newRequestId();
    const response = await fetchImpl(`/api/v1/ops/applications/${encodeURIComponent(applicationId)}/doctors/${encodeURIComponent(doctorId)}/certificate`, {
      headers: { [REQUEST_ID_HEADER]: requestId },
      credentials: "same-origin",
      cache: "no-store",
    });
    if (response.ok) return response.blob();
    let code = "WEB_API_BAD_RESPONSE";
    let message = "The certificate could not be opened.";
    try {
      const body = (await response.json()) as {
        error?: { code?: string; message?: string };
      };
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
    } catch {
      // not JSON: keep the generic words
    }
    throw new ApiError(code, message, response.status, response.headers.get(REQUEST_ID_HEADER) ?? requestId);
  };
  return withSessionRefresh(once);
}

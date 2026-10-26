/**
 * Bills and credit notes (M6d-P2; FR-BIL-02, 07; spec billing R13-R30). Every call names the
 * active clinic when the person has several and refreshes an expired session once. The API does
 * every sum; the screen only shows what it answers.
 */

import { useMemo } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import type { RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionDelete, sessionGet, sessionPost, sessionPut } from "@/lib/auth/refresh";

export type Bill = components["schemas"]["Bill"];
export type BillSummary = components["schemas"]["BillSummary"];
export type BillPage = components["schemas"]["BillPage"];
export type BillStatus = components["schemas"]["BillStatus"];
export type BillLineInput = components["schemas"]["BillLineInput"];
export type BillChange = components["schemas"]["BillChange"];
export type Discount = components["schemas"]["Discount"];
export type DiscountKind = components["schemas"]["DiscountKind"];
export type Payment = components["schemas"]["Payment"];
export type PaymentInput = components["schemas"]["PaymentInput"];
export type PaymentMode = components["schemas"]["PaymentMode"];
export type DuesList = components["schemas"]["DuesList"];

export const MODE_LABELS: Readonly<Record<PaymentMode, string>> = { CASH: "Cash", UPI: "UPI", CARD: "Card" };

export const BIL_VISIT_BILLED = "BIL_VISIT_BILLED";

export const BILL_STATUS_LABELS: Readonly<Record<BillStatus, string>> = {
  DRAFT: "Draft",
  ISSUED: "Issued",
  CANCELLED: "Cancelled",
};

export const BILL_STATUS_TONES = { DRAFT: "waiting", ISSUED: "brand", CANCELLED: "missed" } as const;

export const billPath = (billId: string) => `/bills/${encodeURIComponent(billId)}`;

export interface BillQuery {
  readonly patientId?: string;
  readonly status?: BillStatus;
  readonly cursor?: string;
}

export interface BillsApi {
  readonly list: (query: BillQuery) => Promise<BillPage>;
  readonly get: (billId: string) => Promise<Bill>;
  readonly draft: (patientId: string, visitId?: string) => Promise<Bill>;
  readonly change: (billId: string, change: BillChange) => Promise<Bill>;
  readonly discard: (billId: string) => Promise<void>;
  readonly issue: (billId: string) => Promise<Bill>;
  readonly credit: (billId: string, lineIds: readonly string[] | null, reason: string) => Promise<Bill>;
  /** M6d-P3: a payment or refund, and a void the same day. */
  readonly pay: (billId: string, payment: PaymentInput) => Promise<Bill>;
  readonly voidPayment: (billId: string, paymentId: string, reason: string) => Promise<Bill>;
  /** M6d-P3: who owes the clinic (COLLECTION_VIEW). */
  readonly dues: (patientId?: string) => Promise<DuesList>;
}

export function useBillsApi(): BillsApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    const one = (billId: string): RequestOptions => ({ ...base, pathParams: { bill_id: billId } });
    return {
      list: async (query) =>
        (
          await sessionGet("/api/v1/clinic/bills", {
            ...base,
            query: { patient_id: query.patientId, status: query.status, cursor: query.cursor },
          })
        ).data,
      get: async (billId) => (await sessionGet("/api/v1/clinic/bills/{bill_id}", one(billId))).data,
      draft: async (patientId, visitId) =>
        (await sessionPost("/api/v1/clinic/bills", { patient_id: patientId, ...(visitId === undefined ? {} : { visit_id: visitId }) }, base)).data,
      change: async (billId, change) => (await sessionPut("/api/v1/clinic/bills/{bill_id}", change, one(billId))).data,
      discard: async (billId) => {
        await sessionDelete("/api/v1/clinic/bills/{bill_id}", one(billId));
      },
      issue: async (billId) => (await sessionPost("/api/v1/clinic/bills/{bill_id}/issue", undefined, one(billId))).data,
      credit: async (billId, lineIds, reason) =>
        (await sessionPost("/api/v1/clinic/bills/{bill_id}/credit-notes", { line_ids: lineIds === null ? null : [...lineIds], reason }, one(billId))).data,
      pay: async (billId, payment) => (await sessionPost("/api/v1/clinic/bills/{bill_id}/payments", payment, one(billId))).data,
      voidPayment: async (billId, paymentId, reason) =>
        (
          await sessionPost(
            "/api/v1/clinic/bills/{bill_id}/payments/{payment_id}/void",
            { reason },
            { ...base, pathParams: { bill_id: billId, payment_id: paymentId } },
          )
        ).data,
      dues: async (patientId) => (await sessionGet("/api/v1/clinic/dues", { ...base, query: { patient_id: patientId } })).data,
    };
  }, [clinicId]);
}

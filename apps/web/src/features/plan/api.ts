/**
 * The clinic's plan and trial (M6d-P7; FR-SUB-01; spec plans-and-trial). Owners read it
 * (CLINIC_MANAGE); ops set it from the clinic list. Limits are enforced by the API: a screen
 * only shows what it answers.
 */

import { useMemo } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import type { RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionGet, sessionPut } from "@/lib/auth/refresh";

export type Subscription = components["schemas"]["Subscription"];
export type PlanSummary = components["schemas"]["PlanSummary"];
export type Plan = components["schemas"]["Plan"];

export const PLAN_LABELS: Readonly<Record<Plan, string>> = { SOLO: "Solo", CLINIC: "Clinic", PLUS: "Clinic Plus" };
export const PLANS: readonly Plan[] = ["SOLO", "CLINIC", "PLUS"];
export const SUB_LIMIT_REACHED = "SUB_LIMIT_REACHED";

export function useSubscriptionApi(): { readonly get: () => Promise<Subscription> } {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;
  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    return { get: async () => (await sessionGet("/api/v1/clinic/subscription", base)).data };
  }, [clinicId]);
}

/** Ops: choose a clinic's plan (never one smaller than what it uses, R8). */
export async function setPlan(clinicId: string, plan: Plan): Promise<Subscription> {
  return (await sessionPut("/api/v1/ops/clinics/{clinic_id}/plan", { plan }, { pathParams: { clinic_id: clinicId } })).data;
}

/** "14 days left", "1 day left": the trial in words; undefined when there is no trial running. */
export function trialText(summary: PlanSummary): string | undefined {
  switch (summary.trial_state) {
    case "ACTIVE": {
      const days = summary.trial_days_left ?? 0;
      return `Free trial: ${days} ${days === 1 ? "day" : "days"} left`;
    }
    case "ENDED":
      return "Free trial ended";
    case "NOT_STARTED":
      return "Free trial starts when the clinic goes live";
    default:
      return undefined;
  }
}

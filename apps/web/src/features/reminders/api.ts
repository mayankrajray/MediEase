"use client";

/**
 * Reminders, pending follow-ups and a patient's message history (M5-P4 API, M5-P6 screens).
 * Every call names the active clinic when the person has several and refreshes an expired session
 * once. Message history is status only: the API never sends a message's text or number.
 */

import { useMemo } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import type { RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionGet, sessionPatch, sessionPost } from "@/lib/auth/refresh";

export type Reminder = components["schemas"]["Reminder"];
export type ReminderStatus = components["schemas"]["ReminderStatus"];
export type PendingFollowUp = components["schemas"]["PendingFollowUp"];
export type PatientMessage = components["schemas"]["PatientMessage"];

/** One page of pending follow-ups (R17: 1-100 per request). */
export const PENDING_PAGE = 50;

export interface ReminderApi {
  readonly list: (patientId: string) => Promise<readonly Reminder[]>;
  readonly messages: (patientId: string) => Promise<readonly PatientMessage[]>;
  readonly schedule: (patientId: string, doctorId: string, followUpDate: string) => Promise<Reminder>;
  readonly move: (reminderId: string, followUpDate: string) => Promise<Reminder>;
  readonly cancel: (reminderId: string) => Promise<Reminder>;
  readonly pending: (offset: number) => Promise<readonly PendingFollowUp[]>;
}

export function useReminderApi(): ReminderApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    const patient = (id: string): RequestOptions => ({ ...base, pathParams: { patient_id: id } });
    const reminder = (id: string): RequestOptions => ({ ...base, pathParams: { reminder_id: id } });
    return {
      list: async (id) => (await sessionGet("/api/v1/patients/{patient_id}/reminders", patient(id))).data.items,
      messages: async (id) => (await sessionGet("/api/v1/patients/{patient_id}/messages", patient(id))).data.items,
      schedule: async (id, doctorId, followUpDate) =>
        (
          await sessionPost(
            "/api/v1/patients/{patient_id}/reminders",
            { doctor_id: doctorId, follow_up_date: followUpDate },
            patient(id),
          )
        ).data,
      move: async (id, followUpDate) =>
        (await sessionPatch("/api/v1/reminders/{reminder_id}", { follow_up_date: followUpDate, cancel: false }, reminder(id)))
          .data,
      cancel: async (id) => (await sessionPatch("/api/v1/reminders/{reminder_id}", { cancel: true }, reminder(id))).data,
      pending: async (offset) =>
        (
          await sessionGet("/api/v1/follow-ups/pending", {
            ...base,
            query: { limit: String(PENDING_PAGE), offset: String(offset) },
          })
        ).data.items,
    };
  }, [clinicId]);
}

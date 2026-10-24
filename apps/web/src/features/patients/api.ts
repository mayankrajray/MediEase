"use client";

/**
 * The patient calls, in one place. Every call names the active clinic when the
 * person has several (`X-Clinic-ID`, spec identity-and-tenancy R6) and refreshes an
 * expired session once. The responses carry personal data: they are kept in
 * component state only, never in storage, the URL (beyond a lookup text the person
 * typed) or logs.
 */

import { useMemo } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import type { RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionDelete, sessionGet, sessionPatch, sessionPost, sessionPut } from "@/lib/auth/refresh";

import type { NewPatient, Patient, PatientUpdate } from "./fields";

export type PortalStatus = components["schemas"]["PatientPortalStatus"];
export type PortalInvitation = components["schemas"]["PortalInvitation"];

export interface PatientApi {
  readonly lookup: (q: string, signal?: AbortSignal) => Promise<readonly Patient[]>;
  readonly get: (id: string) => Promise<Patient>;
  readonly register: (body: NewPatient) => Promise<Patient>;
  readonly update: (id: string, body: PatientUpdate) => Promise<Patient>;
  readonly recordConsent: (id: string, whatsapp: boolean, sms: boolean) => Promise<Patient>;
  readonly optOut: (id: string) => Promise<Patient>;
  readonly optIn: (id: string, whatsapp: boolean, sms: boolean) => Promise<Patient>;
  // M6b-P1: the record's link to a patient app account.
  readonly portalStatus: (id: string) => Promise<PortalStatus>;
  readonly invitePortal: (id: string) => Promise<PortalInvitation>;
  readonly unlinkPortal: (id: string) => Promise<PortalStatus>;
}

export function usePatientApi(): PatientApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    const one = (id: string): RequestOptions => ({ ...base, pathParams: { patient_id: id } });
    return {
      lookup: async (q, signal) => {
        const { data } = await sessionGet("/api/v1/patients", {
          ...base,
          query: { q },
          ...(signal === undefined ? {} : { signal }),
        });
        return data.items;
      },
      get: async (id) => (await sessionGet("/api/v1/patients/{patient_id}", one(id))).data,
      register: async (body) => (await sessionPost("/api/v1/patients", body, base)).data,
      update: async (id, body) => (await sessionPatch("/api/v1/patients/{patient_id}", body, one(id))).data,
      recordConsent: async (id, whatsapp, sms) =>
        (await sessionPut("/api/v1/patients/{patient_id}/consent", { whatsapp, sms }, one(id))).data,
      optOut: async (id) => (await sessionPost("/api/v1/patients/{patient_id}/opt-out", undefined, one(id))).data,
      optIn: async (id, whatsapp, sms) =>
        (await sessionPost("/api/v1/patients/{patient_id}/opt-in", { whatsapp, sms }, one(id))).data,
      portalStatus: async (id) => (await sessionGet("/api/v1/patients/{patient_id}/portal", one(id))).data,
      invitePortal: async (id) =>
        (await sessionPost("/api/v1/patients/{patient_id}/portal-invite", undefined, one(id))).data,
      unlinkPortal: async (id) => (await sessionDelete("/api/v1/patients/{patient_id}/portal-link", one(id))).data,
    };
  }, [clinicId]);
}

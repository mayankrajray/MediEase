/**
 * The clinic's fee schedule (M6d-P1; FR-BIL-01; spec billing R1-R4). Every call names the active
 * clinic when the person has several and refreshes an expired session once. Each answer is the
 * whole schedule, so the screen never works out a price.
 */

import { useMemo } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import type { RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionGet, sessionPatch, sessionPost, sessionPut } from "@/lib/auth/refresh";

export type FeeSchedule = components["schemas"]["FeeSchedule"];
export type FeeService = FeeSchedule["services"][number];
export type ServiceKind = components["schemas"]["ServiceKind"];
export type NewService = components["schemas"]["NewService"];
export type ServiceChange = components["schemas"]["ServiceChange"];

export const KIND_LABELS: Readonly<Record<ServiceKind, string>> = {
  CONSULTATION: "Consultation",
  FOLLOW_UP: "Follow-up",
  PROCEDURE: "Procedure",
  OTHER: "Other",
};

export const KIND_OPTIONS = (Object.keys(KIND_LABELS) as ServiceKind[]).map((value) => ({ value, label: KIND_LABELS[value] }));

export interface FeesApi {
  readonly get: () => Promise<FeeSchedule>;
  readonly addService: (service: NewService) => Promise<FeeSchedule>;
  readonly changeService: (serviceId: string, change: ServiceChange) => Promise<FeeSchedule>;
  readonly setDoctorPrice: (serviceId: string, doctorId: string, pricePaise: number | null) => Promise<FeeSchedule>;
}

export function useFeesApi(): FeesApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    return {
      get: async () => (await sessionGet("/api/v1/clinic/fees", base)).data,
      addService: async (service) => (await sessionPost("/api/v1/clinic/fees/services", service, base)).data,
      changeService: async (serviceId, change) =>
        (await sessionPatch("/api/v1/clinic/fees/services/{service_id}", change, { ...base, pathParams: { service_id: serviceId } })).data,
      setDoctorPrice: async (serviceId, doctorId, pricePaise) =>
        (
          await sessionPut(
            "/api/v1/clinic/fees/services/{service_id}/doctors/{doctor_id}",
            { price_paise: pricePaise },
            { ...base, pathParams: { service_id: serviceId, doctor_id: doctorId } },
          )
        ).data,
    };
  }, [clinicId]);
}

/**
 * The owner's directory listing (M6c-P4; spec clinic-onboarding R50-R55). Every call names the
 * active clinic when the person has several and refreshes an expired session once.
 */

import { useMemo } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import type { RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionGet, sessionPut } from "@/lib/auth/refresh";

export type ClinicListing = components["schemas"]["ClinicListing"];
export type ListingProblem = ClinicListing["problems"][number];
export type DoctorListing = ClinicListing["doctors"][number];
export type DoctorProblem = DoctorListing["problems"][number];

export interface ListingApi {
  readonly get: () => Promise<ClinicListing>;
  readonly setListed: (listed: boolean) => Promise<ClinicListing>;
  readonly setVisible: (doctorId: string, visible: boolean) => Promise<ClinicListing>;
}

/** R51: what the owner reads for each problem, with where to fix it. */
export const LISTING_PROBLEM_WORDS: Readonly<Record<ListingProblem, string>> = {
  NOT_ACTIVE: "The clinic is not active.",
  NOT_VERIFIED: "MediEase has not verified the clinic yet.",
  ADDRESS_MISSING: "Add the clinic's address, city and PIN code.",
  NO_BOOKABLE_DOCTOR: "Show at least one verified doctor who has weekly hours.",
};

export const DOCTOR_PROBLEM_WORDS: Readonly<Record<DoctorProblem, string>> = {
  INACTIVE: "Not active",
  NOT_VERIFIED: "Not verified by MediEase",
  NO_SCHEDULE: "No weekly hours",
  HIDDEN: "Hidden",
};

export function useListingApi(): ListingApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    return {
      get: async () => (await sessionGet("/api/v1/clinic/listing", base)).data,
      setListed: async (listed) => (await sessionPut("/api/v1/clinic/listing", { listed }, base)).data,
      setVisible: async (doctorId, visible) =>
        (await sessionPut("/api/v1/clinic/listing/doctors/{doctor_id}", { visible }, { ...base, pathParams: { doctor_id: doctorId } })).data,
    };
  }, [clinicId]);
}

"use client";

/**
 * The owner's Team page (M6a-P5, FR-ORG-07). Every call names the active clinic when the person
 * has several and refreshes an expired session once. Owners only: the API refuses everyone else.
 */

import { useMemo } from "react";

import type { Role } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";
import type { RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionGet, sessionPatch, sessionPost } from "@/lib/auth/refresh";

export type StaffMember = components["schemas"]["StaffMember"];
export type TeamInvitation = components["schemas"]["TeamInvitation"];
export type NewInvite = components["schemas"]["NewStaffInvite"];

export interface TeamApi {
  readonly list: () => Promise<readonly StaffMember[]>;
  readonly invite: (invite: NewInvite) => Promise<TeamInvitation>;
  readonly resend: (membershipId: string) => Promise<TeamInvitation>;
  readonly changeRole: (membershipId: string, role: Role) => Promise<StaffMember>;
  readonly deactivate: (membershipId: string) => Promise<StaffMember>;
}

export function useTeamApi(): TeamApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    const member = (id: string): RequestOptions => ({ ...base, pathParams: { membership_id: id } });
    return {
      list: async () => (await sessionGet("/api/v1/clinic/staff", base)).data.items,
      invite: async (invite) => (await sessionPost("/api/v1/clinic/staff", invite, base)).data,
      resend: async (id) =>
        (await sessionPost("/api/v1/clinic/staff/{membership_id}/resend", undefined, member(id))).data,
      changeRole: async (id, role) =>
        (await sessionPatch("/api/v1/clinic/staff/{membership_id}", { role }, member(id))).data,
      deactivate: async (id) =>
        (await sessionPatch("/api/v1/clinic/staff/{membership_id}", { status: "DEACTIVATED" }, member(id))).data,
    };
  }, [clinicId]);
}

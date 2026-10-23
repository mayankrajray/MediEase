/** Test data for the auth and shell features: invented people and clinics only. */

import type { Membership, PersonAccess, Role } from "./landing";

export const CLINIC_A = "0192f0a0-0000-7000-8000-00000000000a";
export const CLINIC_B = "0192f0a0-0000-7000-8000-00000000000b";

export function membership(
  clinicId: string,
  name: string,
  role: Role = "OWNER",
  overrides: Partial<Membership> = {},
): Membership {
  return {
    membership_id: `m-${clinicId}`,
    clinic_id: clinicId,
    clinic_name: name,
    clinic_status: "ACTIVE",
    role,
    permissions: ["CLINIC_VIEW", "DOCTORS_VIEW"],
    doctor_id: null,
    ...overrides,
  };
}

export function person(
  memberships: readonly Membership[],
  user: Partial<PersonAccess["user"]> = {},
): PersonAccess {
  return {
    user: {
      id: "u-1",
      full_name: "Sample Person",
      email: "person@sample-clinic.example",
      phone_e164: null,
      is_platform_ops: false,
      ...user,
    },
    memberships,
  };
}

export const ops = () => person([], { full_name: "Sample Ops", is_platform_ops: true });

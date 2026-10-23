/** Words and order for the Team page (M6a-P5, decision 2A). */

import type { Tone } from "@/components/ui/StatusBadge";
import type { Role } from "@/features/auth/landing";

import type { StaffMember } from "./api";

export type MemberStatus = StaffMember["status"];

export const ROLES: readonly Role[] = ["OWNER", "DOCTOR", "FRONT_DESK"];

export const STATUS_LABELS: Readonly<Record<MemberStatus, string>> = {
  ACTIVE: "Active",
  INVITED: "Invited",
  DEACTIVATED: "Deactivated",
};

export const STATUS_TONES: Readonly<Record<MemberStatus, Tone>> = {
  ACTIVE: "done",
  INVITED: "waiting",
  DEACTIVATED: "neutral",
};

/** What each role may do, in one line, for the invite form and the change-role dialog. */
export const ROLE_HINTS: Readonly<Record<Role, string>> = {
  OWNER: "Everything, including this Team page and clinic settings.",
  DOCTOR: "Consultations, prescriptions and their own patients.",
  FRONT_DESK: "Patients, bookings and the queue.",
};

const ORDER: Readonly<Record<MemberStatus, number>> = { ACTIVE: 0, INVITED: 1, DEACTIVATED: 2 };

/** Active first, then invited, then deactivated; by name within each (decision 2A). */
export function sortTeam(members: readonly StaffMember[]): StaffMember[] {
  return [...members].sort(
    (a, b) => ORDER[a.status] - ORDER[b.status] || a.full_name.localeCompare(b.full_name, "en"),
  );
}

/** How to reach them: the email if there is one, else the phone. */
export function contactOf(member: Pick<StaffMember, "email" | "phone_e164">): string {
  return member.email ?? member.phone_e164 ?? "–";
}

/**
 * Role workspaces (M6a-P6, decisions 1A, 3A, 4A, 6A; FR-UX-01..06).
 *
 * A workspace is a **view**, never a permission: it decides the navigation, Today's shape and
 * the quick actions, while the API keeps deciding what the role may do. It comes from the
 * membership's role; a practising owner (role `OWNER` with a doctor profile, `doctor_id`)
 * chooses Owner or Doctor, remembered per clinic in this browser, Owner by default.
 */

import type { Membership, Role } from "@/features/auth/landing";

import type { NavItem } from "./nav";

export type Workspace = Role;

export const WORKSPACE_LABELS: Readonly<Record<Workspace, string>> = {
  OWNER: "Owner",
  DOCTOR: "Doctor",
  FRONT_DESK: "Front desk",
};

const STORAGE_PREFIX = "mediease.workspace.";

/** An owner who also practises here: the only person with a choice of workspace. */
export function canSwitch(membership: Membership): boolean {
  return membership.role === "OWNER" && membership.doctor_id !== null;
}

/** The workspace for this membership, given the remembered choice (ignored when not allowed). */
export function resolveWorkspace(membership: Membership, remembered: string | null): Workspace {
  if (canSwitch(membership) && remembered === "DOCTOR") return "DOCTOR";
  return membership.role;
}

export function readRememberedWorkspace(clinicId: string): string | null {
  try {
    return window.localStorage.getItem(`${STORAGE_PREFIX}${clinicId}`);
  } catch {
    return null; // storage refused (private mode): Owner by default
  }
}

export function rememberWorkspace(clinicId: string, workspace: Workspace): void {
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}${clinicId}`, workspace);
  } catch {
    // Not remembered; the choice still applies to this tab.
  }
}

/**
 * Each workspace's navigation (decision 3A). An item appears only once its page exists:
 * booking requests (M6b) and payments (M8) join in their phases; notifications joined in P7. A page left
 * out of a workspace stays reachable by URL when the role is allowed (the switch is a view).
 */
export const WORKSPACE_NAV: Readonly<Record<Workspace, readonly NavItem[]>> = {
  OWNER: [
    { href: "/today", label: "Today" },
    { href: "/queue", label: "Queue" },
    { href: "/patients", label: "Patients", requires: "PATIENTS_MANAGE" },
    { href: "/follow-ups", label: "Follow-ups", requires: "REMINDERS_SCHEDULE" },
    { href: "/team", label: "Team", requires: "STAFF_MANAGE" },
    { href: "/settings/schedule", label: "Schedule", requires: "SCHEDULES_MANAGE" },
    { href: "/settings/notifications", label: "Notifications" },
  ],
  DOCTOR: [
    { href: "/today", label: "Today" },
    { href: "/queue", label: "My queue" },
    { href: "/my-patients", label: "My patients", requires: "CLINICAL_VIEW" },
    { href: "/follow-ups", label: "My follow-ups", requires: "REMINDERS_SCHEDULE" },
    { href: "/my-schedule", label: "My schedule", requires: "DOCTORS_VIEW" },
    { href: "/settings/notifications", label: "Notifications" },
  ],
  FRONT_DESK: [
    { href: "/today", label: "Today" },
    { href: "/queue", label: "Queue" },
    { href: "/patients", label: "Patients", requires: "PATIENTS_MANAGE" },
    { href: "/follow-ups", label: "Follow-ups", requires: "REMINDERS_SCHEDULE" },
    { href: "/settings/notifications", label: "Notifications" },
  ],
};

export type QuickAction =
  | { readonly kind: "link"; readonly label: string; readonly href: string }
  | { readonly kind: "register"; readonly label: string }
  | { readonly kind: "book"; readonly label: string }
  | { readonly kind: "walk-in"; readonly label: string };

/** Today's three quick actions per workspace (decision 4A, FR-UX-05). */
export const QUICK_ACTIONS: Readonly<Record<Workspace, readonly QuickAction[]>> = {
  OWNER: [
    { kind: "link", label: "Invite someone", href: "/team?invite=1" },
    { kind: "link", label: "Schedule settings", href: "/settings/schedule" },
    { kind: "link", label: "See the queue", href: "/queue" },
  ],
  DOCTOR: [
    { kind: "link", label: "Open my queue", href: "/queue" },
    { kind: "link", label: "My patients", href: "/my-patients" },
    { kind: "link", label: "My follow-ups", href: "/follow-ups" },
  ],
  FRONT_DESK: [
    { kind: "register", label: "Register a patient" },
    { kind: "link", label: "Book an appointment", href: "/queue?book=1" },
    { kind: "link", label: "Add a walk-in", href: "/queue?walk-in=1" },
  ],
};

/**
 * Role workspaces (M6a-P6, decisions 1A, 3A, 4A, 6A; FR-UX-01..06).
 *
 * A workspace is a **view**, never a permission: it decides the navigation, Today's shape and
 * the quick actions, while the API keeps deciding what the role may do. It comes from the
 * membership's role; a practising owner (role `OWNER` with a doctor profile, `doctor_id`)
 * chooses Owner or Doctor, remembered per clinic in this browser, Owner by default.
 */

import {
  BadgeCheck,
  Bell,
  CalendarClock,
  CalendarDays,
  CircleDollarSign,
  History,
  Inbox,
  IndianRupee,
  LayoutDashboard,
  ListOrdered,
  MessageSquareText,
  ReceiptText,
  Store,
  UserCog,
  Users,
  Wallet,
} from "lucide-react";

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
 * booking requests (M6b-P4) and payments (M8) join in their phases; notifications joined in P7. A page left
 * out of a workspace stays reachable by URL when the role is allowed (the switch is a view).
 */
const DAY = "Daily work";
const PATIENTS = "Patients";
const MONEY = "Billing";
const CLINIC = "Clinic";
const TOOLS = "Help and alerts";

export const WORKSPACE_NAV: Readonly<Record<Workspace, readonly NavItem[]>> = {
  OWNER: [
    { href: "/today", label: "Today", icon: LayoutDashboard, group: DAY },
    { href: "/queue", label: "Queue", icon: ListOrdered, group: DAY },
    // M6b-P4 (spec R22): what patients asked for on the clinic page.
    { href: "/booking-requests", label: "Booking requests", requires: "APPOINTMENTS_MANAGE", icon: Inbox, group: DAY },
    { href: "/patients", label: "Patients", requires: "PATIENTS_MANAGE", icon: Users, group: PATIENTS },
    { href: "/follow-ups", label: "Follow-ups", requires: "REMINDERS_SCHEDULE", icon: CalendarClock, group: PATIENTS },
    // M6d-P2 (FR-BIL-02): bills; a doctor's list holds only their own.
    { href: "/bills", label: "Bills", requires: "BILLING_MANAGE", icon: ReceiptText, group: MONEY },
    // M6d-P3 (FR-BIL-05): who owes the clinic, owners and the front desk.
    { href: "/dues", label: "Dues", requires: "COLLECTION_VIEW", icon: CircleDollarSign, group: MONEY },
    // M6d-P5 (FR-BIL-06): the day's collection.
    { href: "/collection", label: "Collection", requires: "COLLECTION_VIEW", icon: Wallet, group: MONEY },
    { href: "/team", label: "Team", requires: "STAFF_MANAGE", icon: UserCog, group: CLINIC },
    { href: "/settings/schedule", label: "Schedule", requires: "SCHEDULES_MANAGE", icon: CalendarDays, group: CLINIC },
    // M6a-P8 (FR-AUD-03): the clinic's audit log, owners only.
    { href: "/settings/audit", label: "Audit log", requires: "AUDIT_VIEW", icon: History, group: CLINIC },
    // M6c-P4 (FR-ONB-10): the directory listing and doctor visibility, owners only.
    { href: "/settings/listing", label: "Directory", requires: "CLINIC_MANAGE", icon: Store, group: CLINIC },
    // M6d-P1 (FR-BIL-01): the fee schedule, owners only (others reach it by URL to read it).
    { href: "/settings/fees", label: "Fees", requires: "FEES_MANAGE", icon: IndianRupee, group: CLINIC },
    // M6d-P7 (FR-SUB-01): the plan, its use and the trial, owners only.
    { href: "/settings/plan", label: "Plan", requires: "CLINIC_MANAGE", icon: BadgeCheck, group: CLINIC },
    // M7a-P5 (spec assistant): the staff assistant, with the member's own permissions.
    { href: "/assistant", label: "Assistant", requires: "APPOINTMENTS_MANAGE", icon: MessageSquareText, group: TOOLS },
    { href: "/settings/notifications", label: "Notifications", icon: Bell, group: TOOLS },
  ],
  DOCTOR: [
    { href: "/today", label: "Today", icon: LayoutDashboard, group: DAY },
    { href: "/queue", label: "My queue", icon: ListOrdered, group: DAY },
    { href: "/my-patients", label: "My patients", requires: "CLINICAL_VIEW", icon: Users, group: PATIENTS },
    { href: "/follow-ups", label: "My follow-ups", requires: "REMINDERS_SCHEDULE", icon: CalendarClock, group: PATIENTS },
    { href: "/my-schedule", label: "My schedule", requires: "DOCTORS_VIEW", icon: CalendarDays, group: CLINIC },
    { href: "/bills", label: "My bills", requires: "BILLING_MANAGE", icon: ReceiptText, group: MONEY },
    // M7a-P5 (spec assistant): the staff assistant, with the member's own permissions.
    { href: "/assistant", label: "Assistant", requires: "APPOINTMENTS_MANAGE", icon: MessageSquareText, group: TOOLS },
    { href: "/settings/notifications", label: "Notifications", icon: Bell, group: TOOLS },
  ],
  FRONT_DESK: [
    { href: "/today", label: "Today", icon: LayoutDashboard, group: DAY },
    { href: "/queue", label: "Queue", icon: ListOrdered, group: DAY },
    { href: "/booking-requests", label: "Booking requests", requires: "APPOINTMENTS_MANAGE", icon: Inbox, group: DAY },
    { href: "/patients", label: "Patients", requires: "PATIENTS_MANAGE", icon: Users, group: PATIENTS },
    { href: "/follow-ups", label: "Follow-ups", requires: "REMINDERS_SCHEDULE", icon: CalendarClock, group: PATIENTS },
    { href: "/bills", label: "Bills", requires: "BILLING_MANAGE", icon: ReceiptText, group: MONEY },
    { href: "/dues", label: "Dues", requires: "COLLECTION_VIEW", icon: CircleDollarSign, group: MONEY },
    { href: "/collection", label: "Collection", requires: "COLLECTION_VIEW", icon: Wallet, group: MONEY },
    // M7a-P5 (spec assistant): the staff assistant, with the member's own permissions.
    { href: "/assistant", label: "Assistant", requires: "APPOINTMENTS_MANAGE", icon: MessageSquareText, group: TOOLS },
    { href: "/settings/notifications", label: "Notifications", icon: Bell, group: TOOLS },
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

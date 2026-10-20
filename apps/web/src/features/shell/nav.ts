import type { components } from "@/lib/api/schema";

export type Permission = components["schemas"]["Permission"];

export interface NavItem {
  readonly href: string;
  readonly label: string;
  /** Shown only to roles holding this permission. Omitted = every signed-in member. */
  readonly requires?: Permission;
}

/**
 * The clinic navigation. A page is added to this list in the same change that
 * creates it, so the menu never links to something that does not exist yet.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/queue", label: "Queue" },
  { href: "/patients", label: "Patients", requires: "PATIENTS_MANAGE" },
  // M5-P6: every role holds REMINDERS_SCHEDULE.
  { href: "/follow-ups", label: "Follow-ups", requires: "REMINDERS_SCHEDULE" },
  { href: "/settings/schedule", label: "Schedule", requires: "SCHEDULES_MANAGE" },
];

/**
 * The items a role should see. A convenience only (M1-P6 design, concept 3):
 * hiding a link protects nothing; the API refuses what the role may not do.
 */
export function visibleNav(
  permissions: readonly Permission[],
  items: readonly NavItem[] = NAV_ITEMS,
): readonly NavItem[] {
  return items.filter((item) => item.requires === undefined || permissions.includes(item.requires));
}

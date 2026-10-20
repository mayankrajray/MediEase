/** Words for the Today screen (M6-P1). Pure: no browser APIs. */

import type { Tone } from "@/components/ui/StatusBadge";
import { formatClock } from "@/lib/format/time";

import type { Today } from "./useToday";

export type NextPatient = Today["next_patients"][number];
export type Day = NonNullable<Today["week"]>[number];
export type TodaySession = Today["sessions"][number];

/** "Token 3", or the slot's time on the clinic's clock ("10:30"). */
export function placeLabel(next: Pick<NextPatient, "token_number" | "slot_start">, timeZone: string): string {
  if (next.token_number !== null) return `Token ${next.token_number}`;
  if (next.slot_start !== null) return formatClock(next.slot_start, timeZone);
  return "–";
}

export const NEXT_STATUS: Record<NextPatient["status"], { readonly label: string; readonly tone: Tone }> = {
  ARRIVED: { label: "Waiting", tone: "waiting" },
  BOOKED: { label: "Not arrived", tone: "neutral" },
};

export const SESSION_STATUS: Record<TodaySession["status"], { readonly label: string; readonly tone: Tone }> = {
  OPEN: { label: "Open", tone: "done" },
  CLOSED: { label: "Closed to bookings", tone: "neutral" },
  CANCELLED: { label: "Cancelled", tone: "missed" },
};

/** The share of a day's appointments that were no-shows, as "25%"; "–" for a day with none. */
export function noShowRate(day: Pick<Day, "appointments" | "no_show">): string {
  if (day.appointments === 0) return "–";
  return `${Math.round((day.no_show / day.appointments) * 100)}%`;
}

/** "10:00–13:00" on the clinic's clock. */
export function sessionHours(session: Pick<TodaySession, "starts_at" | "ends_at">, timeZone: string): string {
  return `${formatClock(session.starts_at, timeZone)}–${formatClock(session.ends_at, timeZone)}`;
}

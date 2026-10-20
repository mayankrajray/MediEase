/**
 * Times for people, in the clinic's own zone (apps/web/CLAUDE.md: clinic time,
 * never the browser's). The API sends ISO-8601 with an offset.
 */

const FALLBACK_ZONE = "UTC";

/** "3 Oct 2026, 14:05 IST". An unknown zone name falls back to UTC rather than throwing. */
export function formatDateTime(iso: string, timeZone: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "–";
  }
  const options: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZoneName: "short",
  };
  try {
    return new Intl.DateTimeFormat("en-IN", { ...options, timeZone }).format(date);
  } catch {
    return new Intl.DateTimeFormat("en-IN", { ...options, timeZone: FALLBACK_ZONE }).format(date);
  }
}

/** Whole minutes from `fromIso` to `to`, never negative; `undefined` if either is unreadable. */
export function minutesBetween(fromIso: string, to: string | number | Date): number | undefined {
  const from = new Date(fromIso).getTime();
  const end = new Date(to).getTime();
  if (Number.isNaN(from) || Number.isNaN(end)) {
    return undefined;
  }
  return Math.max(0, Math.floor((end - from) / 60_000));
}

/** "under 1 min", "12 min", "1 h 05 min". */
export function formatDuration(minutes: number): string {
  if (minutes < 1) return "under 1 min";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = String(minutes % 60).padStart(2, "0");
  return `${hours} h ${rest} min`;
}

function inZone(timeZone: string, options: Intl.DateTimeFormatOptions, date: Date): string {
  try {
    return new Intl.DateTimeFormat("en-IN", { ...options, timeZone }).format(date);
  } catch {
    return new Intl.DateTimeFormat("en-IN", { ...options, timeZone: FALLBACK_ZONE }).format(date);
  }
}

/** "10:42" on the clinic's wall clock (M3-P5: slots, sessions, status messages). */
export function formatClock(iso: string | Date, timeZone: string): string {
  const date = typeof iso === "string" ? new Date(iso) : iso;
  if (Number.isNaN(date.getTime())) return "–";
  return inZone(timeZone, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }, date);
}

/** "Mon, 19 Oct, 09:00" on the clinic's calendar and wall clock (M5-P6: when a reminder is due). */
export function formatDayTime(iso: string, timeZone: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "–";
  const day = inZone(timeZone, { weekday: "short", day: "numeric", month: "short" }, date);
  return `${day}, ${formatClock(date, timeZone)}`;
}

/** "Mon 19 Oct" for a clinic-local `YYYY-MM-DD` (a calendar date, no zone needed). */
export function formatDay(isoDate: string): string {
  const date = new Date(`${isoDate}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) return "–";
  return new Intl.DateTimeFormat("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(date);
}

/** `YYYY-MM-DD` plus `days` (calendar arithmetic, no zone). */
export function addDays(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

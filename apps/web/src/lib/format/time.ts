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

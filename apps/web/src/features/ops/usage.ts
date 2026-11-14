import type { GetResponse } from "@/lib/api/client";

export type Usage = GetResponse<"/api/v1/ops/clinic-usage">;
export type UsageRow = Usage["clinics"][number];
export type Counts = UsageRow["totals"];
export type Metric = keyof Counts;

/** The records counted, in the order a clinic's day makes them. */
export const METRICS: readonly { readonly key: Metric; readonly label: string; readonly short: string }[] = [
  { key: "patients", label: "Patients registered", short: "Patients" },
  { key: "appointments", label: "Appointments booked", short: "Appointments" },
  { key: "visits", label: "Visits", short: "Visits" },
  { key: "prescriptions", label: "Prescriptions issued", short: "Prescriptions" },
  { key: "bills", label: "Bills issued", short: "Bills" },
];

const NUMBER = new Intl.NumberFormat("en-IN");
export const formatCount = (n: number): string => NUMBER.format(n);

const SHORT_DAY = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
const DAY_ONLY = new Intl.DateTimeFormat("en-IN", { day: "numeric", timeZone: "UTC" });

/** "19–25 Oct", or "27 Oct – 2 Nov" across a month, for a Monday's ISO date. */
export function weekLabel(start: string): string {
  const from = new Date(`${start}T00:00:00Z`);
  const to = new Date(from.getTime() + 6 * 86_400_000);
  return from.getUTCMonth() === to.getUTCMonth()
    ? `${DAY_ONLY.format(from)}–${SHORT_DAY.format(to)}`
    : `${SHORT_DAY.format(from)} – ${SHORT_DAY.format(to)}`;
}

/** The sum of one metric over the weeks shown. */
export function inWeeks(row: UsageRow, metric: Metric): number {
  return row.weeks.reduce((sum, week) => sum + week.counts[metric], 0);
}

/** Active clinics first, then the most recently used; never-used clinics last. */
export function byActivity(a: UsageRow, b: UsageRow): number {
  if (a.active_this_week !== b.active_this_week) return a.active_this_week ? -1 : 1;
  return (b.last_active_at ?? "").localeCompare(a.last_active_at ?? "");
}

const DAY_KEY = (date: Date, timeZone: string) =>
  new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);

/** "Today, 14:05", "Yesterday, 18:40", "3 days ago" or "2 Oct 2026", in the clinic's zone. */
export function lastActiveLabel(iso: string, timeZone: string, now: Date = new Date()): string {
  const at = new Date(iso);
  const clock = new Intl.DateTimeFormat("en-IN", { timeZone, hour: "2-digit", minute: "2-digit", hour12: false }).format(at);
  const today = DAY_KEY(now, timeZone);
  const day = DAY_KEY(at, timeZone);
  if (day === today) return `Today, ${clock}`;
  const days = Math.round((Date.parse(`${today}T00:00:00Z`) - Date.parse(`${day}T00:00:00Z`)) / 86_400_000);
  if (days === 1) return `Yesterday, ${clock}`;
  if (days > 1 && days < 7) return `${days} days ago`;
  return new Intl.DateTimeFormat("en-IN", { timeZone, day: "numeric", month: "short", year: "numeric" }).format(at);
}

function cell(value: string | number): string {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/**
 * The usage evidence as CSV (Phase 2 deliverable 3): one line per clinic and week, then each
 * clinic's all-time total. Counts and dates only, like the screen.
 */
export function usageCsv(usage: Usage, rows: readonly UsageRow[]): string {
  const header = ["Clinic", "Week starting", "Week ending", ...METRICS.map((m) => m.label)];
  const lines = [header.map(cell).join(",")];
  for (const row of rows) {
    for (const [i, week] of row.weeks.entries()) {
      const end = usage.weeks[i]?.end ?? "";
      lines.push([row.name, week.start, end, ...METRICS.map((m) => week.counts[m.key])].map(cell).join(","));
    }
    lines.push([row.name, "All time", "", ...METRICS.map((m) => row.totals[m.key])].map(cell).join(","));
  }
  return `${lines.join("\n")}\n`;
}

/** Hands a CSV to the browser as a download (nothing leaves the machine). */
export function downloadCsv(filename: string, text: string): void {
  if (typeof URL.createObjectURL !== "function") return;
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

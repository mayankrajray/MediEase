"use client";

import { formatDayTime } from "@/lib/format/time";

import type { Reminder } from "./api";
import { REMINDER_STATUS_LABELS, explainFailure } from "./labels";

/** Status in words first, colour only as a second signal (spec §6, apps/web/CLAUDE.md). */
const TONE: Record<Reminder["status"], string> = {
  SCHEDULED: "bg-brand-50 ring-brand-600 text-brand-900",
  SENT: "bg-green-50 ring-green-700 text-green-950",
  DELIVERED: "bg-green-50 ring-green-700 text-green-950",
  READ: "bg-green-50 ring-green-700 text-green-950",
  FAILED: "bg-red-50 ring-red-700 text-red-950",
  CANCELLED: "bg-slate-100 ring-slate-500 text-slate-900",
  SKIPPED_NO_CONSENT: "bg-amber-50 ring-amber-700 text-amber-950",
};

/** "Follow-up reminder · Mon 19 Oct, 09:00 · Scheduled", and why, when it did not go (spec §6). */
export function ReminderChip({ reminder, timeZone }: Readonly<{ reminder: Reminder; timeZone: string }>) {
  const why = explainFailure(reminder.status, reminder.error_code);
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span className={`inline-block rounded px-2 py-0.5 text-sm font-medium ring-1 ring-inset ${TONE[reminder.status]}`}>
        Follow-up reminder · {formatDayTime(reminder.due_at, timeZone)} · {REMINDER_STATUS_LABELS[reminder.status]}
      </span>
      {why !== null && <span className="text-sm text-slate-800">{why}</span>}
    </span>
  );
}

import { appointmentWord, portalCalendarDate, portalDay, portalTime, type PortalStrings } from "@/lib/i18n/portal";

import type { PortalAppointment, PortalReminder } from "./data";

/** When an appointment is, on the clinic's clock (spec R18, R22): a slot's time, or the token. */
export function appointmentWhen(a: PortalAppointment, zone: string, s: PortalStrings): string {
  const day = portalDay(a.starts_at, zone, s);
  if (a.mode === "SLOTS" || a.token_number === null) return `${day}, ${portalTime(a.starts_at, zone, s)}`;
  const session = s.appointments.session(portalTime(a.session_starts_at, zone, s), portalTime(a.session_ends_at, zone, s));
  return `${day} · ${s.appointments.token(a.token_number)}, ${session}`;
}

export function AppointmentRow({ a, zone, s }: Readonly<{ a: PortalAppointment; zone: string; s: PortalStrings }>) {
  const word = appointmentWord(a.status);
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-t border-slate-200 py-2 first:border-t-0">
      <span>
        <span className="block font-semibold">{appointmentWhen(a, zone, s)}</span>
        <span className="block text-sm text-slate-700">{a.doctor_name}</span>
      </span>
      <span
        className={`rounded-full border px-2 py-0.5 text-sm font-medium ${
          word === "confirmed" || word === "atClinic"
            ? "border-brand-700 text-brand-800"
            : word === "completed"
              ? "border-slate-500 text-slate-800"
              : "border-red-800 text-red-900"
        }`}
      >
        {s.appointments.words[word]}
      </span>
    </li>
  );
}

export function ReminderRow({ r, zone, s }: Readonly<{ r: PortalReminder; zone: string; s: PortalStrings }>) {
  const kind = r.kind === "APPOINTMENT" ? s.reminders.appointment : s.reminders.followUp;
  const when = r.kind === "APPOINTMENT" ? `${portalDay(r.due_at, zone, s)}, ${portalTime(r.due_at, zone, s)}` : portalCalendarDate(r.follow_up_date, s);
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-t border-slate-200 py-2 first:border-t-0">
      <span>
        <span className="block font-semibold">{kind}</span>
        <span className="block text-sm text-slate-700">{s.reminders.due(when)}</span>
      </span>
      <span className="text-sm text-slate-800">{s.reminders.status(r.status)}</span>
    </li>
  );
}

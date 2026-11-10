import { BellRing, CalendarClock, Stethoscope } from "lucide-react";
import type { ReactNode } from "react";

import { StatusBadge, type Tone } from "@/components/ui/StatusBadge";
import {
  type AppointmentWord,
  appointmentWord,
  portalCalendarDate,
  portalDay,
  portalDayParts,
  portalTime,
  type PortalStrings,
} from "@/lib/i18n/portal";

import type { PortalAppointment, PortalReminder } from "./data";

/** When an appointment is, on the clinic's clock (spec R18, R22): a slot's time, or the token. */
export function appointmentWhen(a: PortalAppointment, zone: string, s: PortalStrings): string {
  const day = portalDay(a.starts_at, zone, s);
  if (a.mode === "SLOTS" || a.token_number === null) return `${day}, ${portalTime(a.starts_at, zone, s)}`;
  const session = s.appointments.session(portalTime(a.session_starts_at, zone, s), portalTime(a.session_ends_at, zone, s));
  return `${day} · ${s.appointments.token(a.token_number)}, ${session}`;
}

/** M7c-P7 (M7): one tone per appointment word; the word itself always says the status. */
export const APPOINTMENT_TONE: Record<AppointmentWord, Tone> = {
  confirmed: "brand",
  atClinic: "active",
  completed: "done",
  cancelled: "neutral",
  missed: "missed",
};

/** A calendar-page tile for a day: weekday, date and month, read as one date by the row's text. */
export function DateTile({ iso, zone, s, muted = false }: Readonly<{ iso: string; zone: string; s: PortalStrings; muted?: boolean }>) {
  const p = portalDayParts(iso, zone, s);
  return (
    <span
      aria-hidden="true"
      className={`flex w-14 shrink-0 flex-col items-center self-start rounded-xl border py-1.5 leading-none ${
        muted ? "border-line bg-slate-50 text-slate-700" : "border-brand-200 bg-brand-50 text-brand-900"
      }`}
    >
      <span className="text-[0.6875rem] font-semibold uppercase tracking-wide">{p.weekday}</span>
      <span className="mt-1 text-xl font-bold tabular-nums">{p.day}</span>
      <span className="mt-0.5 text-xs">{p.month}</span>
    </span>
  );
}

export function AppointmentRow({
  a,
  zone,
  s,
  children,
  past = false,
}: Readonly<{ a: PortalAppointment; zone: string; s: PortalStrings; children?: ReactNode; past?: boolean }>) {
  const word = appointmentWord(a.status);
  return (
    <li className="flex gap-3 border-t border-line py-3 first:border-t-0 first:pt-0 last:pb-0">
      <DateTile iso={a.starts_at} zone={zone} s={s} muted={past} />
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <span className="min-w-0">
            <span className="block font-semibold text-slate-900 [overflow-wrap:anywhere]">{appointmentWhen(a, zone, s)}</span>
            <span className="mt-0.5 flex items-center gap-1.5 text-sm text-slate-700">
              <Stethoscope aria-hidden="true" className="size-3.5 shrink-0 text-slate-500" />
              <span className="min-w-0 [overflow-wrap:anywhere]">{a.doctor_name}</span>
            </span>
          </span>
          <StatusBadge tone={APPOINTMENT_TONE[word]}>{s.appointments.words[word]}</StatusBadge>
        </div>
        {children}
      </div>
    </li>
  );
}

export function ReminderRow({ r, zone, s }: Readonly<{ r: PortalReminder; zone: string; s: PortalStrings }>) {
  const kind = r.kind === "APPOINTMENT" ? s.reminders.appointment : s.reminders.followUp;
  const when = r.kind === "APPOINTMENT" ? `${portalDay(r.due_at, zone, s)}, ${portalTime(r.due_at, zone, s)}` : portalCalendarDate(r.follow_up_date, s);
  const Icon = r.kind === "APPOINTMENT" ? BellRing : CalendarClock;
  return (
    <li className="flex items-start gap-3 border-t border-line py-2.5 first:border-t-0 first:pt-0 last:pb-0">
      <span aria-hidden="true" className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-700">
        <Icon className="size-4" />
      </span>
      <span className="flex min-w-0 flex-1 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <span className="min-w-0">
          <span className="block font-semibold text-slate-900">{kind}</span>
          <span className="block text-sm text-slate-700">{s.reminders.due(when)}</span>
        </span>
        <span className="text-sm text-slate-700">{s.reminders.status(r.status)}</span>
      </span>
    </li>
  );
}

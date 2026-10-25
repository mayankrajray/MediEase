"use client";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { portalGet } from "@/lib/auth/portal-session";

import { type PortalAppointmentGroup, type PortalBookingRequest, type PortalReminder, usePortalLoad } from "./data";
import { PortalCard, ScreenLoading, usePortal } from "./PortalShell";
import { AppointmentRow, ReminderRow } from "./Rows";
import { bookingWords } from "@/lib/i18n/booking-request";
import { portalDay, portalTime } from "@/lib/i18n/portal";

function RequestedList({ requests }: Readonly<{ requests: readonly PortalBookingRequest[] }>) {
  const { s } = usePortal();
  const words = bookingWords(s.lang);
  return (
    <PortalCard id="requested" title={words.mine.title}>
      <ul>
        {requests.map((r) => (
          <li key={r.id} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-t border-slate-200 py-2 first:border-t-0">
            <span>
              <span className="block font-semibold">
                {portalDay(r.starts_at, r.timezone, s)}
                {r.mode === "SLOTS" ? `, ${portalTime(r.starts_at, r.timezone, s)}` : ""}
              </span>
              <span className="block text-sm text-slate-700">
                {r.doctor_name} · {r.clinic_name}
              </span>
              <span className="block text-sm text-slate-700">{words.mine.waiting}</span>
            </span>
            <span className="rounded-full border border-amber-800 px-2 py-0.5 text-sm font-medium text-amber-950">{words.mine.requested}</span>
          </li>
        ))}
      </ul>
    </PortalCard>
  );
}

async function loadAppointments(): Promise<{
  readonly groups: readonly PortalAppointmentGroup[];
  readonly reminders: readonly PortalReminder[];
  readonly requests: readonly PortalBookingRequest[];
  readonly now: number;
}> {
  const [groups, reminders, requests] = await Promise.all([
    portalGet("/api/v1/portal/appointments"),
    portalGet("/api/v1/portal/reminders"),
    portalGet("/api/v1/portal/booking-requests"),
  ]);
  return { groups: groups.data.items, reminders: reminders.data.items, requests: requests.data.items, now: Date.now() };
}

/**
 * *My appointments* (M6b-P2; FR-PRT-07, spec R18): one group per linked clinic, upcoming then past,
 * on that clinic's clock; the clinic's reminders under its appointments (decision 7A). One clinic's
 * records never appear in another's group. Open booking requests (M6b-P4, spec R23) come first,
 * as "Requested", also for clinics the account is not linked to.
 */
export function MyAppointments() {
  const { s } = usePortal();
  const loaded = usePortalLoad(loadAppointments);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">{s.appointments.title}</h1>
      {loaded.status === "loading" && <ScreenLoading label={s.loading} />}
      {loaded.status === "failed" && <ErrorNotice error={loaded.error} onRetry={loaded.retry} />}
      {loaded.status === "ready" && loaded.data.requests.length > 0 && <RequestedList requests={loaded.data.requests} />}
      {loaded.status === "ready" &&
        (loaded.data.groups.length === 0 ? (
          loaded.data.requests.length === 0 && <p>{s.appointments.empty}</p>
        ) : (
          loaded.data.groups.map((g) => (
            <ClinicGroup key={g.clinic_id} group={g} now={loaded.data.now} reminders={loaded.data.reminders.filter((r) => r.clinic_id === g.clinic_id)} />
          ))
        ))}
    </div>
  );
}

function ClinicGroup({
  group,
  reminders,
  now,
}: Readonly<{ group: PortalAppointmentGroup; reminders: readonly PortalReminder[]; now: number }>) {
  const { s } = usePortal();
  const upcoming = group.appointments.filter((a) => Date.parse(a.session_ends_at) > now);
  const past = group.appointments.filter((a) => Date.parse(a.session_ends_at) <= now);
  const id = `clinic-${group.clinic_id}`;
  return (
    <PortalCard id={id} title={group.clinic_name}>
      {group.phone_e164 !== null && (
        <a href={`tel:${group.phone_e164}`} className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
          {s.appointments.call}
        </a>
      )}
      {[
        { title: s.appointments.upcoming, rows: upcoming },
        { title: s.appointments.past, rows: past },
      ].map((part) => (
        <div key={part.title}>
          <h3 className="font-semibold text-slate-800">{part.title}</h3>
          {part.rows.length === 0 ? (
            <p className="text-sm text-slate-700">{s.appointments.none}</p>
          ) : (
            <ul>
              {part.rows.map((a) => (
                <AppointmentRow key={a.id} a={a} zone={group.timezone} s={s} />
              ))}
            </ul>
          )}
        </div>
      ))}
      {reminders.length > 0 && (
        <div>
          <h3 className="font-semibold text-slate-800">{s.appointments.reminders}</h3>
          <ul>
            {reminders.map((r) => (
              <ReminderRow key={r.id} r={r} zone={group.timezone} s={s} />
            ))}
          </ul>
        </div>
      )}
    </PortalCard>
  );
}

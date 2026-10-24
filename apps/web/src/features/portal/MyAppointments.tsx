"use client";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { portalGet } from "@/lib/auth/portal-session";

import { type PortalAppointmentGroup, type PortalReminder, usePortalLoad } from "./data";
import { PortalCard, ScreenLoading, usePortal } from "./PortalShell";
import { AppointmentRow, ReminderRow } from "./Rows";

async function loadAppointments(): Promise<{
  readonly groups: readonly PortalAppointmentGroup[];
  readonly reminders: readonly PortalReminder[];
  readonly now: number;
}> {
  const [groups, reminders] = await Promise.all([
    portalGet("/api/v1/portal/appointments"),
    portalGet("/api/v1/portal/reminders"),
  ]);
  return { groups: groups.data.items, reminders: reminders.data.items, now: Date.now() };
}

/**
 * *My appointments* (M6b-P2; FR-PRT-07, spec R18): one group per linked clinic, upcoming then past,
 * on that clinic's clock; the clinic's reminders under its appointments (decision 7A). One clinic's
 * records never appear in another's group.
 */
export function MyAppointments() {
  const { s } = usePortal();
  const loaded = usePortalLoad(loadAppointments);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">{s.appointments.title}</h1>
      {loaded.status === "loading" && <ScreenLoading label={s.loading} />}
      {loaded.status === "failed" && <ErrorNotice error={loaded.error} onRetry={loaded.retry} />}
      {loaded.status === "ready" &&
        (loaded.data.groups.length === 0 ? (
          <p>{s.appointments.empty}</p>
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

"use client";

import { useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { portalGet, portalPost } from "@/lib/auth/portal-session";

import { type PortalAppointment, type PortalAppointmentGroup, type PortalBookingRequest, type PortalReminder, usePortalLoad } from "./data";
import { PortalCard, ScreenLoading, usePortal } from "./PortalShell";
import { AppointmentRow, ReminderRow } from "./Rows";
import { bookingWords } from "@/lib/i18n/booking-request";
import { notificationWords } from "@/lib/i18n/patient-notifications";
import { portalDay, portalTime } from "@/lib/i18n/portal";

/**
 * Open and recently answered booking requests (M6b-P4, P5; spec R48, R49): *Requested*,
 * *Suggested another time* with Accept this time / No thanks, *Declined* with the reason's words,
 * *Expired*; with a call button where the clinic should be phoned. Accepted ones are appointments.
 */
function RequestedList({ requests, onChanged }: Readonly<{ requests: readonly PortalBookingRequest[]; onChanged: () => void }>) {
  const { s } = usePortal();
  const words = bookingWords(s.lang);
  return (
    <PortalCard id="requested" title={words.mine.title}>
      <ul>
        {requests.map((r) => (
          <RequestRow key={r.id} r={r} onChanged={onChanged} />
        ))}
      </ul>
    </PortalCard>
  );
}

function RequestRow({ r, onChanged }: Readonly<{ r: PortalBookingRequest; onChanged: () => void }>) {
  const { s, leave } = usePortal();
  const words = bookingWords(s.lang);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | undefined>(undefined);
  const when = (iso: string) => `${portalDay(iso, r.timezone, s)}${r.mode === "SLOTS" ? `, ${portalTime(iso, r.timezone, s)}` : ""}`;

  async function answer(action: "accept-proposal" | "decline-proposal") {
    if (busy) return;
    setBusy(true);
    try {
      const path =
        action === "accept-proposal"
          ? ("/api/v1/portal/booking-requests/{request_id}/accept-proposal" as const)
          : ("/api/v1/portal/booking-requests/{request_id}/decline-proposal" as const);
      await portalPost(path, undefined, { pathParams: { request_id: r.id } });
      setResult(action === "accept-proposal" ? words.mine.accepted : words.mine.declinedByYou);
      onChanged();
    } catch (failure) {
      if (!leave(failure)) setResult(words.mine.answerFailed);
    } finally {
      setBusy(false);
    }
  }

  const badge =
    r.status === "PROPOSED" ? words.mine.proposed : r.status === "DECLINED" ? words.mine.declined : r.status === "EXPIRED" ? words.mine.expired : words.mine.requested;
  const call =
    r.clinic_phone_e164 !== null && (r.status === "DECLINED" || r.status === "EXPIRED") ? (
      <a href={`tel:${r.clinic_phone_e164}`} className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
        {words.mine.call}
      </a>
    ) : null;
  const button = "inline-flex min-h-11 items-center rounded-lg px-4 font-semibold";

  return (
    <li className="space-y-1 border-t border-slate-200 py-2 first:border-t-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span>
          <span className="block font-semibold">{when(r.starts_at)}</span>
          <span className="block text-sm text-slate-700">
            {r.doctor_name} · {r.clinic_name}
          </span>
        </span>
        <span className="rounded-full border border-amber-800 px-2 py-0.5 text-sm font-medium text-amber-950">{badge}</span>
      </div>
      {r.status === "REQUESTED" ? <p className="text-sm text-slate-700">{words.mine.waiting}</p> : null}
      {r.status === "PROPOSED" && (
        <div className="space-y-2">
          <p>{words.mine.proposedBody(when(r.starts_at), r.original_starts_at === null ? "" : when(r.original_starts_at))}</p>
          {r.respond_by !== null && <p className="text-sm text-slate-700">{words.mine.replyBy(`${portalDay(r.respond_by, r.timezone, s)}, ${portalTime(r.respond_by, r.timezone, s)}`)}</p>}
          {result === undefined && (
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={busy} onClick={() => void answer("accept-proposal")} className={`${button} bg-brand-700 text-white disabled:bg-slate-400`}>
                {words.mine.acceptTime}
              </button>
              <button type="button" disabled={busy} onClick={() => void answer("decline-proposal")} className={`${button} border border-slate-400 bg-white text-slate-900`}>
                {words.mine.noThanks}
              </button>
            </div>
          )}
        </div>
      )}
      {r.status === "DECLINED" && r.decline_reason !== null && <p>{words.mine.reasons[r.decline_reason] ?? words.mine.reasons["OTHER"]}</p>}
      {r.status === "EXPIRED" && <p>{words.mine.expiredBody}</p>}
      {result !== undefined && (
        <p role="status" className="font-medium">
          {result}
        </p>
      )}
      {call}
    </li>
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
      {loaded.status === "ready" && loaded.data.requests.length > 0 && <RequestedList requests={loaded.data.requests} onChanged={loaded.retry} />}
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

/** The clinic's calendar date of an instant (`YYYY-MM-DD`). */
function dayIn(zone: string, at: number): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(at);
}

/** M6b-P6 (spec R69): today's appointment, still in the queue, has a live token page. */
export function isLiveToday(a: PortalAppointment, zone: string, now: number): boolean {
  return (
    (a.status === "BOOKED" || a.status === "ARRIVED" || a.status === "IN_CONSULTATION") &&
    a.on_date === dayIn(zone, now) &&
    Date.parse(a.session_ends_at) > now
  );
}

/** Asks for the appointment's live link (owned by this account, R71) and opens the public page. */
function LiveQueueButton({ appointmentId }: Readonly<{ appointmentId: string }>) {
  const { s, leave } = usePortal();
  const words = notificationWords(s.lang);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function open() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await portalGet("/api/v1/portal/appointments/{appointment_id}/live-link", {
        pathParams: { appointment_id: appointmentId },
      });
      // The page is on this site; keep the address relative so it opens wherever the portal runs.
      window.location.assign(new URL(data.url, window.location.origin).pathname);
    } catch (failure) {
      if (!leave(failure)) setError(failure);
      setBusy(false);
    }
  }

  return (
    <div className="w-full">
      <button
        type="button"
        onClick={() => void open()}
        disabled={busy}
        className="inline-flex min-h-11 items-center rounded-lg bg-brand-700 px-4 font-semibold text-white hover:bg-brand-800 disabled:bg-slate-400"
      >
        {busy ? words.liveOpening : words.liveButton}
      </button>
      {error !== null && <ErrorNotice error={error} />}
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
                <AppointmentRow key={a.id} a={a} zone={group.timezone} s={s}>
                  {isLiveToday(a, group.timezone, now) && <LiveQueueButton appointmentId={a.id} />}
                </AppointmentRow>
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

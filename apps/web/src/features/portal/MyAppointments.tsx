"use client";

import { Building2, CalendarDays, ChevronRight, Phone, Radio, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button, buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusBadge, type Tone } from "@/components/ui/StatusBadge";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { portalGet, portalPost } from "@/lib/auth/portal-session";

import { type PortalAppointment, type PortalAppointmentGroup, type PortalBookingRequest, type PortalReminder, usePortalLoad } from "./data";
import { PORTAL_LINK, PortalCard, PortalTitle, ScreenLoading, usePortal } from "./PortalShell";
import { AppointmentRow, DateTile, ReminderRow } from "./Rows";
import { bookingWords } from "@/lib/i18n/booking-request";
import { notificationWords } from "@/lib/i18n/patient-notifications";
import { portalDay, portalTime } from "@/lib/i18n/portal";

/** A call link that looks like a small secondary button (44 px on a phone). */
const CALL = `${buttonClasses("secondary", "md")} min-h-11 shrink-0`;

/**
 * Open and recently answered booking requests (M6b-P4, P5; spec R48, R49): *Requested*,
 * *Suggested another time* with Accept this time / No thanks, *Declined* with the reason's words,
 * *Expired*; with a call button where the clinic should be phoned. Accepted ones are appointments.
 */
function RequestedList({ requests, onChanged }: Readonly<{ requests: readonly PortalBookingRequest[]; onChanged: () => void }>) {
  const { s } = usePortal();
  const words = bookingWords(s.lang);
  return (
    <PortalCard id="requested" title={words.mine.title} icon={<Send />}>
      <ul>
        {requests.map((r) => (
          <RequestRow key={r.id} r={r} onChanged={onChanged} />
        ))}
      </ul>
    </PortalCard>
  );
}

const REQUEST_TONE: Record<string, Tone> = { PROPOSED: "active", DECLINED: "danger", EXPIRED: "neutral" };

function RequestRow({ r, onChanged }: Readonly<{ r: PortalBookingRequest; onChanged: () => void }>) {
  const { s, leave } = usePortal();
  const words = bookingWords(s.lang);
  const [busy, setBusy] = useState<"accept-proposal" | "decline-proposal" | null>(null);
  const [result, setResult] = useState<string | undefined>(undefined);
  const when = (iso: string) => `${portalDay(iso, r.timezone, s)}${r.mode === "SLOTS" ? `, ${portalTime(iso, r.timezone, s)}` : ""}`;

  async function answer(action: "accept-proposal" | "decline-proposal") {
    if (busy !== null) return;
    setBusy(action);
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
      setBusy(null);
    }
  }

  const badge =
    r.status === "PROPOSED" ? words.mine.proposed : r.status === "DECLINED" ? words.mine.declined : r.status === "EXPIRED" ? words.mine.expired : words.mine.requested;
  const call =
    r.clinic_phone_e164 !== null && (r.status === "DECLINED" || r.status === "EXPIRED") ? (
      <a href={`tel:${r.clinic_phone_e164}`} className={CALL}>
        <Phone aria-hidden="true" className="size-4" />
        {words.mine.call}
      </a>
    ) : null;

  return (
    <li className="flex gap-3 border-t border-line py-3 first:border-t-0 first:pt-0 last:pb-0">
      <DateTile iso={r.starts_at} zone={r.timezone} s={s} muted={r.status === "DECLINED" || r.status === "EXPIRED"} />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <span className="min-w-0">
            <span className="block font-semibold text-slate-900">{when(r.starts_at)}</span>
            <span className="block text-sm text-slate-700 [overflow-wrap:anywhere]">
              {r.doctor_name} · {r.clinic_name}
            </span>
          </span>
          <StatusBadge tone={REQUEST_TONE[r.status] ?? "waiting"}>{badge}</StatusBadge>
        </div>
        {r.status === "REQUESTED" ? <p className="text-sm text-slate-700">{words.mine.waiting}</p> : null}
        {r.status === "PROPOSED" && (
          <div className="space-y-2 rounded-lg border border-sky-200 bg-sky-50 p-3">
            <p className="text-slate-900">{words.mine.proposedBody(when(r.starts_at), r.original_starts_at === null ? "" : when(r.original_starts_at))}</p>
            {r.respond_by !== null && (
              <p className="text-sm text-slate-700">{words.mine.replyBy(`${portalDay(r.respond_by, r.timezone, s)}, ${portalTime(r.respond_by, r.timezone, s)}`)}</p>
            )}
            {result === undefined && (
              <div className="grid gap-2 min-[400px]:flex min-[400px]:flex-wrap">
                <Button variant="primary" loading={busy === "accept-proposal"} disabled={busy !== null} onClick={() => void answer("accept-proposal")} className="min-h-11">
                  {words.mine.acceptTime}
                </Button>
                <Button loading={busy === "decline-proposal"} disabled={busy !== null} onClick={() => void answer("decline-proposal")} className="min-h-11">
                  {words.mine.noThanks}
                </Button>
              </div>
            )}
          </div>
        )}
        {r.status === "DECLINED" && r.decline_reason !== null && <p className="text-slate-800">{words.mine.reasons[r.decline_reason] ?? words.mine.reasons["OTHER"]}</p>}
        {r.status === "EXPIRED" && <p className="text-slate-800">{words.mine.expiredBody}</p>}
        {result !== undefined && (
          <p role="status" className="font-medium text-slate-900">
            {result}
          </p>
        )}
        {call}
      </div>
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
      <PortalTitle>{s.appointments.title}</PortalTitle>
      {loaded.status === "loading" && <ScreenLoading label={s.loading} />}
      {loaded.status === "failed" && <ErrorNotice error={loaded.error} onRetry={loaded.retry} />}
      {loaded.status === "ready" && loaded.data.requests.length > 0 && <RequestedList requests={loaded.data.requests} onChanged={loaded.retry} />}
      {loaded.status === "ready" &&
        (loaded.data.groups.length === 0 ? (
          loaded.data.requests.length === 0 && (
            <EmptyState
              title={s.appointments.empty}
              icon={<CalendarDays className="size-5" />}
              action={
                <Link href="/portal/find" className={PORTAL_LINK}>
                  {s.home.findDoctor}
                  <ChevronRight aria-hidden="true" className="size-4" />
                </Link>
              }
            />
          )
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
    <div className="space-y-2">
      <Button variant="primary" onClick={() => void open()} disabled={busy} icon={<Radio className="size-4" />} className="min-h-11">
        {busy ? words.liveOpening : words.liveButton}
      </Button>
      {error !== null && <ErrorNotice error={error} />}
    </div>
  );
}

function PartHeading({ children }: Readonly<{ children: string }>) {
  return <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">{children}</h3>;
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
    <PortalCard
      id={id}
      title={group.clinic_name}
      icon={<Building2 />}
      action={
        group.phone_e164 !== null && (
          <a href={`tel:${group.phone_e164}`} className={CALL}>
            <Phone aria-hidden="true" className="size-4" />
            {s.appointments.call}
          </a>
        )
      }
    >
      {[
        { title: s.appointments.upcoming, rows: upcoming, past: false },
        { title: s.appointments.past, rows: past, past: true },
      ].map((part) => (
        <div key={part.title} className="space-y-2 border-t border-line pt-3">
          <PartHeading>{part.title}</PartHeading>
          {part.rows.length === 0 ? (
            <p className="text-sm text-slate-700">{s.appointments.none}</p>
          ) : (
            <ul>
              {part.rows.map((a) => (
                <AppointmentRow key={a.id} a={a} zone={group.timezone} s={s} past={part.past}>
                  {isLiveToday(a, group.timezone, now) && <LiveQueueButton appointmentId={a.id} />}
                </AppointmentRow>
              ))}
            </ul>
          )}
        </div>
      ))}
      {reminders.length > 0 && (
        <div className="space-y-2 border-t border-line pt-3">
          <PartHeading>{s.appointments.reminders}</PartHeading>
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

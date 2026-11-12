"use client";

import { CalendarDays, Clock, Users } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { cx } from "@/components/ui/cx";
import { EmptyState } from "@/components/ui/EmptyState";
import { m } from "@/components/ui/Motion";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { STAT_STRIP, StatTile } from "@/components/ui/StatTile";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tabs } from "@/components/ui/Tabs";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useRegisterPatient } from "@/features/patients/RegisterPatientProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { AppPromptsGate } from "@/features/pwa/AppPromptsGate";
import type { Permission } from "@/features/shell/nav";
import { QUICK_ACTIONS, type Workspace } from "@/features/shell/workspace";
import { useWorkspace } from "@/features/shell/WorkspaceProvider";
import { useTeamApi } from "@/features/team/api";
import { formatDay } from "@/lib/format/time";

import { NEXT_STATUS, SESSION_STATUS, noShowRate, placeLabel, sessionHours, type Day, type TodaySession } from "./labels";
import { useToday, type Today } from "./useToday";

/**
 * Today (M6-P1, decisions 5A and 6A): the first screen of every clinic role. Front desk and
 * owners see the clinic; a doctor sees their own sessions. Each count links to the screen it
 * summarises. The numbers refresh with the queue's 5-second rhythm. Owners and doctors also get
 * the last 7 days in a second tab. Counts, codes and first names only: nothing clinical.
 *
 * M7c-P7 (M3): the quick actions sit in the page header (the primary action top right); the five
 * counts are one strip instead of five cards; the day's work (next up, sessions) takes the wide
 * column and what needs following up the narrow one, as list rows instead of cards inside cards.
 * No entrance choreography: only a changed number moves. Each section loads and fails on its own.
 */
export function TodayDashboard() {
  const clinic = useClinic();
  const { clinic: choice, endSession } = useSession();
  const clinicId = choice.kind === "active" && choice.sendClinicHeader ? choice.membership.clinic_id : undefined;
  const role = choice.kind === "active" ? choice.membership.role : "FRONT_DESK";
  const permissions: readonly Permission[] = choice.kind === "active" ? choice.membership.permissions : [];
  const view = useWorkspace();
  const workspace = view?.workspace ?? role;
  // M6a-P6 (decision 4A): only a practising owner asks for the Doctor view; a doctor gets it anyway.
  const { today, error, refresh } = useToday(clinicId, view?.canSwitch === true && workspace === "DOCTOR" ? "doctor" : undefined);

  // A session that can no longer be refreshed sends the person to sign in, as other screens do.
  useEffect(() => {
    if (error !== undefined) endSession(error);
  }, [error, endSession]);

  if (today === undefined) {
    return (
      <>
        <PageHeader title="Today" description={`${WORKSPACE_LINES[workspace]} · ${clinic.name}`} actions={<QuickActions workspace={workspace} />} />
        {error !== undefined ? <ErrorNotice error={error} onRetry={refresh} /> : <TodaySkeleton />}
      </>
    );
  }

  const scopeLine = today.scope === "DOCTOR" ? "Your sessions" : clinic.name;
  const showTeam = workspace === "OWNER" && permissions.includes("STAFF_MANAGE");
  const overview = <Overview today={today} timeZone={clinic.timezone} permissions={permissions} showTeam={showTeam} />;

  return (
    <>
      <PageHeader
        title="Today"
        description={`${formatDay(today.on_date)} · ${WORKSPACE_LINES[workspace]} · ${scopeLine}`}
        actions={<QuickActions workspace={workspace} />}
      />
      {/* M7e-E1: install the app once, Add to Home Screen on an iPhone, Update when ready. */}
      <AppPromptsGate language="en" />
      {error !== undefined && (
        <div className="mb-4">
          <ErrorNotice error={error} onRetry={refresh} message="These numbers could not be refreshed. They show the last update." />
        </div>
      )}
      {today.week === null ? (
        overview
      ) : (
        <Tabs
          label="Views of the day"
          items={[
            { value: "today", label: "Today", content: overview },
            { value: "week", label: "Last 7 days", content: <Week days={today.week} /> },
          ]}
        />
      )}
    </>
  );
}

function TodaySkeleton() {
  return (
    <div>
      <p role="status" className="sr-only">
        Loading today…
      </p>
      <Skeleton className="h-24" />
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-56 lg:col-span-2" />
        <Skeleton className="h-56" />
      </div>
    </div>
  );
}

function Overview({
  today,
  timeZone,
  permissions,
  showTeam,
}: {
  today: Today;
  timeZone: string;
  permissions: readonly Permission[];
  showTeam: boolean;
}) {
  const { counts } = today;
  const doctorNames = new Map(today.sessions.map((s) => [s.doctor_id, s.doctor_name]));
  const showDoctor = doctorNames.size > 1;
  const canBook = permissions.includes("APPOINTMENTS_MANAGE");
  const canSchedule = permissions.includes("SCHEDULES_MANAGE");

  return (
    <div className="space-y-4">
      <ul
        aria-label="Today's appointments"
        className={cx(STAT_STRIP, "grid-cols-2 md:grid-cols-5 max-md:[&>li:last-child]:col-span-2")}
      >
        <StatTile layout="segment" label="Waiting" value={counts.waiting} hint="Arrived, not yet seen" tone="waiting" href="/queue" />
        <StatTile layout="segment" label="In consultation" value={counts.in_consultation} hint="With the doctor now" tone="active" href="/queue" />
        <StatTile layout="segment" label="Not arrived" value={counts.not_arrived} hint="Booked for today" href="/queue" />
        <StatTile layout="segment" label="Completed" value={counts.completed} hint="Seen today" tone="done" href="/queue" />
        <StatTile layout="segment" label="No-shows" value={counts.no_show} hint="Did not come" tone="missed" href="/queue" />
      </ul>

      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card
            title="Next up"
            action={
              <Link href="/queue" className="rounded text-sm font-semibold text-brand-800 underline-offset-4 hover:underline">
                Open the queue
              </Link>
            }
          >
            {today.next_patients.length === 0 ? (
              <EmptyState
                icon={<Users className="size-5" />}
                title="No one is waiting"
                action={
                  canBook ? (
                    <Link href="/queue?book=1" className={buttonClasses("secondary", "sm")}>
                      Book an appointment
                    </Link>
                  ) : undefined
                }
              >
                Nobody else is booked for the rest of today.
              </EmptyState>
            ) : (
              <ol className="-mx-1 divide-y divide-line">
                {today.next_patients.map((next) => (
                  <li key={next.appointment_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 py-2.5">
                    <span className="min-w-20 rounded-md bg-surface-muted px-2 py-1 text-center text-sm font-semibold tabular-nums text-slate-800">
                      {placeLabel(next, timeZone)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="font-medium text-slate-900">{next.patient_first_name}</span>{" "}
                      <span className="text-sm tabular-nums text-slate-600">{next.patient_code}</span>
                      {showDoctor && <span className="block text-sm text-slate-600">{doctorNames.get(next.doctor_id)}</span>}
                    </span>
                    <StatusBadge tone={NEXT_STATUS[next.status].tone}>{NEXT_STATUS[next.status].label}</StatusBadge>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <SessionsCard today={today} timeZone={timeZone} canSchedule={canSchedule} />
        </div>

        <div className="space-y-4">
          {showTeam && <TeamCard />}
          <Card title="Follow-ups and messages">
            <ul className="-mx-3 -my-1 space-y-0.5">
              <StatTile
                layout="row"
                label="Follow-ups due"
                value={today.follow_ups_pending}
                hint="Past their follow-up date, not yet seen"
                tone="brand"
                href="/follow-ups"
              />
              {today.bookings_to_move !== null && today.bookings_to_move > 0 && (
                // M6a-P8 (FR-APT-09): closed by leave or a schedule change; move or cancel each.
                <StatTile
                  layout="row"
                  label="Bookings to move"
                  value={today.bookings_to_move}
                  hint="In sessions closed by leave or a schedule change"
                  tone="danger"
                  href="/bookings-to-move"
                />
              )}
              {today.booking_requests_open !== null && today.booking_requests_open > 0 && (
                // M6b-P5 (R45): what patients asked for on the clinic page, waiting for an answer.
                <StatTile
                  layout="row"
                  label="Booking requests waiting"
                  value={today.booking_requests_open}
                  hint="Answer before the reply-by time"
                  tone="waiting"
                  href="/booking-requests"
                />
              )}
              {today.requests_answered_30d !== null &&
                today.requests_expired_30d !== null &&
                today.requests_answered_30d + today.requests_expired_30d > 0 && (
                  // R46: the share answered before the deadline; owners only.
                  <StatTile
                    layout="row"
                    label="Requests answered in time"
                    value={`${Math.round((100 * today.requests_answered_30d) / (today.requests_answered_30d + today.requests_expired_30d))}%`}
                    hint={`Last 30 days · ${today.requests_expired_30d} expired unanswered`}
                    tone={today.requests_expired_30d > 0 ? "waiting" : "done"}
                  />
                )}
              {today.messages_failed !== null && (
                <StatTile
                  layout="row"
                  label="Messages failed today"
                  value={today.messages_failed}
                  hint="A patient's profile shows each message"
                  tone={today.messages_failed > 0 ? "danger" : "neutral"}
                />
              )}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}

function SessionsCard({ today, timeZone, canSchedule }: { today: Today; timeZone: string; canSchedule: boolean }) {
  return (
    <Card title={today.scope === "DOCTOR" ? "Your sessions" : "Sessions"}>
      {today.sessions.length === 0 ? (
        <EmptyState
          icon={<CalendarDays className="size-5" />}
          title="No sessions today"
          action={
            canSchedule ? (
              <Link href="/settings/schedule" className={buttonClasses("secondary", "sm")}>
                Open schedule settings
              </Link>
            ) : undefined
          }
        >
          Sessions come from each doctor&apos;s weekly schedule.
        </EmptyState>
      ) : (
        <ul className="-mx-1 divide-y divide-line">
          {today.sessions.map((s) => (
            <SessionRow key={s.id} session={s} timeZone={timeZone} />
          ))}
        </ul>
      )}
    </Card>
  );
}

/**
 * One session: who and when, its status in words, and how full it is. The bar repeats the
 * "11 of 20 booked" line for the eye; the line is what screen readers read.
 */
function SessionRow({ session: s, timeZone }: { session: TodaySession; timeZone: string }) {
  const filled = s.capacity > 0 ? Math.min(100, Math.round((100 * s.counts.total) / s.capacity)) : 0;
  return (
    <li className="grid gap-x-4 gap-y-2 px-1 py-3 sm:grid-cols-[minmax(0,1fr)_12rem] sm:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="inline-flex items-center gap-1.5 font-medium tabular-nums text-slate-900">
            <Clock aria-hidden="true" className="size-4 text-slate-500" />
            {sessionHours(s, timeZone)}
          </span>
          {/* Also in the doctor's own view: it confirms whose sessions these are (FR-UX-06). */}
          <span className="text-slate-700">· {s.doctor_name}</span>
          <StatusBadge tone={SESSION_STATUS[s.status].tone}>{SESSION_STATUS[s.status].label}</StatusBadge>
        </div>
        <p className="mt-1 text-sm tabular-nums text-slate-700">
          {s.counts.total} of {s.capacity} booked · {s.counts.waiting} waiting · {s.counts.completed} completed
        </p>
      </div>
      <div aria-hidden="true" className="h-2 overflow-hidden rounded-full bg-surface-muted ring-1 ring-inset ring-line">
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${filled}%` }} />
      </div>
    </li>
  );
}

/** The last 7 days: a small bar chart for the eye and the same numbers as a table for everyone. */
function Week({ days }: { days: readonly Day[] }) {
  const most = Math.max(1, ...days.map((d) => d.appointments));
  const withMessages = days.some((d) => d.messages_sent !== null);
  return (
    <Card title="Last 7 days" description="Appointments each day, oldest first">
      <div aria-hidden="true" className="mb-5 flex h-36 items-end gap-2 border-b border-line pb-px">
        {days.map((d) => (
          <div key={d.on_date} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
            <span className="text-xs font-semibold tabular-nums text-slate-700">{d.appointments}</span>
            <m.div
              initial={{ scaleY: 0 }}
              animate={{ scaleY: 1 }}
              transition={{ duration: 0.3 }}
              style={{ height: `${Math.max(4, (d.appointments / most) * 96)}px`, originY: 1 }}
              className="w-full max-w-12 rounded-t-md bg-brand-500"
            />
          </div>
        ))}
      </div>
      <div aria-hidden="true" className="-mt-4 mb-4 flex gap-2">
        {days.map((d) => (
          <span key={d.on_date} className="flex-1 text-center text-xs text-slate-600">
            {formatDay(d.on_date).split(",")[0]}
          </span>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[26rem] text-left text-sm">
          <caption className="sr-only">Appointments, completed visits, no-shows and messages each day</caption>
          <thead className="bg-surface-muted text-slate-700">
            <tr>
              <th scope="col" className="px-2 py-2 font-semibold">Day</th>
              <th scope="col" className="px-2 py-2 font-semibold">Appointments</th>
              <th scope="col" className="px-2 py-2 font-semibold">Completed</th>
              <th scope="col" className="px-2 py-2 font-semibold">No-show rate</th>
              {withMessages && <th scope="col" className="px-2 py-2 font-semibold">Messages sent</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-line tabular-nums">
            {days.map((d) => (
              <tr key={d.on_date}>
                <th scope="row" className="px-2 py-2 font-medium">{formatDay(d.on_date)}</th>
                <td className="px-2 py-2">{d.appointments}</td>
                <td className="px-2 py-2">{d.completed}</td>
                <td className="px-2 py-2">{noShowRate(d)}</td>
                {withMessages && <td className="px-2 py-2">{d.messages_sent ?? "–"}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

const WORKSPACE_LINES: Readonly<Record<Workspace, string>> = {
  OWNER: "Clinic overview",
  DOCTOR: "My day",
  FRONT_DESK: "Front desk",
};

/**
 * Each workspace's three first actions (decision 4A, FR-UX-05), at the top right of the page.
 * The first is the page's one primary action.
 */
function QuickActions({ workspace }: { workspace: Workspace }) {
  const openRegister = useRegisterPatient();
  return (
    <nav aria-label="Quick actions">
      <ul className="flex flex-wrap gap-2">
        {QUICK_ACTIONS[workspace].map((action, index) => {
          const variant = index === 0 ? "primary" : "secondary";
          return (
            <li key={action.label}>
              {action.kind === "register" ? (
                openRegister !== null && (
                  <Button variant={variant} onClick={() => openRegister()}>
                    {action.label}
                  </Button>
                )
              ) : (
                <Link href={action.kind === "link" ? action.href : "/queue"} className={buttonClasses(variant)}>
                  {action.label}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/**
 * The owner's view of their staff (FR-UX-01): who is active, and invitations still open. Its own
 * section: it loads, fails and retries without touching the rest of Today (DESIGN.md §8a).
 */
function TeamCard() {
  const api = useTeamApi();
  const { endSession } = useSession();
  const [state, setState] = useState<
    | { readonly kind: "loading" }
    | { readonly kind: "failed"; readonly error: unknown }
    | { readonly kind: "ready"; readonly active: number; readonly invited: number }
  >({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => {
    setState({ kind: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.list().then(
      (members) => {
        if (cancelled) return;
        setState({
          kind: "ready",
          active: members.filter((m) => m.status === "ACTIVE").length,
          invited: members.filter((m) => m.status === "INVITED").length,
        });
      },
      (failure: unknown) => {
        if (cancelled || endSession(failure)) return;
        setState({ kind: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, endSession, attempt]);

  return (
    <Card title="Team">
      {state.kind === "loading" ? (
        <div>
          <p role="status" className="sr-only">
            Loading the team…
          </p>
          <Skeleton className="h-12" />
          <Skeleton className="mt-2 h-12" />
        </div>
      ) : state.kind === "failed" ? (
        <ErrorNotice error={state.error} onRetry={retry} message="The team could not be loaded." />
      ) : (
        <ul aria-label="Team" className="-mx-3 -my-1 space-y-0.5">
          <StatTile layout="row" label="Team members" value={state.active} hint="Active in this clinic" href="/team" />
          <StatTile
            layout="row"
            label="Invitations open"
            value={state.invited}
            hint="Not accepted yet"
            tone={state.invited > 0 ? "waiting" : "neutral"}
            href="/team"
          />
        </ul>
      )}
    </Card>
  );
}

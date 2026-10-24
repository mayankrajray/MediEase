"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { m, RISE, STAGGER } from "@/components/ui/Motion";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatTile } from "@/components/ui/StatTile";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tabs } from "@/components/ui/Tabs";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useRegisterPatient } from "@/features/patients/RegisterPatientProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { QUICK_ACTIONS, type Workspace } from "@/features/shell/workspace";
import { useWorkspace } from "@/features/shell/WorkspaceProvider";
import { useTeamApi } from "@/features/team/api";
import { formatDay } from "@/lib/format/time";

import { NEXT_STATUS, SESSION_STATUS, noShowRate, placeLabel, sessionHours, type Day } from "./labels";
import { useToday, type Today } from "./useToday";

/**
 * Today (M6-P1, decisions 5A and 6A): the first screen of every clinic role. Front desk and
 * owners see the clinic; a doctor sees their own sessions. Each tile links to the screen it
 * summarises. The numbers refresh with the queue's 5-second rhythm. Owners and doctors also get
 * the last 7 days in a second tab. Counts, codes and first names only: nothing clinical.
 */
export function TodayDashboard() {
  const clinic = useClinic();
  const { clinic: choice, endSession } = useSession();
  const clinicId = choice.kind === "active" && choice.sendClinicHeader ? choice.membership.clinic_id : undefined;
  const role = choice.kind === "active" ? choice.membership.role : "FRONT_DESK";
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
        <PageHeader title="Today" description={`${WORKSPACE_LINES[workspace]} · ${clinic.name}`} />
        {error !== undefined ? <ErrorNotice error={error} onRetry={refresh} /> : <TodaySkeleton />}
      </>
    );
  }

  const scopeLine = today.scope === "DOCTOR" ? "Your sessions" : clinic.name;
  const overview = (
    <div className="space-y-4">
      {workspace === "OWNER" && choice.kind === "active" && choice.membership.permissions.includes("STAFF_MANAGE") && (
        <TeamTile />
      )}
      <Overview today={today} timeZone={clinic.timezone} />
    </div>
  );

  return (
    <>
      <PageHeader
        title="Today"
        description={`${formatDay(today.on_date)} · ${WORKSPACE_LINES[workspace]} · ${scopeLine}`}
      />
      <QuickActions workspace={workspace} />
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
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="mt-4 h-48" />
    </div>
  );
}

function Overview({ today, timeZone }: { today: Today; timeZone: string }) {
  const { counts } = today;
  const doctorNames = new Map(today.sessions.map((s) => [s.doctor_id, s.doctor_name]));
  const showDoctor = doctorNames.size > 1;

  return (
    <div className="space-y-4">
      <m.ul
        variants={STAGGER}
        initial="hidden"
        animate="shown"
        aria-label="Today's appointments"
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
      >
        <StatTile label="Waiting" value={counts.waiting} hint="Arrived, not yet seen" tone="waiting" href="/queue" />
        <StatTile label="In consultation" value={counts.in_consultation} tone="active" href="/queue" />
        <StatTile label="Not arrived" value={counts.not_arrived} hint="Booked for today" href="/queue" />
        <StatTile label="Completed" value={counts.completed} tone="done" href="/queue" />
        <StatTile label="No-shows" value={counts.no_show} tone="missed" href="/queue" />
      </m.ul>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Next up"
          className="lg:col-span-2"
          action={
            <Link href="/queue" className="text-sm font-medium text-brand-800 underline-offset-2 hover:underline">
              Open the queue
            </Link>
          }
        >
          {today.next_patients.length === 0 ? (
            <EmptyState title="No one is waiting">Nobody else is booked for the rest of today.</EmptyState>
          ) : (
            <m.ol variants={STAGGER} initial="hidden" animate="shown" className="divide-y divide-slate-100">
              {today.next_patients.map((next) => (
                <m.li key={next.appointment_id} variants={RISE} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
                  <span className="min-w-20 rounded-md bg-slate-100 px-2 py-1 text-center text-sm font-semibold tabular-nums text-slate-800">
                    {placeLabel(next, timeZone)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="font-medium text-slate-900">{next.patient_first_name}</span>{" "}
                    <span className="text-sm text-slate-600">{next.patient_code}</span>
                    {showDoctor && (
                      <span className="block text-sm text-slate-600">{doctorNames.get(next.doctor_id)}</span>
                    )}
                  </span>
                  <StatusBadge tone={NEXT_STATUS[next.status].tone}>{NEXT_STATUS[next.status].label}</StatusBadge>
                </m.li>
              ))}
            </m.ol>
          )}
        </Card>

        <Card title="Follow-ups and messages">
          <m.ul variants={STAGGER} initial="hidden" animate="shown" className="grid gap-3">
            <StatTile
              label="Follow-ups due"
              value={today.follow_ups_pending}
              hint="Past their follow-up date, not yet seen"
              tone="brand"
              href="/follow-ups"
            />
            {today.bookings_to_move !== null && today.bookings_to_move > 0 && (
              // M6a-P8 (FR-APT-09): closed by leave or a schedule change; move or cancel each.
              <StatTile
                label="Bookings to move"
                value={today.bookings_to_move}
                hint="In sessions closed by leave or a schedule change"
                tone="danger"
                href="/bookings-to-move"
              />
            )}
            {today.messages_failed !== null && (
              <StatTile
                label="Messages failed today"
                value={today.messages_failed}
                hint="A patient's profile shows each message"
                tone={today.messages_failed > 0 ? "danger" : "neutral"}
              />
            )}
          </m.ul>
        </Card>
      </div>

      <Card title={today.scope === "DOCTOR" ? "Your sessions" : "Sessions"}>
        {today.sessions.length === 0 ? (
          <EmptyState title="No sessions today">Sessions come from each doctor&apos;s weekly schedule.</EmptyState>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {today.sessions.map((s) => (
              <li key={s.id} className="rounded-lg border border-slate-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-slate-900">{s.doctor_name}</span>
                  <StatusBadge tone={SESSION_STATUS[s.status].tone}>{SESSION_STATUS[s.status].label}</StatusBadge>
                </div>
                <p className="mt-1 text-sm tabular-nums text-slate-700">{sessionHours(s, timeZone)}</p>
                <p className="mt-1 text-sm text-slate-700">
                  {s.counts.total} of {s.capacity} booked · {s.counts.waiting} waiting · {s.counts.completed} completed
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

/** The last 7 days: a small bar chart for the eye and the same numbers as a table for everyone. */
function Week({ days }: { days: readonly Day[] }) {
  const most = Math.max(1, ...days.map((d) => d.appointments));
  const withMessages = days.some((d) => d.messages_sent !== null);
  return (
    <Card title="Last 7 days">
      <div aria-hidden="true" className="mb-4 flex h-28 items-end gap-2">
        {days.map((d) => (
          <div key={d.on_date} className="flex flex-1 flex-col items-center gap-1">
            <m.div
              initial={{ scaleY: 0 }}
              animate={{ scaleY: 1 }}
              transition={{ duration: 0.3 }}
              style={{ height: `${Math.max(4, (d.appointments / most) * 96)}px`, originY: 1 }}
              className="w-full rounded-t-md bg-brand-600"
            />
            <span className="text-xs text-slate-600">{formatDay(d.on_date).split(",")[0]}</span>
          </div>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[26rem] text-left text-sm">
          <caption className="sr-only">Appointments, completed visits, no-shows and messages each day</caption>
          <thead className="text-slate-700">
            <tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">Day</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">Appointments</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">Completed</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">No-show rate</th>
              {withMessages && <th scope="col" className="py-1.5 font-medium">Messages sent</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 tabular-nums">
            {days.map((d) => (
              <tr key={d.on_date}>
                <th scope="row" className="py-1.5 pr-3 font-medium">{formatDay(d.on_date)}</th>
                <td className="py-1.5 pr-3">{d.appointments}</td>
                <td className="py-1.5 pr-3">{d.completed}</td>
                <td className="py-1.5 pr-3">{noShowRate(d)}</td>
                {withMessages && <td className="py-1.5">{d.messages_sent ?? "–"}</td>}
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

/** Each workspace's three first actions (decision 4A, FR-UX-05). */
function QuickActions({ workspace }: { workspace: Workspace }) {
  const openRegister = useRegisterPatient();
  return (
    <nav aria-label="Quick actions" className="mb-5">
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

/** The owner's view of their staff (FR-UX-01): who is active, and invitations still open. */
function TeamTile() {
  const api = useTeamApi();
  const { endSession } = useSession();
  const [counts, setCounts] = useState<{ readonly active: number; readonly invited: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.list().then(
      (members) => {
        if (cancelled) return;
        setCounts({
          active: members.filter((m) => m.status === "ACTIVE").length,
          invited: members.filter((m) => m.status === "INVITED").length,
        });
      },
      (failure: unknown) => {
        if (!cancelled) endSession(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, endSession]);

  if (counts === null) return null;
  return (
    <m.ul variants={STAGGER} initial="hidden" animate="shown" aria-label="Team" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatTile label="Team members" value={counts.active} hint="Active in this clinic" href="/team" />
      <StatTile
        label="Invitations open"
        value={counts.invited}
        hint="Not accepted yet"
        tone={counts.invited > 0 ? "waiting" : "neutral"}
        href="/team"
      />
    </m.ul>
  );
}

"use client";

import Link from "next/link";
import { useEffect } from "react";

import { buttonClasses } from "@/components/ui/Button";
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
import { useClinic } from "@/features/shell/ClinicGate";
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
  const { today, error, refresh } = useToday(clinicId);

  // A session that can no longer be refreshed sends the person to sign in, as other screens do.
  useEffect(() => {
    if (error !== undefined) endSession(error);
  }, [error, endSession]);

  if (today === undefined) {
    return (
      <>
        <PageHeader title="Today" description={clinic.name} />
        {error !== undefined ? <ErrorNotice error={error} onRetry={refresh} /> : <TodaySkeleton />}
      </>
    );
  }

  const scopeLine = today.scope === "DOCTOR" ? "Your sessions" : clinic.name;
  const overview = <Overview today={today} timeZone={clinic.timezone} />;

  return (
    <>
      <PageHeader
        title="Today"
        description={`${formatDay(today.on_date)} · ${scopeLine}`}
        actions={
          <Link href="/queue" className={buttonClasses("primary")}>
            Open the queue
          </Link>
        }
      />
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

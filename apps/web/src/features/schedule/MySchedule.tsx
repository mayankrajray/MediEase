"use client";

import { CalendarDays, Plane, Stethoscope } from "lucide-react";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useAppointmentApi, type Schedule } from "@/features/appointments/api";
import { clinicToday } from "@/features/patients/fields";
import { useClinic } from "@/features/shell/ClinicGate";
import { useWorkspace } from "@/features/shell/WorkspaceProvider";
import { formatDay } from "@/lib/format/time";

import { WEEKDAYS } from "./ScheduleSettings";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly schedule: Schedule }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * *My schedule* (M6a-P6, decision 7A): my weekly hours, leave and extra sessions, read-only.
 * Changing them stays the owner's (`SCHEDULES_MANAGE`, Schedule settings).
 */
export function MySchedule() {
  const clinic = useClinic();
  const api = useAppointmentApi();
  const view = useWorkspace();
  const { endSession } = useSession();
  const doctorId = view?.doctorId ?? null;
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (doctorId === null) return;
    let cancelled = false;
    api.schedule(doctorId).then(
      (schedule) => {
        if (!cancelled) setLoad({ status: "ready", schedule });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, doctorId, attempt, endSession]);

  const header = <PageHeader title="My schedule" description="Your weekly hours and days off. The clinic owner changes them." />;
  if (doctorId === null) {
    return (
      <>
        {header}
        <EmptyState icon={<Stethoscope className="size-5" />} title="You have no doctor profile in this clinic.">The owner can link one on the Team page.</EmptyState>
      </>
    );
  }
  if (load.status === "loading") {
    return (
      <>
        {header}
        <p role="status" className="sr-only">
          Loading your schedule…
        </p>
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-72" />
          <Skeleton className="h-40" />
        </div>
      </>
    );
  }
  if (load.status === "failed") {
    return (
      <>
        {header}
        <ErrorNotice error={load.error} onRetry={() => setAttempt((n) => n + 1)} />
      </>
    );
  }

  const today = clinicToday(clinic.timezone);
  const blocks = [...load.schedule.blocks].sort(
    (a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time),
  );
  const coming = load.schedule.exceptions.filter((e) => e.on_date >= today).sort((a, b) => a.on_date.localeCompare(b.on_date));

  return (
    <>
      {header}
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Card title="Every week" description="Monday to Sunday, on the clinic's clock">
          {blocks.length === 0 ? (
            <EmptyState icon={<CalendarDays className="size-5" />} title="No weekly hours yet">
              The clinic owner sets them in Schedule settings.
            </EmptyState>
          ) : (
            // M7c-P7 (M4): every day of the week, so a day off reads as one, not as a gap.
            <ul className="divide-y divide-line">
              {WEEKDAYS.map((day, weekday) => {
                const hours = blocks.filter((b) => b.weekday === weekday);
                return (
                  <li key={day} className="flex flex-wrap justify-between gap-2 py-2.5">
                    <span className={hours.length === 0 ? "text-slate-600" : "font-medium text-slate-900"}>{day}</span>
                    {hours.length === 0 ? (
                      <span className="text-slate-600">Not working</span>
                    ) : (
                      <span className="flex flex-col items-end tabular-nums text-slate-800">
                        {hours.map((b) => (
                          <span key={b.id}>
                            {b.start_time}–{b.end_time}
                            {b.overnight && " (next day)"}
                          </span>
                        ))}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Card>        <Card title="Leave and extra sessions">
          {coming.length === 0 ? (
            <EmptyState icon={<Plane className="size-5" />} title="Nothing coming up">
              Leave and extra sessions the owner adds appear here.
            </EmptyState>
          ) : (
            <ul className="divide-y divide-line">
              {coming.map((e) => (
                <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <span className="font-medium text-slate-900">{formatDay(e.on_date)}</span>
                  {e.kind === "LEAVE" ? (
                    <StatusBadge tone="missed">Leave</StatusBadge>
                  ) : (
                    <span className="tabular-nums text-slate-800">{`Extra session ${e.start_time ?? ""}–${e.end_time ?? ""}`}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}

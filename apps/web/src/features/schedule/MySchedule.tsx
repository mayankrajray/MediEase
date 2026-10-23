"use client";

import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
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
        <EmptyState title="You have no doctor profile in this clinic.">The owner can link one on the Team page.</EmptyState>
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
        <Skeleton className="h-40 w-full" />
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
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Every week">
          {blocks.length === 0 ? (
            <EmptyState title="No weekly hours yet" />
          ) : (
            <ul className="divide-y divide-slate-100">
              {blocks.map((b) => (
                <li key={b.id} className="flex flex-wrap justify-between gap-2 py-2">
                  <span className="font-medium">{WEEKDAYS[b.weekday]}</span>
                  <span className="tabular-nums text-slate-800">
                    {b.start_time}–{b.end_time}
                    {b.overnight && " (next day)"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Leave and extra sessions">
          {coming.length === 0 ? (
            <EmptyState title="Nothing coming up" />
          ) : (
            <ul className="divide-y divide-slate-100">
              {coming.map((e) => (
                <li key={e.id} className="flex flex-wrap justify-between gap-2 py-2">
                  <span className="font-medium">{formatDay(e.on_date)}</span>
                  <span className="text-slate-800">
                    {e.kind === "LEAVE" ? "Leave" : `Extra session ${e.start_time ?? ""}–${e.end_time ?? ""}`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}

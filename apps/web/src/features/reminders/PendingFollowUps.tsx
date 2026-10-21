"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { LIST_ITEM, LayoutMotion } from "@/components/ui/LayoutMotion";
import { m } from "@/components/ui/Motion";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { BookDrawer } from "@/features/appointments/BookDrawer";
import { useAppointmentApi, type Doctor } from "@/features/appointments/api";
import { clinicToday } from "@/features/patients/fields";
import { patientPath } from "@/features/patients/RegisterPatientDrawer";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatDay } from "@/lib/format/time";

import { PENDING_PAGE, useReminderApi, type PendingFollowUp } from "./api";
import { REMINDER_STATUS_LABELS } from "./labels";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly items: readonly PendingFollowUp[]; readonly more: boolean }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * Patients whose follow-up date passed without a completed visit since (FR-REM-07, R17; M5-P6
 * decision 4A), oldest first, 50 at a time. *Book follow-up* opens the booking drawer with the
 * patient and doctor chosen and today's date, so Confirm books it. A booked row says so; it
 * leaves the list once the visit is completed.
 */
export function PendingFollowUps() {
  const clinic = useClinic();
  const api = useReminderApi();
  const appointments = useAppointmentApi();
  const { clinic: choice, endSession } = useSession();
  const canBook = choice.kind === "active" && choice.membership.permissions.includes("APPOINTMENTS_MANAGE");
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [doctors, setDoctors] = useState<readonly Doctor[]>([]);
  const [attempt, setAttempt] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<unknown>(undefined);
  const [booking, setBooking] = useState<PendingFollowUp | undefined>(undefined);
  const [booked, setBooked] = useState<ReadonlyMap<string, string>>(new Map());
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.pending(0), appointments.doctors()]).then(
      ([items, ds]) => {
        if (cancelled) return;
        setLoad({ status: "ready", items, more: items.length === PENDING_PAGE });
        setDoctors(ds);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, appointments, attempt, endSession]);

  async function showMore(current: readonly PendingFollowUp[]) {
    setLoadingMore(true);
    setMoreError(undefined);
    try {
      const next = await api.pending(current.length);
      setLoad({ status: "ready", items: [...current, ...next], more: next.length === PENDING_PAGE });
    } catch (failure) {
      if (!endSession(failure)) setMoreError(failure);
    } finally {
      setLoadingMore(false);
    }
  }

  const names = new Map(doctors.map((d) => [d.id, d.display_name]));
  const active = doctors.filter((d) => d.is_active);
  const today = clinicToday(clinic.timezone);

  return (
    <section aria-labelledby="follow-ups-heading" className="space-y-4">
      <div>
        <h1 id="follow-ups-heading" className="text-2xl font-bold tracking-tight">
          Pending follow-ups
        </h1>
        <p className="text-slate-800">Patients whose follow-up date has passed without a visit since. Oldest first.</p>
      </div>
      <p role="status" className="min-h-6 font-medium text-emerald-900">
        {message}
      </p>

      {load.status === "loading" && (
        <p role="status" className="text-slate-700">
          Loading follow-ups…
        </p>
      )}
      {load.status === "failed" && (
        <div className="max-w-xl">
          <ErrorNotice
            error={load.error}
            onRetry={() => {
              setLoad({ status: "loading" });
              setAttempt((n) => n + 1);
            }}
          />
        </div>
      )}
      {load.status === "ready" && load.items.length === 0 && <EmptyState title="No follow-ups are overdue." />}
      {load.status === "ready" && load.items.length > 0 && (
        <LayoutMotion>
        <div className={TABLE_WRAP}>
          <table role="table" className={TABLE}>
            <caption className="sr-only">Pending follow-ups, oldest first</caption>
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader" scope="col" className={TH}>Patient</th>
                <th role="columnheader" scope="col" className={TH}>Follow-up was due</th>
                <th role="columnheader" scope="col" className={TH}>Doctor</th>
                <th role="columnheader" scope="col" className={TH}>Reminder</th>
                <th role="columnheader" scope="col" className={TH}>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {load.items.map((item) => (
                <m.tr {...LIST_ITEM} role="row" key={item.patient_id} className={TR}>
                  <th role="rowheader" scope="row" className={`${TD} font-medium`}>
                    <Link href={patientPath(item.patient_id)} className="text-brand-800 underline-offset-2 hover:underline">
                      {item.patient_name}
                    </Link>
                    <span className="block font-mono text-sm font-normal text-slate-700">{item.patient_code}</span>
                  </th>
                  <td role="cell" data-label="Follow-up was due" className={TD}>{formatDay(item.follow_up_date)}</td>
                  <td role="cell" data-label="Doctor" className={TD}>{names.get(item.doctor_id) ?? "–"}</td>
                  <td role="cell" data-label="Reminder" className={TD}>
                    {item.reminder_status === null ? "None" : REMINDER_STATUS_LABELS[item.reminder_status]}
                  </td>
                  <td role="cell" data-label="" className={TD}>
                    {booked.has(item.patient_id) ? (
                      <span className="font-medium text-emerald-900">{booked.get(item.patient_id)}</span>
                    ) : (
                      canBook &&
                      active.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setBooking(item)}
                          className="inline-flex min-h-8 items-center justify-center gap-2 rounded-lg bg-brand-700 px-3 py-1 text-sm font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
                        >
                          Book follow-up{" "}<span className="sr-only">for {item.patient_name}</span>
                        </button>
                      )
                    )}
                  </td>
                </m.tr>
              ))}
            </tbody>
          </table>
        </div>
        </LayoutMotion>
      )}
      {load.status === "ready" && load.more && (
        <div className="space-y-2">
          {moreError !== undefined && <ErrorNotice error={moreError} />}
          <button
            type="button"
            disabled={loadingMore}
            onClick={() => void showMore(load.items)}
            className="rounded-lg border border-slate-400 px-4 py-2 font-medium hover:bg-slate-100 disabled:text-slate-500"
          >
            {loadingMore ? "Loading…" : "Show more"}
          </button>
        </div>
      )}

      {booking !== undefined && (
        <BookDrawer
          target={{
            kind: "book",
            patient: { id: booking.patient_id, full_name: booking.patient_name, code: booking.patient_code },
          }}
          doctors={active}
          doctorId={active.some((d) => d.id === booking.doctor_id) ? booking.doctor_id : (active[0]?.id ?? booking.doctor_id)}
          date={today}
          onDone={(appointment, text) => {
            setBooked((m) => new Map(m).set(booking.patient_id, `Booked ${formatDay(appointment.on_date)}`));
            setBooking(undefined);
            setMessage(text);
          }}
          onClose={() => setBooking(undefined)}
        />
      )}
    </section>
  );
}

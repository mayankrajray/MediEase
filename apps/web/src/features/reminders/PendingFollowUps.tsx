"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

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
        <h1 id="follow-ups-heading" className="text-2xl font-bold">
          Pending follow-ups
        </h1>
        <p className="text-slate-800">Patients whose follow-up date has passed without a visit since. Oldest first.</p>
      </div>
      <p role="status" className="min-h-6 font-medium text-green-900">
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
      {load.status === "ready" && load.items.length === 0 && <p className="text-lg">No follow-ups are overdue.</p>}
      {load.status === "ready" && load.items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <caption className="sr-only">Pending follow-ups, oldest first</caption>
            <thead>
              <tr className="border-b border-slate-400">
                <th scope="col" className="py-2 pr-4">Patient</th>
                <th scope="col" className="py-2 pr-4">Follow-up was due</th>
                <th scope="col" className="py-2 pr-4">Doctor</th>
                <th scope="col" className="py-2 pr-4">Reminder</th>
                <th scope="col" className="py-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {load.items.map((item) => (
                <tr key={item.patient_id} className="border-b border-slate-200 align-top">
                  <th scope="row" className="py-2 pr-4 font-medium">
                    <Link href={patientPath(item.patient_id)} className="text-blue-900 underline">
                      {item.patient_name}
                    </Link>
                    <span className="block font-mono text-sm font-normal text-slate-700">{item.patient_code}</span>
                  </th>
                  <td className="py-2 pr-4">{formatDay(item.follow_up_date)}</td>
                  <td className="py-2 pr-4">{names.get(item.doctor_id) ?? "–"}</td>
                  <td className="py-2 pr-4">
                    {item.reminder_status === null ? "None" : REMINDER_STATUS_LABELS[item.reminder_status]}
                  </td>
                  <td className="py-2">
                    {booked.has(item.patient_id) ? (
                      <span className="font-medium text-green-900">{booked.get(item.patient_id)}</span>
                    ) : (
                      canBook &&
                      active.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setBooking(item)}
                          className="rounded bg-blue-800 px-3 py-1.5 font-semibold text-white hover:bg-blue-900"
                        >
                          Book follow-up{" "}<span className="sr-only">for {item.patient_name}</span>
                        </button>
                      )
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {load.status === "ready" && load.more && (
        <div className="space-y-2">
          {moreError !== undefined && <ErrorNotice error={moreError} />}
          <button
            type="button"
            disabled={loadingMore}
            onClick={() => void showMore(load.items)}
            className="rounded border border-slate-600 px-4 py-2 font-medium hover:bg-slate-100 disabled:text-slate-500"
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

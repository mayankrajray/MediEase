"use client";

import { StatusBadge } from "@/components/ui/StatusBadge";
import { TABLE, TD, TH, TR } from "@/components/ui/table";
import { useEffect, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatClock, formatDay } from "@/lib/format/time";
import { clinicToday, type Patient } from "@/features/patients/fields";

import { STATUS_LABELS, STATUS_TONES, placeText, useAppointmentApi, type Appointment, type Doctor } from "./api";
import { BookDrawer } from "./BookDrawer";

/** D32: the patient's appointments on their profile, newest first, with Book for them. */
export function PatientAppointments({ patient }: { patient: Patient }) {
  const clinic = useClinic();
  const api = useAppointmentApi();
  const { clinic: choice, endSession } = useSession();
  const canManage = choice.kind === "active" && choice.membership.permissions.includes("APPOINTMENTS_MANAGE");
  const [items, setItems] = useState<readonly Appointment[] | undefined>(undefined);
  const [doctors, setDoctors] = useState<readonly Doctor[]>([]);
  const [error, setError] = useState<unknown>(undefined);
  const [booking, setBooking] = useState(false);
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.patientAppointments(patient.id), api.doctors()]).then(
      ([found, ds]) => {
        if (cancelled) return;
        setItems(found);
        setDoctors(ds);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, patient.id, reload, endSession]);

  const names = new Map(doctors.map((d) => [d.id, d.display_name]));
  const active = doctors.filter((d) => d.is_active);
  const clock = (iso: string) => formatClock(iso, clinic.timezone);

  return (
    <section aria-labelledby="appointments-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
      <div className="flex items-center justify-between gap-2">
        <h2 id="appointments-heading" className="text-lg font-bold">
          Appointments
        </h2>
        {canManage && active[0] !== undefined && (
          <button
            type="button"
            onClick={() => setBooking(true)}
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
          >
            Book for {patient.full_name}
          </button>
        )}
      </div>
      <p role="status" className="min-h-6 font-medium text-emerald-900">
        {message}
      </p>
      {error !== undefined && <ErrorNotice error={error} />}
      {items === undefined && error === undefined && <p className="text-slate-700">Loading appointments…</p>}
      {items !== undefined && items.length === 0 && <p className="text-slate-700">No appointments yet.</p>}
      {items !== undefined && items.length > 0 && (
        <table role="table" className={TABLE}>
          <thead role="rowgroup">
            <tr role="row">
              <th role="columnheader" scope="col" className={TH}>Date</th>
              <th role="columnheader" scope="col" className={TH}>Doctor</th>
              <th role="columnheader" scope="col" className={TH}>Place</th>
              <th role="columnheader" scope="col" className={TH}>Status</th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {items.map((a) => (
              <tr role="row" key={a.id} className={TR}>
                <td role="cell" data-label="Date" className={TD}>{formatDay(a.on_date)}</td>
                <td role="cell" data-label="Doctor" className={TD}>{names.get(a.doctor_id) ?? "–"}</td>
                <td role="cell" data-label="Place" className={TD}>{placeText(a, clock)}</td>
                <td role="cell" data-label="Status" className={TD}><StatusBadge tone={STATUS_TONES[a.status]}>{STATUS_LABELS[a.status]}</StatusBadge></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {booking && active[0] !== undefined && (
        <BookDrawer
          target={{ kind: "book", patient }}
          doctors={active}
          doctorId={active[0].id}
          date={clinicToday(clinic.timezone)}
          onDone={(_a, text) => {
            setBooking(false);
            setMessage(text);
            setReload((n) => n + 1);
          }}
          onClose={() => setBooking(false)}
        />
      )}
    </section>
  );
}

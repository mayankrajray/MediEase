"use client";

import { useEffect, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatClock, formatDay } from "@/lib/format/time";
import { clinicToday, type Patient } from "@/features/patients/fields";

import { STATUS_LABELS, placeText, useAppointmentApi, type Appointment, type Doctor } from "./api";
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
    <section aria-labelledby="appointments-heading" className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h2 id="appointments-heading" className="text-lg font-bold">
          Appointments
        </h2>
        {canManage && active[0] !== undefined && (
          <button
            type="button"
            onClick={() => setBooking(true)}
            className="rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900"
          >
            Book for {patient.full_name}
          </button>
        )}
      </div>
      <p role="status" className="min-h-6 font-medium text-green-900">
        {message}
      </p>
      {error !== undefined && <ErrorNotice error={error} />}
      {items === undefined && error === undefined && <p className="text-slate-700">Loading appointments…</p>}
      {items !== undefined && items.length === 0 && <p className="text-slate-700">No appointments yet.</p>}
      {items !== undefined && items.length > 0 && (
        <table className="w-full text-left">
          <thead className="text-sm text-slate-700">
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Doctor</th>
              <th scope="col">Place</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id} className="border-t border-slate-200">
                <td className="py-2">{formatDay(a.on_date)}</td>
                <td>{names.get(a.doctor_id) ?? "–"}</td>
                <td>{placeText(a, clock)}</td>
                <td>{STATUS_LABELS[a.status]}</td>
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

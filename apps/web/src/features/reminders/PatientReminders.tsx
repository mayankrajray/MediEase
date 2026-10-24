"use client";

import { useEffect, useId, useState } from "react";

import { LIST_ITEM, LayoutMotion } from "@/components/ui/LayoutMotion";
import { m } from "@/components/ui/Motion";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useAppointmentApi, type Doctor } from "@/features/appointments/api";
import { clinicToday, type Patient } from "@/features/patients/fields";
import { useClinic } from "@/features/shell/ClinicGate";
import { addDays, formatDay } from "@/lib/format/time";
import { formatPhone } from "@/lib/format/phone";

import { useReminderApi, type Reminder } from "./api";
import { shouldCall } from "./labels";
import { ReminderChip } from "./ReminderChip";

const SOURCE_LABELS: Record<Reminder["source"], string> = {
  PRESCRIPTION: "From a prescription",
  MANUAL: "Added by staff",
  APPOINTMENT: "Before a booked visit",
};

/**
 * The patient's follow-up reminders on the profile (M5-P6 decision 3A; FR-REM-02, 05; R16):
 * status, follow-up date, due time and where it came from. A scheduled one can be moved or
 * cancelled, and staff can add one with a doctor and a date (due 09:00 the day before). A
 * failed one says why and offers a call.
 */
export function PatientReminders({ patient }: Readonly<{ patient: Patient }>) {
  const clinic = useClinic();
  const api = useReminderApi();
  const appointments = useAppointmentApi();
  const { endSession } = useSession();
  const [items, setItems] = useState<readonly Reminder[] | undefined>(undefined);
  const [doctors, setDoctors] = useState<readonly Doctor[]>([]);
  const [loadError, setLoadError] = useState<unknown>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [message, setMessage] = useState("");
  const [adding, setAdding] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.list(patient.id), appointments.doctors()]).then(
      ([found, ds]) => {
        if (cancelled) return;
        setItems(found);
        setDoctors(ds);
        setLoadError(undefined);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoadError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, appointments, patient.id, reload, endSession]);

  const active = doctors.filter((d) => d.is_active);
  const names = new Map(doctors.map((d) => [d.id, d.display_name]));
  const tomorrow = addDays(clinicToday(clinic.timezone), 1);

  async function run(action: () => Promise<Reminder>, done: string) {
    setError(undefined);
    try {
      await action();
      setMessage(done);
      setAdding(false);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setReload((n) => n + 1); // show it as it is now, also after a refusal
    }
  }

  return (
    <section aria-labelledby="reminders-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
      <div className="flex items-center justify-between gap-2">
        <h2 id="reminders-heading" className="text-lg font-bold">
          Reminders
        </h2>
        {!adding && active[0] !== undefined && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="inline-flex min-h-8 items-center justify-center gap-2 rounded-lg border border-slate-400 bg-white px-3 py-1 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500 motion-reduce:transition-none"
          >
            Add follow-up reminder
          </button>
        )}
      </div>
      <p role="status" className="min-h-6 font-medium text-emerald-900">
        {message}
      </p>
      {error !== undefined && <ErrorNotice error={error} />}
      {adding && active[0] !== undefined && (
        <AddReminder
          doctors={active}
          min={tomorrow}
          onCancel={() => setAdding(false)}
          onAdd={(doctorId, date) =>
            void run(() => api.schedule(patient.id, doctorId, date), `Reminder added for the follow-up on ${formatDay(date)}.`)
          }
        />
      )}
      {loadError !== undefined && <ErrorNotice error={loadError} onRetry={() => setReload((n) => n + 1)} />}
      {items === undefined && loadError === undefined && <p className="text-slate-700">Loading reminders…</p>}
      {items !== undefined && items.length === 0 && <p className="text-slate-700">No reminders.</p>}
      {items !== undefined && items.length > 0 && (
        <LayoutMotion>
        <ul className="space-y-3">
          {items.map((r) => (
            <ReminderRow
              key={`${r.id}-${r.revision}`}
              reminder={r}
              doctorName={names.get(r.doctor_id)}
              phone={patient.phone_e164}
              timeZone={clinic.timezone}
              min={tomorrow}
              onMove={(date) => void run(() => api.move(r.id, date), `Reminder moved to the follow-up on ${formatDay(date)}.`)}
              onCancel={() => void run(() => api.cancel(r.id), "Reminder cancelled.")}
            />
          ))}
        </ul>
        </LayoutMotion>
      )}
    </section>
  );
}

function ReminderRow({
  reminder,
  doctorName,
  phone,
  timeZone,
  min,
  onMove,
  onCancel,
}: Readonly<{
  reminder: Reminder;
  doctorName: string | undefined;
  phone: string;
  timeZone: string;
  min: string;
  onMove: (date: string) => void;
  onCancel: () => void;
}>) {
  const [moving, setMoving] = useState(false);
  const [date, setDate] = useState(reminder.follow_up_date);
  const id = useId();
  const scheduled = reminder.status === "SCHEDULED";
  // M6a-P8: an appointment reminder follows its appointment: move the appointment, not this.
  const visit = reminder.kind === "APPOINTMENT";

  return (
    <m.li {...LIST_ITEM} className="space-y-2 rounded-card border border-slate-200 bg-white p-3">
      <ReminderChip reminder={reminder} timeZone={timeZone} />
      <p className="text-slate-800">
        {visit ? "Visit on" : "Follow-up on"} {formatDay(reminder.follow_up_date)}
        {doctorName !== undefined && ` with ${doctorName}`} · {SOURCE_LABELS[reminder.source]}
      </p>
      {shouldCall(reminder.status) && (
        <p>
          <a href={`tel:${phone}`} className="font-medium text-brand-800 underline">
            Call patient{" "}<span className="sr-only">on {formatPhone(phone)}</span>
          </a>
        </p>
      )}
      {scheduled && !moving && (
        <div className="flex flex-wrap gap-2">
          {!visit && (
            <button type="button" onClick={() => setMoving(true)} className="rounded-lg border border-slate-400 px-3 py-1 hover:bg-slate-100">
              Move
            </button>
          )}
          <button type="button" onClick={onCancel} className="inline-flex min-h-8 items-center rounded-lg border border-red-700 bg-white px-3 py-1 text-sm font-medium text-red-900 hover:bg-red-50">
            Cancel reminder
          </button>
        </div>
      )}
      {scheduled && moving && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setMoving(false);
            onMove(date);
          }}
        >
          <div>
            <label htmlFor={id} className="block font-medium">
              New follow-up date
            </label>
            <input
              id={id}
              type="date"
              required
              min={min}
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="rounded-lg border border-slate-400 px-2 py-1"
            />
          </div>
          <button type="submit" className="inline-flex min-h-8 items-center justify-center gap-2 rounded-lg bg-brand-700 px-3 py-1 text-sm font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none">
            Save
          </button>
          <button type="button" onClick={() => setMoving(false)} className="rounded-lg border border-slate-400 px-3 py-1.5">
            Keep it
          </button>
        </form>
      )}
    </m.li>
  );
}

function AddReminder({
  doctors,
  min,
  onAdd,
  onCancel,
}: Readonly<{
  doctors: readonly Doctor[];
  min: string;
  onAdd: (doctorId: string, date: string) => void;
  onCancel: () => void;
}>) {
  const [doctorId, setDoctorId] = useState(doctors[0]?.id ?? "");
  const [date, setDate] = useState(min);
  const ids = { doctor: useId(), date: useId() };

  return (
    <form
      aria-label="Add follow-up reminder"
      className="flex flex-wrap items-end gap-3 rounded-card border border-slate-200 bg-white p-3"
      onSubmit={(event) => {
        event.preventDefault();
        onAdd(doctorId, date);
      }}
    >
      <div>
        <label htmlFor={ids.doctor} className="block font-medium">
          Doctor
        </label>
        <select
          id={ids.doctor}
          value={doctorId}
          onChange={(event) => setDoctorId(event.target.value)}
          className="rounded-lg border border-slate-400 px-2 py-1.5"
        >
          {doctors.map((d) => (
            <option key={d.id} value={d.id}>
              {d.display_name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor={ids.date} className="block font-medium">
          Follow-up date
        </label>
        <input
          id={ids.date}
          type="date"
          required
          min={min}
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="rounded-lg border border-slate-400 px-2 py-1"
        />
      </div>
      <p className="w-full text-sm text-slate-700">Sent on WhatsApp at 09:00 the day before, if the patient agreed to messages.</p>
      <button type="submit" className="inline-flex min-h-8 items-center justify-center gap-2 rounded-lg bg-brand-700 px-3 py-1 text-sm font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none">
        Add reminder
      </button>
      <button type="button" onClick={onCancel} className="rounded-lg border border-slate-400 px-3 py-1.5">
        Cancel
      </button>
    </form>
  );
}

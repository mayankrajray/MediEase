"use client";

import { useEffect, useId, useState } from "react";

import { Drawer } from "@/components/Drawer";
import { useNow } from "@/components/useNow";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import type { Patient } from "@/features/patients/fields";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatClock, formatDay } from "@/lib/format/time";

import { useAppointmentApi, type Appointment, type Doctor, type DoctorSession } from "./api";
import { PatientPicker } from "./PatientPicker";

/** Who is being booked: a patient (new booking) or an existing appointment (reschedule). */
export type BookingTarget =
  | { readonly kind: "book"; readonly patient?: Pick<Patient, "id" | "full_name" | "code"> }
  | {
      readonly kind: "reschedule";
      readonly appointment: Appointment;
      readonly patientName: string;
    };

type Choice = { readonly sessionId: string; readonly slotStart?: string };

function bookable(session: DoctorSession, now: number): boolean {
  return session.status === "OPEN" && new Date(session.ends_at).getTime() > now && session.available > 0;
}

function freeSlots(session: DoctorSession, now: number) {
  return session.slots.filter((s) => s.available !== false && new Date(s.ends_at).getTime() > now);
}

/** The first place to offer: the earliest open session with room, and its earliest free slot. */
export function preselect(sessions: readonly DoctorSession[], now: number): Choice | undefined {
  for (const session of sessions) {
    if (!bookable(session, now)) continue;
    if (session.mode === "TOKENS") return { sessionId: session.id };
    const slot = freeSlots(session, now)[0];
    if (slot !== undefined) return { sessionId: session.id, slotStart: slot.starts_at };
  }
  return undefined;
}

/**
 * Book (or reschedule) in at most three interactions from the board (FR-APT-03, AC6): the patient
 * search is focused → pick the patient → the earliest free slot or the next token is already
 * chosen → Confirm. Any other session or slot of the day, and another date or doctor, can be
 * picked too. A place taken meanwhile (409) reloads the day and says so.
 */
export function BookDrawer({
  target,
  doctors,
  doctorId: initialDoctor,
  date: initialDate,
  onDone,
  onClose,
}: {
  target: BookingTarget;
  doctors: readonly Doctor[];
  doctorId: string;
  date: string;
  onDone: (appointment: Appointment, message: string) => void;
  onClose: () => void;
}) {
  const clinic = useClinic();
  const api = useAppointmentApi();
  const { endSession } = useSession();
  const clock = (iso: string) => formatClock(iso, clinic.timezone);
  const now = useNow();
  const [patient, setPatient] = useState(target.kind === "book" ? target.patient : undefined);
  const [doctorId, setDoctorId] = useState(initialDoctor);
  const [date, setDate] = useState(initialDate);
  const [reload, setReload] = useState(0);
  const [sessions, setSessions] = useState<{ key: string; items: readonly DoctorSession[] } | null>(null);
  const [loadError, setLoadError] = useState<unknown>(undefined);
  const [choice, setChoice] = useState<Choice | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const ids = { doctor: useId(), date: useId() };
  const key = `${doctorId}|${date}|${reload}`;

  useEffect(() => {
    let cancelled = false;
    api.sessions(date, doctorId).then(
      (items) => {
        if (cancelled) return;
        setSessions({ key, items });
        setLoadError(undefined);
        setChoice(preselect(items, Date.now()));
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoadError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, date, doctorId, key, endSession]);

  const day = sessions !== null && sessions.key === key ? sessions.items : null;
  const who = target.kind === "reschedule" ? target.patientName : patient?.full_name;
  const chosen = day?.find((s) => s.id === choice?.sessionId);

  async function confirm() {
    if (choice === undefined || (target.kind === "book" && patient === undefined)) return;
    setSaving(true);
    setError(undefined);
    try {
      const done =
        target.kind === "book"
          ? await api.book({
              session_id: choice.sessionId,
              patient_id: patient?.id ?? "",
              source: "FRONT_DESK",
              ...(choice.slotStart === undefined ? {} : { slot_start: choice.slotStart }),
            })
          : await api.reschedule(target.appointment.id, choice.sessionId, choice.slotStart);
      const place = done.token_number !== null ? `token ${done.token_number}` : clock(done.slot_start ?? "");
      const verb = target.kind === "book" ? "booked" : "moved";
      onDone(done, `${who ?? "Patient"} ${verb}: ${formatDay(done.on_date)}, ${place}.`);
    } catch (failure) {
      if (endSession(failure)) return;
      setError(failure);
      setReload((n) => n + 1); // someone may have taken the place: show the day as it is now
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer title={target.kind === "book" ? "Book appointment" : `Reschedule ${target.patientName}`} onClose={onClose}>
      {target.kind === "book" && patient === undefined ? (
        <PatientPicker onPick={setPatient} />
      ) : (
        <p className="flex items-center justify-between gap-2 rounded bg-slate-100 px-3 py-2">
          <span>
            <span className="font-semibold">{who}</span>
            {patient !== undefined && <span className="text-sm text-slate-700"> · {patient.code}</span>}
          </span>
          {target.kind === "book" && (
            <button type="button" onClick={() => setPatient(undefined)} className="text-brand-800 underline">
              Change patient
            </button>
          )}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor={ids.doctor} className="block font-medium">
            Doctor
          </label>
          <select
            id={ids.doctor}
            value={doctorId}
            onChange={(event) => setDoctorId(event.target.value)}
            className="w-full rounded-lg border border-slate-400 px-2 py-2"
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
            Date
          </label>
          <input
            id={ids.date}
            type="date"
            value={date}
            onChange={(event) => event.target.value !== "" && setDate(event.target.value)}
            className="w-full rounded-lg border border-slate-400 px-2 py-2"
          />
        </div>
      </div>

      {loadError !== undefined && <ErrorNotice error={loadError} onRetry={() => setReload((n) => n + 1)} />}
      {day === null && loadError === undefined && (
        <p role="status" className="text-slate-700">
          Loading sessions…
        </p>
      )}
      {day !== null && day.length === 0 && <p role="status">The doctor has no sessions on {formatDay(date)}.</p>}
      {day !== null && day.length > 0 && (
        <fieldset className="space-y-3">
          <legend className="font-medium">When</legend>
          {day.map((session) => {
            const open = bookable(session, now);
            const label = `${clock(session.starts_at)}–${clock(session.ends_at)}`;
            if (session.mode === "TOKENS") {
              return (
                <label key={session.id} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="place"
                    disabled={!open}
                    checked={choice?.sessionId === session.id}
                    onChange={() => setChoice({ sessionId: session.id })}
                  />
                  <span>
                    {label} · {open ? `next token ${session.next_token ?? ""}, ${session.available} left` : "not taking bookings"}
                  </span>
                </label>
              );
            }
            const slots = freeSlots(session, now);
            return (
              <div key={session.id} className="space-y-1">
                <p className="text-sm font-medium text-slate-800">
                  {label}
                  {!open && " · not taking bookings"}
                </p>
                <div className="flex flex-wrap gap-2">
                  {open &&
                    slots.map((slot) => (
                      <label
                        key={slot.starts_at}
                        className="flex items-center gap-1 rounded-lg border border-slate-300 px-2 py-1 has-[:checked]:border-brand-700 has-[:checked]:bg-brand-50"
                      >
                        <input
                          type="radio"
                          name="place"
                          checked={choice?.slotStart === slot.starts_at}
                          onChange={() => setChoice({ sessionId: session.id, slotStart: slot.starts_at })}
                        />
                        {clock(slot.starts_at)}
                      </label>
                    ))}
                  {open && slots.length === 0 && <span className="text-slate-700">No free slots</span>}
                </div>
              </div>
            );
          })}
        </fieldset>
      )}

      {error !== undefined && <ErrorNotice error={error} />}
      <button
        type="button"
        disabled={saving || choice === undefined || chosen === undefined || (target.kind === "book" && patient === undefined)}
        onClick={() => void confirm()}
        className="w-full rounded bg-brand-700 px-4 py-2 font-semibold text-white hover:bg-brand-800 disabled:bg-slate-400"
      >
        {saving ? "Saving…" : target.kind === "book" ? "Confirm booking" : "Confirm new time"}
      </button>
    </Drawer>
  );
}

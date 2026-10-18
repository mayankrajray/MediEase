"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { Dialog } from "@/components/Dialog";
import { useNow } from "@/components/useNow";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { BookDrawer, type BookingTarget } from "@/features/appointments/BookDrawer";
import { CancelDialog } from "@/features/appointments/CancelDialog";
import { PatientPicker } from "@/features/appointments/PatientPicker";
import {
  STATUS_LABELS,
  placeText,
  useAppointmentApi,
  type AppointmentStatus,
  type Doctor,
} from "@/features/appointments/api";
import { clinicToday } from "@/features/patients/fields";
import { useRxApi } from "@/features/prescriptions/api";
import { usePrint } from "@/features/prescriptions/PrintAndLink";
import { visitPath } from "@/features/visits/paths";
import { useClinic } from "@/features/shell/ClinicGate";
import { ApiError } from "@/lib/api/client";
import { addDays, formatClock, formatDay } from "@/lib/format/time";

import { QueueRow, type QueueEntry } from "./QueueRow";
import { useQueue } from "./useQueue";

export const QUE_INVALID_TRANSITION = "QUE_INVALID_TRANSITION";
export const VIS_ALREADY_EXISTS = "VIS_ALREADY_EXISTS";
const STORAGE_PREFIX = "mediease.queue.doctor.";

/** D27: a doctor sees their own day; others the doctor last chosen here, else the first active. */
export function initialDoctor(doctors: readonly Doctor[], userId: string, remembered: string | null): string | undefined {
  const active = doctors.filter((d) => d.is_active);
  return (
    active.find((d) => d.user_id === userId)?.id ??
    active.find((d) => d.id === remembered)?.id ??
    active[0]?.id
  );
}

type Overlay =
  | { readonly kind: "book"; readonly target: BookingTarget }
  | { readonly kind: "cancel"; readonly entry: QueueEntry }
  | { readonly kind: "no-show"; readonly entry: QueueEntry }
  | { readonly kind: "walk-in" };

/**
 * The live queue board (FR-QUE-01, FR-QUE-03, M3-P5): one doctor's day, refreshed every 5 s.
 * Every action sends the status the row showed (D18); when another screen moved first the row
 * refreshes and says so. Each action is reported in a status message naming the patient and the
 * time, so a slip is seen at once (the safeguard for single-click steps, D29).
 */
export function QueueBoard() {
  const clinic = useClinic();
  const { identity, clinic: choice, endSession } = useSession();
  const api = useAppointmentApi();
  const permissions = choice.kind === "active" ? choice.membership.permissions : [];
  const canMove = permissions.includes("QUEUE_MOVE");
  const canManage = permissions.includes("APPOINTMENTS_MANAGE");
  const canWriteClinical = permissions.includes("CLINICAL_WRITE");
  const canPrint = permissions.includes("RX_PRINT");
  const router = useRouter();
  const rxApi = useRxApi();
  const printer = usePrint();
  const now = useNow();
  const today = clinicToday(clinic.timezone, new Date(now));
  const storageKey = `${STORAGE_PREFIX}${clinic.id}`;

  const [doctors, setDoctors] = useState<readonly Doctor[] | undefined>(undefined);
  const [doctorsError, setDoctorsError] = useState<unknown>(undefined);
  const [doctorId, setDoctorId] = useState<string | undefined>(undefined);
  const [date, setDate] = useState(today);
  const [overlay, setOverlay] = useState<Overlay | undefined>(undefined);
  const [message, setMessage] = useState("");
  const [actionError, setActionError] = useState<unknown>(undefined);
  const [busy, setBusy] = useState(false);
  const pickerId = useId();
  const dateId = useId();

  useEffect(() => {
    let cancelled = false;
    api.doctors().then(
      (items) => {
        if (cancelled) return;
        setDoctors(items);
        setDoctorId(initialDoctor(items, identity.user.id, window.localStorage.getItem(storageKey)));
      },
      (error: unknown) => {
        if (!cancelled && !endSession(error)) setDoctorsError(error);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, identity.user.id, storageKey, endSession]);

  const { queue, error, refresh } = useQueue({
    date,
    ...(doctorId === undefined ? {} : { doctorId }),
    ...(api.clinicId === undefined ? {} : { clinicId: api.clinicId }),
  });
  const clock = (iso: string) => formatClock(iso, clinic.timezone);
  const at = () => clock(new Date().toISOString());

  function chooseDoctor(id: string) {
    setDoctorId(id);
    window.localStorage.setItem(storageKey, id);
  }

  function done(text: string) {
    setOverlay(undefined);
    setActionError(undefined);
    setMessage(text);
    refresh();
  }

  // M4-P6: the rows of the signed-in doctor's own profile open the consultation screen.
  const myDoctorIds = new Set((doctors ?? []).filter((d) => d.user_id === identity.user.id).map((d) => d.id));
  const isMine = (entry: QueueEntry) => canWriteClinical && myDoctorIds.has(entry.doctor_id);

  /** Opens the entry's visit, starting it first when there is none yet (a second start reopens it). */
  async function open(entry: QueueEntry) {
    if (entry.visit_id !== null) {
      router.push(visitPath(entry.visit_id));
      return;
    }
    try {
      const visit = await rxApi.startVisit(entry.id);
      router.push(visitPath(visit.id));
    } catch (failure) {
      const existing = failure instanceof ApiError && failure.code === VIS_ALREADY_EXISTS ? failure.details["visit_id"] : undefined;
      if (typeof existing === "string") {
        router.push(visitPath(existing));
        return;
      }
      throw failure;
    }
  }

  async function openFromRow(entry: QueueEntry) {
    setBusy(true);
    setActionError(undefined);
    try {
      await open(entry);
    } catch (failure) {
      if (!endSession(failure)) setActionError(failure);
    } finally {
      setBusy(false);
    }
  }

  async function step(entry: QueueEntry, to: AppointmentStatus) {
    const who = entry.patient.full_name;
    setBusy(true);
    setActionError(undefined);
    try {
      await api.transition(entry.id, entry.status, to);
      if (to === "IN_CONSULTATION" && isMine(entry)) {
        // The doctor's own Start goes straight to the consultation (journey step 1).
        try {
          await open({ ...entry, status: to });
        } catch (failure) {
          refresh(); // the row has moved even though the visit could not be opened
          throw failure;
        }
        return;
      }
      done(`${who} marked ${STATUS_LABELS[to].toLowerCase()} at ${at()}.`);
    } catch (failure) {
      if (endSession(failure)) return;
      if (failure instanceof ApiError && failure.code === QUE_INVALID_TRANSITION) {
        const real = failure.details["from"];
        const now = typeof real === "string" && real in STATUS_LABELS ? STATUS_LABELS[real as AppointmentStatus] : "changed";
        setMessage(`Someone else already updated ${who}: now ${now.toLowerCase()}. The queue has been refreshed.`);
        refresh();
      } else {
        setActionError(failure);
      }
    } finally {
      setBusy(false);
      setOverlay(undefined);
    }
  }

  const sessions = queue?.sessions ?? [];
  const isToday = date === today;

  return (
    <section aria-labelledby="queue-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 id="queue-heading" className="text-2xl font-bold">
            {isToday ? "Today's queue" : `Queue for ${formatDay(date)}`}
          </h1>
          <p className="text-slate-700">{formatDay(date)}</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          {doctors !== undefined && doctors.filter((d) => d.is_active).length > 1 && (
            <div>
              <label htmlFor={pickerId} className="block text-sm font-medium">
                Doctor
              </label>
              <select
                id={pickerId}
                value={doctorId ?? ""}
                onChange={(event) => chooseDoctor(event.target.value)}
                className="rounded border border-slate-500 px-2 py-2"
              >
                {doctors
                  .filter((d) => d.is_active)
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.display_name}
                    </option>
                  ))}
              </select>
            </div>
          )}
          <nav aria-label="Day" className="flex items-end gap-1">
            <button type="button" onClick={() => setDate(addDays(date, -1))} className="rounded border border-slate-500 px-3 py-2">
              Previous day
            </button>
            <div>
              <label htmlFor={dateId} className="block text-sm font-medium">
                Date
              </label>
              <input
                id={dateId}
                type="date"
                value={date}
                onChange={(event) => event.target.value !== "" && setDate(event.target.value)}
                className="rounded border border-slate-500 px-2 py-1.5"
              />
            </div>
            <button type="button" onClick={() => setDate(addDays(date, 1))} className="rounded border border-slate-500 px-3 py-2">
              Next day
            </button>
            {!isToday && (
              <button type="button" onClick={() => setDate(today)} className="rounded border border-slate-500 px-3 py-2">
                Today
              </button>
            )}
          </nav>
          {canManage && doctorId !== undefined && (
            <button
              type="button"
              onClick={() => setOverlay({ kind: "book", target: { kind: "book" } })}
              className="rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900"
            >
              Book
            </button>
          )}
          {canMove && isToday && doctorId !== undefined && (
            <button
              type="button"
              onClick={() => setOverlay({ kind: "walk-in" })}
              className="rounded border border-blue-800 px-4 py-2 font-semibold text-blue-900 hover:bg-blue-50"
            >
              Add walk-in
            </button>
          )}
        </div>
      </div>

      <p role="status" aria-live="polite" className="min-h-6 font-medium text-green-900">
        {message}
      </p>
      {actionError !== undefined && <ErrorNotice error={actionError} />}
      {printer.error !== undefined && <ErrorNotice error={printer.error} />}
      {printer.printing && <p role="status">Preparing the prescription…</p>}
      {doctorsError !== undefined && <ErrorNotice error={doctorsError} />}
      {error !== undefined && (
        <ErrorNotice
          error={error}
          {...(queue === undefined ? {} : { message: "The queue could not be refreshed; it will try again." })}
        />
      )}

      {doctors !== undefined && doctorId === undefined && <p>No active doctors yet. Ask the clinic owner to add one.</p>}
      {doctorId !== undefined && queue === undefined && error === undefined && (
        <p role="status" className="text-slate-700">
          Loading the queue…
        </p>
      )}
      {queue !== undefined && sessions.length === 0 && (
        <p>No sessions for this doctor on {formatDay(date)}.</p>
      )}

      {sessions.map((session) => {
        const sessionDay =
          session.on_date === today ||
          (now >= new Date(session.starts_at).getTime() && now < new Date(session.ends_at).getTime());
        const rows = session.appointments;
        return (
          <section key={session.id} aria-label={`Session ${clock(session.starts_at)} to ${clock(session.ends_at)}`} className="rounded border border-slate-300">
            <h2 className="flex flex-wrap items-baseline justify-between gap-2 border-b border-slate-300 bg-slate-50 px-4 py-2">
              <span className="font-bold">
                {clock(session.starts_at)}–{clock(session.ends_at)}
              </span>
              <span className="text-sm text-slate-800">
                {session.mode === "TOKENS" ? "Tokens" : `${session.slot_minutes ?? ""}-minute slots`} · {session.booked_count} of {session.capacity} booked
                {session.status === "CLOSED" && " · closed to new bookings"}
              </span>
            </h2>
            {rows.length === 0 ? (
              <p className="px-4 py-3 text-slate-700">Nobody booked yet.</p>
            ) : (
              <table className="w-full px-4">
                <caption className="sr-only">Appointments in this session</caption>
                <thead className="text-left text-sm text-slate-700">
                  <tr>
                    <th scope="col" className="px-4 py-2">Place</th>
                    <th scope="col" className="py-2">Patient</th>
                    <th scope="col" className="py-2">Status</th>
                    <th scope="col" className="py-2">Waiting</th>
                    <th scope="col" className="py-2 pr-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="[&_td:first-child]:px-4 [&_td:last-child]:pr-4">
                  {rows.map((entry) => (
                    <QueueRow
                      key={entry.id}
                      entry={entry}
                      session={session}
                      actions={{
                        canMove: canMove && sessionDay,
                        canManage,
                        busy,
                        onStep: (e, to) => void step(e, to),
                        onNoShow: (e) => setOverlay({ kind: "no-show", entry: e }),
                        onCancel: (e) => setOverlay({ kind: "cancel", entry: e }),
                        onReschedule: (e) =>
                          setOverlay({
                            kind: "book",
                            target: { kind: "reschedule", appointment: e, patientName: e.patient.full_name },
                          }),
                        isMine,
                        onOpen: (e) => void openFromRow(e),
                        canPrint,
                        onPrint: printer.print,
                      }}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </section>
        );
      })}

      {overlay?.kind === "book" && doctors !== undefined && doctorId !== undefined && (
        <BookDrawer
          target={overlay.target}
          doctors={doctors.filter((d) => d.is_active)}
          doctorId={doctorId}
          date={date < today ? today : date}
          onDone={(_a, text) => done(text)}
          onClose={() => setOverlay(undefined)}
        />
      )}
      {overlay?.kind === "cancel" && (
        <CancelDialog
          appointmentId={overlay.entry.id}
          patientName={overlay.entry.patient.full_name}
          onDone={(_a, text) => done(text)}
          onClose={() => setOverlay(undefined)}
        />
      )}
      {overlay?.kind === "no-show" && (
        <Dialog title={`Mark ${overlay.entry.patient.full_name} as a no-show?`} onClose={() => setOverlay(undefined)}>
          <p>
            {placeText(overlay.entry, clock)} · booked for {clock(overlay.entry.slot_start ?? overlay.entry.session_starts_at)}. If they
            arrive later today you can still mark them arrived.
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setOverlay(undefined)} className="rounded border border-slate-500 px-4 py-2">
              Go back
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void step(overlay.entry, "NO_SHOW")}
              className="rounded bg-red-800 px-4 py-2 font-semibold text-white disabled:bg-slate-400"
            >
              Mark no-show
            </button>
          </div>
        </Dialog>
      )}
      {overlay?.kind === "walk-in" && doctorId !== undefined && (
        <WalkInDialog doctorId={doctorId} onDone={done} onClose={() => setOverlay(undefined)} />
      )}
    </section>
  );
}

/** D30: today's walk-in in one pick; the API chooses the session and place (D21). */
function WalkInDialog({ doctorId, onDone, onClose }: { doctorId: string; onDone: (text: string) => void; onClose: () => void }) {
  const clinic = useClinic();
  const api = useAppointmentApi();
  const { endSession } = useSession();
  const [error, setError] = useState<unknown>(undefined);
  const [saving, setSaving] = useState(false);

  return (
    <Dialog title="Add walk-in" onClose={onClose}>
      <PatientPicker
        onPick={(patient) => {
          if (saving) return;
          setSaving(true);
          setError(undefined);
          api.walkIn(doctorId, patient.id).then(
            (a) => onDone(`${patient.full_name} added as a walk-in: ${placeText(a, (iso) => formatClock(iso, clinic.timezone)).toLowerCase()}, arrived.`),
            (failure: unknown) => {
              setSaving(false);
              if (!endSession(failure)) setError(failure);
            },
          );
        }}
      />
      {saving && error === undefined && <p role="status">Adding…</p>}
      {error !== undefined && <ErrorNotice error={error} />}
      <div className="flex justify-end">
        <button type="button" onClick={onClose} className="rounded border border-slate-500 px-4 py-2">
          Close
        </button>
      </div>
    </Dialog>
  );
}

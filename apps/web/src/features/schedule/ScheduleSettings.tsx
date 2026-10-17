"use client";

import { useEffect, useId, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import {
  useAppointmentApi,
  type BookingMode,
  type Doctor,
  type DoctorSession,
  type Schedule,
  type ScheduleBlockInput,
} from "@/features/appointments/api";
import { clinicToday } from "@/features/patients/fields";
import { useClinic } from "@/features/shell/ClinicGate";
import { ApiError } from "@/lib/api/client";
import { formatClock, formatDay } from "@/lib/format/time";

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;

/** A block as the form edits it: every field text, so a half-typed value is never lost. */
interface Draft {
  readonly key: string;
  readonly weekday: string;
  readonly start: string;
  readonly end: string;
  readonly slot: string;
  readonly capacity: string;
}

let counter = 0;
const newKey = () => `b${(counter += 1)}`;

function draftsOf(schedule: Schedule): Draft[] {
  return schedule.blocks.map((b) => ({
    key: newKey(),
    weekday: String(b.weekday),
    start: b.start_time,
    end: b.end_time,
    slot: b.slot_minutes === null ? "" : String(b.slot_minutes),
    capacity: b.capacity === null ? "" : String(b.capacity),
  }));
}

export function blocksOf(drafts: readonly Draft[]): ScheduleBlockInput[] {
  return drafts.map((d) => ({
    weekday: Number(d.weekday),
    start_time: d.start,
    end_time: d.end,
    ...(d.slot === "" ? {} : { slot_minutes: Number(d.slot) }),
    ...(d.capacity === "" ? {} : { capacity: Number(d.capacity) }),
  }));
}

/** Which block a schedule error is about, in words ("Block 2 (Monday 10:00)"), from its details. */
export function blockProblem(error: unknown, drafts: readonly Draft[]): string | undefined {
  if (!(error instanceof ApiError)) return undefined;
  const name = (raw: unknown) => {
    const i = Number(raw);
    const d = drafts[i];
    return d === undefined ? undefined : `block ${i + 1} (${WEEKDAYS[Number(d.weekday)] ?? ""} ${d.start}–${d.end})`;
  };
  if (error.code === "SCH_INVALID_BLOCK") {
    const which = name(error.details["index"]);
    const reason = typeof error.details["reason"] === "string" ? error.details["reason"] : "";
    return which === undefined ? undefined : `Check ${which}: ${reason}.`;
  }
  if (error.code === "SCH_OVERLAP") {
    const a = name(error.details["first"]);
    const b = name(error.details["second"]);
    return a === undefined || b === undefined ? undefined : `${a[0]?.toUpperCase()}${a.slice(1)} overlaps ${b}.`;
  }
  return undefined;
}

/** D4, D10: sessions a change kept because people are booked in them, for the owner to move. */
function KeptSessions({ sessions }: { sessions: readonly DoctorSession[] }) {
  const clinic = useClinic();
  if (sessions.length === 0) return null;
  const clock = (iso: string) => formatClock(iso, clinic.timezone);
  return (
    <div role="alert" className="rounded border border-amber-700 bg-amber-50 p-4">
      <p className="font-semibold">
        {sessions.length === 1 ? "One session has" : `${sessions.length} sessions have`} bookings and
        {sessions.length === 1 ? " was" : " were"} kept. They take no new bookings; reschedule those patients from the queue.
      </p>
      <ul className="mt-2 list-disc pl-6">
        {sessions.map((s) => (
          <li key={s.id}>
            {formatDay(s.on_date)}, {clock(s.starts_at)}–{clock(s.ends_at)}: {s.booked_count} booked
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Schedule settings (D31, FR-APT-01): for owners. A doctor's week of blocks, saved as a whole
 * (R16); their upcoming leave and extra sessions; and the clinic's booking mode. Times are the
 * clinic's wall clock; an end at or before the start means the next day (up to 12 hours).
 * Nothing booked is ever dropped: kept sessions are listed after each change.
 */
export function ScheduleSettings() {
  const clinic = useClinic();
  const api = useAppointmentApi();
  const { clinic: choice, endSession } = useSession();
  const canSetMode = choice.kind === "active" && choice.membership.permissions.includes("CLINIC_MANAGE");
  const [doctors, setDoctors] = useState<readonly Doctor[] | undefined>(undefined);
  const [doctorId, setDoctorId] = useState<string | undefined>(undefined);
  const [schedule, setSchedule] = useState<Schedule | undefined>(undefined);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [kept, setKept] = useState<readonly DoctorSession[]>([]);
  const [error, setError] = useState<unknown>(undefined);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  const pickerId = useId();

  useEffect(() => {
    let cancelled = false;
    api.doctors().then(
      (items) => {
        if (cancelled) return;
        setDoctors(items);
        setDoctorId((current) => current ?? items.find((d) => d.is_active)?.id);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, endSession]);

  useEffect(() => {
    if (doctorId === undefined) return;
    let cancelled = false;
    api.schedule(doctorId).then(
      (found) => {
        if (cancelled) return;
        setSchedule(found);
        setDrafts(draftsOf(found));
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, doctorId, reload, endSession]);

  async function run(work: () => Promise<{ kept: readonly DoctorSession[]; text: string }>) {
    setSaving(true);
    setError(undefined);
    setMessage("");
    try {
      const outcome = await work();
      setKept(outcome.kept);
      setMessage(outcome.text);
      setReload((n) => n + 1);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSaving(false);
    }
  }

  const doctorName = doctors?.find((d) => d.id === doctorId)?.display_name ?? "";
  const set = (key: string, field: keyof Omit<Draft, "key">, value: string) =>
    setDrafts((list) => list.map((d) => (d.key === key ? { ...d, [field]: value } : d)));
  const problem = blockProblem(error, drafts);

  return (
    <section aria-labelledby="schedule-heading" className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 id="schedule-heading" className="text-2xl font-bold">
          Schedule
        </h1>
        {doctors !== undefined && doctors.length > 0 && (
          <div>
            <label htmlFor={pickerId} className="block text-sm font-medium">
              Doctor
            </label>
            <select
              id={pickerId}
              value={doctorId ?? ""}
              onChange={(event) => {
                setDoctorId(event.target.value);
                setKept([]);
                setMessage("");
              }}
              className="rounded border border-slate-500 px-2 py-2"
            >
              {doctors.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.display_name}
                  {d.is_active ? "" : " (inactive)"}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      <p className="text-slate-700">Times are the clinic&apos;s ({clinic.timezone}). An end before the start means the next day, up to 12 hours.</p>

      <p role="status" aria-live="polite" className="min-h-6 font-medium text-green-900">
        {message}
      </p>
      {problem !== undefined && (
        <p role="alert" className="font-semibold text-red-900">
          {problem}
        </p>
      )}
      {error !== undefined && <ErrorNotice error={error} />}
      <KeptSessions sessions={kept} />

      {doctors !== undefined && doctors.length === 0 && <p>No doctors yet.</p>}
      {schedule !== undefined && doctorId !== undefined && (
        <>
          <section aria-labelledby="week-heading" className="space-y-3 rounded border border-slate-300 p-4">
            <h2 id="week-heading" className="text-lg font-bold">
              Weekly hours for {doctorName}
            </h2>
            {drafts.length === 0 && <p className="text-slate-700">No weekly hours: nobody can be booked except in extra sessions.</p>}
            {drafts.map((d, index) => (
              <fieldset key={d.key} className="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-3">
                <legend className="sr-only">Block {index + 1}</legend>
                <label className="text-sm">
                  <span className="block font-medium">Day</span>
                  <select value={d.weekday} onChange={(e) => set(d.key, "weekday", e.target.value)} className="rounded border border-slate-500 px-2 py-1.5">
                    {WEEKDAYS.map((name, i) => (
                      <option key={name} value={i}>
                        {name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-sm">
                  <span className="block font-medium">From</span>
                  <input type="time" value={d.start} onChange={(e) => set(d.key, "start", e.target.value)} className="rounded border border-slate-500 px-2 py-1" />
                </label>
                <label className="text-sm">
                  <span className="block font-medium">To</span>
                  <input type="time" value={d.end} onChange={(e) => set(d.key, "end", e.target.value)} className="rounded border border-slate-500 px-2 py-1" />
                </label>
                <label className="text-sm">
                  <span className="block font-medium">Slot minutes</span>
                  <input inputMode="numeric" value={d.slot} onChange={(e) => set(d.key, "slot", e.target.value)} className="w-20 rounded border border-slate-500 px-2 py-1" />
                </label>
                <label className="text-sm">
                  <span className="block font-medium">Tokens</span>
                  <input inputMode="numeric" value={d.capacity} onChange={(e) => set(d.key, "capacity", e.target.value)} className="w-20 rounded border border-slate-500 px-2 py-1" />
                </label>
                <button
                  type="button"
                  aria-label={`Remove block ${index + 1}`}
                  onClick={() => setDrafts((list) => list.filter((x) => x.key !== d.key))}
                  className="rounded border border-slate-500 px-3 py-1.5"
                >
                  Remove
                </button>
              </fieldset>
            ))}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() =>
                  setDrafts((list) => [...list, { key: newKey(), weekday: "0", start: "10:00", end: "13:00", slot: "15", capacity: "12" }])
                }
                className="rounded border border-blue-800 px-3 py-1.5 font-medium text-blue-900"
              >
                Add hours
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() =>
                  void run(async () => {
                    const change = await api.replaceSchedule(doctorId, blocksOf(drafts));
                    return { kept: change.kept_sessions, text: `Weekly hours for ${doctorName} saved.` };
                  })
                }
                className="rounded bg-blue-800 px-4 py-1.5 font-semibold text-white disabled:bg-slate-400"
              >
                Save weekly hours
              </button>
            </div>
          </section>

          <ExceptionsSection
            schedule={schedule}
            saving={saving}
            onAdd={(body) =>
              void run(async () => {
                const change = await api.addException(doctorId, body);
                const what = body.kind === "LEAVE" ? "Leave" : "Extra session";
                return { kept: change.kept_sessions, text: `${what} on ${formatDay(body.on_date)} added for ${doctorName}.` };
              })
            }
            onRemove={(id, onDate) =>
              void run(async () => {
                const change = await api.removeException(doctorId, id);
                return { kept: change.kept_sessions, text: `Exception on ${formatDay(onDate)} removed.` };
              })
            }
          />

          <BookingModeSection
            mode={schedule.booking_mode}
            canSet={canSetMode}
            saving={saving}
            onSet={(mode) =>
              void run(async () => {
                await api.setBookingMode(mode);
                return { kept: [], text: `The clinic now books by ${mode === "SLOTS" ? "time slots" : "tokens"}.` };
              })
            }
          />
        </>
      )}
    </section>
  );
}

function ExceptionsSection({
  schedule,
  saving,
  onAdd,
  onRemove,
}: {
  schedule: Schedule;
  saving: boolean;
  onAdd: (body: Parameters<ReturnType<typeof useAppointmentApi>["addException"]>[1]) => void;
  onRemove: (id: string, onDate: string) => void;
}) {
  const clinic = useClinic();
  const [kind, setKind] = useState<"LEAVE" | "EXTRA">("LEAVE");
  const [onDate, setOnDate] = useState(clinicToday(clinic.timezone));
  const [start, setStart] = useState("17:00");
  const [end, setEnd] = useState("19:00");
  const [capacity, setCapacity] = useState("8");
  const [slot, setSlot] = useState("15");
  const [note, setNote] = useState("");
  const ids = { kind: useId(), date: useId(), note: useId() };

  return (
    <section aria-labelledby="exceptions-heading" className="space-y-3 rounded border border-slate-300 p-4">
      <h2 id="exceptions-heading" className="text-lg font-bold">
        Leave and extra sessions
      </h2>
      {schedule.exceptions.length === 0 ? (
        <p className="text-slate-700">None coming up.</p>
      ) : (
        <ul className="divide-y divide-slate-200">
          {schedule.exceptions.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-2 py-2">
              <span>
                {formatDay(e.on_date)}: {e.kind === "LEAVE" ? "on leave all day" : `extra session ${e.start_time ?? ""}–${e.end_time ?? ""}`}
                {e.note !== null && <span className="text-slate-700"> · {e.note}</span>}
              </span>
              <button
                type="button"
                disabled={saving}
                aria-label={`Remove the ${e.kind === "LEAVE" ? "leave" : "extra session"} on ${formatDay(e.on_date)}`}
                onClick={() => onRemove(e.id, e.on_date)}
                className="rounded border border-slate-500 px-3 py-1"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-3">
        <div>
          <label htmlFor={ids.kind} className="block text-sm font-medium">
            Add
          </label>
          <select id={ids.kind} value={kind} onChange={(e) => setKind(e.target.value as "LEAVE" | "EXTRA")} className="rounded border border-slate-500 px-2 py-1.5">
            <option value="LEAVE">Leave (whole day)</option>
            <option value="EXTRA">Extra session</option>
          </select>
        </div>
        <div>
          <label htmlFor={ids.date} className="block text-sm font-medium">
            On
          </label>
          <input id={ids.date} type="date" value={onDate} onChange={(e) => setOnDate(e.target.value)} className="rounded border border-slate-500 px-2 py-1" />
        </div>
        {kind === "EXTRA" && (
          <>
            <label className="text-sm">
              <span className="block font-medium">From</span>
              <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className="rounded border border-slate-500 px-2 py-1" />
            </label>
            <label className="text-sm">
              <span className="block font-medium">To</span>
              <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded border border-slate-500 px-2 py-1" />
            </label>
            <label className="text-sm">
              <span className="block font-medium">Slot minutes</span>
              <input inputMode="numeric" value={slot} onChange={(e) => setSlot(e.target.value)} className="w-20 rounded border border-slate-500 px-2 py-1" />
            </label>
            <label className="text-sm">
              <span className="block font-medium">Tokens</span>
              <input inputMode="numeric" value={capacity} onChange={(e) => setCapacity(e.target.value)} className="w-20 rounded border border-slate-500 px-2 py-1" />
            </label>
          </>
        )}
        <div>
          <label htmlFor={ids.note} className="block text-sm font-medium">
            Note (optional)
          </label>
          <input id={ids.note} maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} className="rounded border border-slate-500 px-2 py-1" />
        </div>
        <button
          type="button"
          disabled={saving || onDate === ""}
          onClick={() =>
            onAdd(
              kind === "LEAVE"
                ? { kind, on_date: onDate, ...(note.trim() === "" ? {} : { note }) }
                : {
                    kind,
                    on_date: onDate,
                    start_time: start,
                    end_time: end,
                    ...(slot === "" ? {} : { slot_minutes: Number(slot) }),
                    ...(capacity === "" ? {} : { capacity: Number(capacity) }),
                    ...(note.trim() === "" ? {} : { note }),
                  },
            )
          }
          className="rounded bg-blue-800 px-4 py-1.5 font-semibold text-white disabled:bg-slate-400"
        >
          Add {kind === "LEAVE" ? "leave" : "extra session"}
        </button>
      </div>
    </section>
  );
}

function BookingModeSection({
  mode,
  canSet,
  saving,
  onSet,
}: {
  mode: BookingMode;
  canSet: boolean;
  saving: boolean;
  onSet: (mode: BookingMode) => void;
}) {
  const other: BookingMode = mode === "SLOTS" ? "TOKENS" : "SLOTS";
  const words = (m: BookingMode) => (m === "SLOTS" ? "time slots" : "tokens");
  return (
    <section aria-labelledby="mode-heading" className="space-y-2 rounded border border-slate-300 p-4">
      <h2 id="mode-heading" className="text-lg font-bold">
        How patients are booked
      </h2>
      <p>The clinic books by {words(mode)}.</p>
      {canSet && (
        <button type="button" disabled={saving} onClick={() => onSet(other)} className="rounded border border-blue-800 px-3 py-1.5 font-medium text-blue-900 disabled:text-slate-500">
          Switch to {words(other)}
        </button>
      )}
      <p className="text-sm text-slate-700">Every block needs a slot length for time slots and a number of tokens for tokens; give both to switch freely.</p>
    </section>
  );
}

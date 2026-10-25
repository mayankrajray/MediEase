"use client";

import { useEffect, useId, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import {
  useAppointmentApi,
  type BookingMode,
  type Doctor,
  type DoctorSession,
  type ReminderSettings,
  type RequestSettings,
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
    <div role="alert" className="rounded-lg border border-amber-700 bg-amber-50 p-4">
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
        <h1 id="schedule-heading" className="text-2xl font-bold tracking-tight">
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
              className="rounded-lg border border-slate-400 px-2 py-2"
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

      <p role="status" aria-live="polite" className="min-h-6 font-medium text-emerald-900">
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
          <section aria-labelledby="week-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
            <h2 id="week-heading" className="text-lg font-bold">
              Weekly hours for {doctorName}
            </h2>
            {drafts.length === 0 && <p className="text-slate-700">No weekly hours: nobody can be booked except in extra sessions.</p>}
            {drafts.map((d, index) => (
              <fieldset key={d.key} className="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-3">
                <legend className="sr-only">Block {index + 1}</legend>
                <label className="text-sm">
                  <span className="block font-medium">Day</span>
                  <select value={d.weekday} onChange={(e) => set(d.key, "weekday", e.target.value)} className="rounded-lg border border-slate-400 px-2 py-1.5">
                    {WEEKDAYS.map((name, i) => (
                      <option key={name} value={i}>
                        {name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-sm">
                  <span className="block font-medium">From</span>
                  <input type="time" value={d.start} onChange={(e) => set(d.key, "start", e.target.value)} className="rounded-lg border border-slate-400 px-2 py-1" />
                </label>
                <label className="text-sm">
                  <span className="block font-medium">To</span>
                  <input type="time" value={d.end} onChange={(e) => set(d.key, "end", e.target.value)} className="rounded-lg border border-slate-400 px-2 py-1" />
                </label>
                <label className="text-sm">
                  <span className="block font-medium">Slot minutes</span>
                  <input inputMode="numeric" value={d.slot} onChange={(e) => set(d.key, "slot", e.target.value)} className="w-20 rounded-lg border border-slate-400 px-2 py-1" />
                </label>
                <label className="text-sm">
                  <span className="block font-medium">Tokens</span>
                  <input inputMode="numeric" value={d.capacity} onChange={(e) => set(d.key, "capacity", e.target.value)} className="w-20 rounded-lg border border-slate-400 px-2 py-1" />
                </label>
                <button
                  type="button"
                  aria-label={`Remove block ${index + 1}`}
                  onClick={() => setDrafts((list) => list.filter((x) => x.key !== d.key))}
                  className="rounded-lg border border-slate-400 px-3 py-1.5"
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
                className="rounded-lg border border-brand-700 px-3 py-1.5 font-medium text-brand-800"
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
                className="rounded-lg bg-brand-700 px-4 py-1.5 font-semibold text-white disabled:bg-slate-400"
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

          {canSetMode && (
            <RemindersSection
              saving={saving}
              onSave={(change, text) =>
                void run(async () => {
                  await api.setReminders(change);
                  return { kept: [], text };
                })
              }
            />
          )}

          {canSetMode && (
            <OnlineRequestsSection
              saving={saving}
              onSave={(change, text) =>
                void run(async () => {
                  await api.setRequestSettings(change);
                  return { kept: [], text };
                })
              }
            />
          )}
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
    <section aria-labelledby="exceptions-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
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
                className="rounded-lg border border-slate-400 px-3 py-1"
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
          <select id={ids.kind} value={kind} onChange={(e) => setKind(e.target.value as "LEAVE" | "EXTRA")} className="rounded-lg border border-slate-400 px-2 py-1.5">
            <option value="LEAVE">Leave (whole day)</option>
            <option value="EXTRA">Extra session</option>
          </select>
        </div>
        <div>
          <label htmlFor={ids.date} className="block text-sm font-medium">
            On
          </label>
          <input id={ids.date} type="date" value={onDate} onChange={(e) => setOnDate(e.target.value)} className="rounded-lg border border-slate-400 px-2 py-1" />
        </div>
        {kind === "EXTRA" && (
          <>
            <label className="text-sm">
              <span className="block font-medium">From</span>
              <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className="rounded-lg border border-slate-400 px-2 py-1" />
            </label>
            <label className="text-sm">
              <span className="block font-medium">To</span>
              <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded-lg border border-slate-400 px-2 py-1" />
            </label>
            <label className="text-sm">
              <span className="block font-medium">Slot minutes</span>
              <input inputMode="numeric" value={slot} onChange={(e) => setSlot(e.target.value)} className="w-20 rounded-lg border border-slate-400 px-2 py-1" />
            </label>
            <label className="text-sm">
              <span className="block font-medium">Tokens</span>
              <input inputMode="numeric" value={capacity} onChange={(e) => setCapacity(e.target.value)} className="w-20 rounded-lg border border-slate-400 px-2 py-1" />
            </label>
          </>
        )}
        <div>
          <label htmlFor={ids.note} className="block text-sm font-medium">
            Note (optional)
          </label>
          <input id={ids.note} maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} className="rounded-lg border border-slate-400 px-2 py-1" />
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
          className="rounded-lg bg-brand-700 px-4 py-1.5 font-semibold text-white disabled:bg-slate-400"
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
    <section aria-labelledby="mode-heading" className="space-y-2 rounded-card border border-slate-200 bg-white p-4">
      <h2 id="mode-heading" className="text-lg font-bold">
        How patients are booked
      </h2>
      <p>The clinic books by {words(mode)}.</p>
      {canSet && (
        <button type="button" disabled={saving} onClick={() => onSet(other)} className="rounded-lg border border-brand-700 px-3 py-1.5 font-medium text-brand-800 disabled:text-slate-500">
          Switch to {words(other)}
        </button>
      )}
      <p className="text-sm text-slate-700">Every block needs a slot length for time slots and a number of tokens for tokens; give both to switch freely.</p>
    </section>
  );
}

const HOURS = [0, 1, 2, 3, 4, 5, 6] as const;
const HOLD_MINUTES = [30, 60, 90, 120, 180, 240, 360, 480] as const;

const holdWords = (minutes: number) => (minutes < 60 ? `${minutes} minutes` : minutes % 60 === 0 ? `${minutes / 60} hour${minutes === 60 ? "" : "s"}` : `${minutes} minutes`);

/**
 * M6b-P4 (FR-PUB-01, FR-BKG-02, spec R20): the clinic's public page address, how long a patient's
 * request holds its time, and whether the request form must ask age and sex. Owners only
 * (CLINIC_MANAGE). Applies to requests made after the change; a request stays open for up to
 * 4 hours whatever the hold.
 */
function OnlineRequestsSection({
  saving,
  onSave,
}: {
  saving: boolean;
  onSave: (change: RequestSettings, text: string) => void;
}) {
  const clinic = useClinic();
  const [minutes, setMinutes] = useState(clinic.request_hold_minutes);
  const [ageSex, setAgeSex] = useState(clinic.request_requires_age_sex);
  const [copied, setCopied] = useState(false);
  const ids = { minutes: useId(), ageSex: useId(), link: useId() };
  const address = `${typeof window === "undefined" ? "" : window.location.origin}/c/${clinic.slug}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section aria-labelledby="requests-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4">
      <h2 id="requests-heading" className="text-lg font-bold">
        Online booking requests
      </h2>
      <div className="space-y-1">
        <label htmlFor={ids.link} className="block font-medium">
          Your clinic page
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <input id={ids.link} readOnly value={address} className="min-h-10 min-w-0 flex-1 rounded-lg border border-slate-400 bg-slate-50 px-3 py-2" />
          <button type="button" onClick={() => void copy()} className="min-h-10 rounded-lg border border-brand-700 px-3 py-1.5 font-medium text-brand-800">
            Copy link
          </button>
        </div>
        <p role="status" aria-live="polite" className={copied ? "text-sm font-medium text-emerald-900" : "sr-only"}>
          {copied ? "Link copied." : ""}
        </p>
        <p className="text-sm text-slate-700">Patients choose a time here and ask for it; you reply. The page is not listed on search engines yet.</p>
      </div>
      <div>
        <label htmlFor={ids.minutes} className="block font-medium">
          Keep a requested time for
        </label>
        <select
          id={ids.minutes}
          value={minutes}
          onChange={(event) => setMinutes(Number(event.target.value))}
          className="rounded-lg border border-slate-400 px-2 py-2"
        >
          {HOLD_MINUTES.map((m) => (
            <option key={m} value={m}>
              {holdWords(m)}
            </option>
          ))}
        </select>
        <p className="text-sm text-slate-700">
          While a time is kept, other patients cannot ask for it and the booking drawer shows it as held. After that it can be booked again; the request stays open for
          up to 4 hours.
        </p>
      </div>
      <div className="flex min-h-10 items-center gap-3">
        <input
          id={ids.ageSex}
          type="checkbox"
          checked={ageSex}
          onChange={(event) => setAgeSex(event.target.checked)}
          className="size-5 rounded border-slate-400 accent-brand-700"
        />
        <label htmlFor={ids.ageSex} className="font-medium">
          Ask patients for age and sex
        </label>
      </div>
      <button
        type="button"
        disabled={saving}
        onClick={() =>
          onSave(
            { request_hold_minutes: minutes, request_requires_age_sex: ageSex },
            `Online requests saved: a requested time is kept for ${holdWords(minutes)}; age and sex ${ageSex ? "are asked" : "are optional"}.`,
          )
        }
        className="rounded-lg bg-brand-700 px-4 py-1.5 font-semibold text-white disabled:bg-slate-400"
      >
        Save online requests
      </button>
    </section>
  );
}

/**
 * M6a-P8 (FR-APT-08, decision 3A): the clinic's appointment reminders, the evening before at 19:00
 * and some hours before the visit. Owners only (CLINIC_MANAGE). Applies to bookings made or moved
 * after the change; nothing is sent between 21:00 and 08:00.
 */
function RemindersSection({
  saving,
  onSave,
}: {
  saving: boolean;
  onSave: (change: ReminderSettings, text: string) => void;
}) {
  const clinic = useClinic();
  const [evening, setEvening] = useState(clinic.reminder_evening_before);
  const [hours, setHours] = useState(clinic.reminder_hours_before);
  const ids = { evening: useId(), hours: useId() };
  const before = hours === 0 ? "no reminder before the visit" : `${hours} hour${hours === 1 ? "" : "s"} before`;

  return (
    <section aria-labelledby="reminders-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4">
      <h2 id="reminders-heading" className="text-lg font-bold">
        Appointment reminders
      </h2>
      <p className="text-slate-700">
        Patients who agreed to WhatsApp get a reminder of their visit. Changes apply to bookings made or moved from now on.
        Nothing is sent between 21:00 and 08:00.
      </p>
      <div className="flex min-h-10 items-center gap-3">
        <input
          id={ids.evening}
          type="checkbox"
          checked={evening}
          onChange={(event) => setEvening(event.target.checked)}
          className="size-5 rounded border-slate-400 accent-brand-700"
        />
        <label htmlFor={ids.evening} className="font-medium">
          The evening before, at 19:00
        </label>
      </div>
      <div>
        <label htmlFor={ids.hours} className="block font-medium">
          Before the visit
        </label>
        <select
          id={ids.hours}
          value={hours}
          onChange={(event) => setHours(Number(event.target.value))}
          className="rounded-lg border border-slate-400 px-2 py-2"
        >
          {HOURS.map((h) => (
            <option key={h} value={h}>
              {h === 0 ? "Off" : `${h} hour${h === 1 ? "" : "s"} before`}
            </option>
          ))}
        </select>
      </div>
      <button
        type="button"
        disabled={saving}
        onClick={() =>
          onSave(
            { reminder_evening_before: evening, reminder_hours_before: hours },
            `Appointment reminders saved: ${evening ? "the evening before" : "no evening reminder"}, ${before}.`,
          )
        }
        className="rounded-lg bg-brand-700 px-4 py-1.5 font-semibold text-white disabled:bg-slate-400"
      >
        Save reminders
      </button>
    </section>
  );
}
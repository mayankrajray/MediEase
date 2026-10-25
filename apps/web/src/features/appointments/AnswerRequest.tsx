"use client";

import { useEffect, useId, useState } from "react";

import { Dialog } from "@/components/Dialog";
import { Drawer } from "@/components/Drawer";
import { useNow } from "@/components/useNow";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import type { Patient } from "@/features/patients/fields";
import { useClinic } from "@/features/shell/ClinicGate";
import { ApiError } from "@/lib/api/client";
import { formatClock, formatDay, formatDayTime } from "@/lib/format/time";

import {
  useAppointmentApi,
  type DoctorSession,
  type RecordChoice,
  type RequestCandidates,
  type StaffBookingRequest,
  type StaffDeclineReason,
} from "./api";
import { PatientPicker } from "./PatientPicker";

type Sex = "FEMALE" | "MALE" | "OTHER" | "UNDISCLOSED";
const SEXES: readonly Sex[] = ["FEMALE", "MALE", "OTHER", "UNDISCLOSED"];
const SEX_LABELS: Readonly<Record<Sex, string>> = {
  FEMALE: "Female",
  MALE: "Male",
  OTHER: "Other",
  UNDISCLOSED: "Prefers not to say",
};

export const DECLINE_LABELS: Readonly<Record<StaffDeclineReason, string>> = {
  TIME_UNAVAILABLE: "Time no longer available",
  DOCTOR_UNAVAILABLE: "Doctor unavailable",
  PLEASE_CALL: "Please call the clinic",
  NOT_ONLINE: "Not something we can book online",
  DUPLICATE: "Duplicate request",
  OTHER: "Other",
};

/** What the desk has chosen for the record so far (R36-R38); `undefined` until a choice. */
type Choice =
  | { readonly kind: "existing"; readonly id: string; readonly label: string }
  | { readonly kind: "new"; readonly name: string; readonly sex: Sex | ""; readonly age: string };

function toRecord(choice: Choice | undefined): RecordChoice | undefined {
  if (choice === undefined) return undefined;
  if (choice.kind === "existing") return { patient_id: choice.id };
  const age = Number.parseInt(choice.age, 10);
  if (choice.sex === "" || Number.isNaN(age) || choice.name.trim() === "") return undefined;
  return { new_patient: { full_name: choice.name.trim(), sex: choice.sex, age_years: age } };
}

/**
 * R36-R38: the clinic record this request is for. Candidates share the request's phone (with
 * their no-show count); search finds any other record; *Create new* is prefilled from the request.
 * Phone only suggests: nothing is chosen until the desk chooses. An account already linked here
 * has exactly one possible record.
 */
function RecordPicker({ request, onChange }: { request: StaffBookingRequest; onChange: (record: RecordChoice | undefined) => void }) {
  const api = useAppointmentApi();
  const { endSession } = useSession();
  const [candidates, setCandidates] = useState<RequestCandidates | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [choice, setChoice] = useState<Choice | undefined>(undefined);
  const [searching, setSearching] = useState(false);
  const ids = { name: useId(), sex: useId(), age: useId() };

  useEffect(() => {
    let cancelled = false;
    api.requestCandidates(request.id).then(
      (found) => {
        if (cancelled) return;
        setCandidates(found);
        const only = found.items[0];
        if (found.linked && only !== undefined) {
          const linked: Choice = { kind: "existing", id: only.id, label: `${only.full_name} · ${only.code}` };
          setChoice(linked);
          onChange(toRecord(linked));
        }
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
    // `onChange` is the parent's setter; the candidates are read once per request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, request.id, endSession]);

  function choose(next: Choice) {
    setChoice(next);
    onChange(toRecord(next));
  }

  function pickSearched(patient: Pick<Patient, "id" | "full_name" | "code">) {
    setSearching(false);
    choose({ kind: "existing", id: patient.id, label: `${patient.full_name} · ${patient.code}` });
  }

  if (error !== undefined) return <ErrorNotice error={error} />;
  if (candidates === undefined) return <p role="status">Looking for this patient&apos;s record…</p>;

  const fresh = (): Choice => ({
    kind: "new",
    name: candidates.suggested.full_name,
    sex: candidates.suggested.sex ?? "",
    age: candidates.suggested.age_years === null ? "" : String(candidates.suggested.age_years),
  });

  if (candidates.linked) {
    return (
      <p className="rounded bg-slate-100 px-3 py-2">
        Already linked to this patient&apos;s app: <span className="font-semibold">{choice?.kind === "existing" ? choice.label : ""}</span>
      </p>
    );
  }

  return (
    <fieldset className="space-y-2">
      <legend className="font-medium">Which record is this?</legend>
      {candidates.items.length > 0 && <p className="text-sm text-slate-700">Records with the same phone. Choose only if it is the same person.</p>}
      {candidates.items.map((c) => (
        <label key={c.id} className="flex items-start gap-2">
          <input
            type="radio"
            name="record"
            checked={choice?.kind === "existing" && choice.id === c.id}
            onChange={() => choose({ kind: "existing", id: c.id, label: `${c.full_name} · ${c.code}` })}
          />
          <span>
            <span className="font-semibold">{c.full_name}</span> · {c.code} · {c.age_years} years
            {c.no_shows > 0 && <span className="block text-sm text-amber-900">{c.no_shows} no-show{c.no_shows === 1 ? "" : "s"} in 12 months</span>}
          </span>
        </label>
      ))}
      {choice?.kind === "existing" && !candidates.items.some((c) => c.id === choice.id) && (
        <p className="rounded bg-slate-100 px-3 py-2">
          Chosen: <span className="font-semibold">{choice.label}</span>
        </p>
      )}
      {searching ? (
        <PatientPicker onPick={pickSearched} />
      ) : (
        <button type="button" onClick={() => setSearching(true)} className="text-brand-800 underline">
          Search for another record
        </button>
      )}
      <label className="flex items-center gap-2">
        <input type="radio" name="record" checked={choice?.kind === "new"} onChange={() => choose(fresh())} />
        <span className="font-semibold">Create new record</span>
      </label>
      {choice?.kind === "new" && (
        <div className="grid gap-3 rounded-lg border border-slate-300 p-3 sm:grid-cols-3">
          <div className="sm:col-span-3">
            <label htmlFor={ids.name} className="block font-medium">
              Full name
            </label>
            <input id={ids.name} value={choice.name} maxLength={200} onChange={(e) => choose({ ...choice, name: e.target.value })} className="min-h-10 w-full rounded-lg border border-slate-400 px-3" />
          </div>
          <div>
            <label htmlFor={ids.sex} className="block font-medium">
              Sex (required)
            </label>
            <select id={ids.sex} value={choice.sex} onChange={(e) => choose({ ...choice, sex: e.target.value as Sex | "" })} className="min-h-10 w-full rounded-lg border border-slate-400 px-2">
              <option value="">Choose</option>
              {SEXES.map((s) => (
                <option key={s} value={s}>
                  {SEX_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor={ids.age} className="block font-medium">
              Age in years (required)
            </label>
            <input id={ids.age} inputMode="numeric" maxLength={3} value={choice.age} onChange={(e) => choose({ ...choice, age: e.target.value })} className="min-h-10 w-full rounded-lg border border-slate-400 px-3" />
          </div>
        </div>
      )}
    </fieldset>
  );
}

/** The words for a refusal the desk can act on; otherwise the API's message. */
function answerError(error: unknown): string | undefined {
  if (!(error instanceof ApiError)) return undefined;
  switch (error.code) {
    case "BKG_ALREADY_ANSWERED":
      return "Someone has already answered this request, or it has expired.";
    case "APT_SLOT_TAKEN":
    case "APT_SESSION_FULL":
    case "APT_SLOT_HELD":
      return "That time has gone. Propose another time instead.";
    case "PRT_ALREADY_LINKED":
      return "That record is already linked to another patient app account. Choose another record or create a new one.";
    default:
      return undefined;
  }
}

function RequestSummary({ request }: { request: StaffBookingRequest }) {
  const clinic = useClinic();
  return (
    <div className="rounded bg-slate-100 px-3 py-2">
      <p className="font-semibold">{request.full_name}</p>
      <p className="text-sm text-slate-700">
        {formatDayTime(request.starts_at, clinic.timezone)} · {request.doctor_name} · {request.phone_e164}
      </p>
      {request.reason !== null && <p className="text-sm text-slate-800">Reason: {request.reason}</p>}
    </div>
  );
}

/** R34: accept books the requested time and links the patient's app to the chosen record. */
export function AcceptDrawer({ request, onDone, onClose }: { request: StaffBookingRequest; onDone: (message: string) => void; onClose: () => void }) {
  const api = useAppointmentApi();
  const { endSession } = useSession();
  const [record, setRecord] = useState<RecordChoice | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(undefined);

  async function confirm() {
    if (record === undefined) return;
    setSaving(true);
    setError(undefined);
    try {
      await api.acceptRequest(request.id, record);
      onDone(`${request.full_name}'s request accepted and booked.`);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSaving(false);
    }
  }

  const words = answerError(error);
  return (
    <Drawer title="Accept request" onClose={onClose}>
      <RequestSummary request={request} />
      <RecordPicker request={request} onChange={setRecord} />
      {error !== undefined && <ErrorNotice error={error} {...(words === undefined ? {} : { message: words })} />}
      <button
        type="button"
        disabled={saving || record === undefined}
        onClick={() => void confirm()}
        className="w-full rounded bg-brand-700 px-4 py-2 font-semibold text-white hover:bg-brand-800 disabled:bg-slate-400"
      >
        {saving ? "Booking…" : "Accept and book"}
      </button>
    </Drawer>
  );
}

const MIN_LEAD_MS = 2 * 3_600_000;

function offerable(session: DoctorSession, now: number): boolean {
  return session.status === "OPEN" && session.available - session.held.filter((h) => Date.parse(h.until) > now).length > 0 && Date.parse(session.starts_at) - now >= MIN_LEAD_MS;
}

function freeSlots(session: DoctorSession, now: number) {
  const held = new Set(session.held.filter((h) => Date.parse(h.until) > now).map((h) => h.slot_start));
  return session.slots.filter((s) => s.available !== false && !held.has(s.starts_at) && Date.parse(s.starts_at) - now >= MIN_LEAD_MS);
}

/**
 * R40: offer another time with the same doctor, at least 2 hours ahead, free of bookings and
 * other holds. The record is chosen now; the patient's app is linked when they accept.
 */
export function ProposeDrawer({ request, onDone, onClose }: { request: StaffBookingRequest; onDone: (message: string) => void; onClose: () => void }) {
  const clinic = useClinic();
  const api = useAppointmentApi();
  const { endSession } = useSession();
  const now = useNow();
  const [date, setDate] = useState(request.starts_at.slice(0, 10));
  const [day, setDay] = useState<{ date: string; items: readonly DoctorSession[] } | undefined>(undefined);
  const [place, setPlace] = useState<{ sessionId: string; slotStart?: string } | undefined>(undefined);
  const [record, setRecord] = useState<RecordChoice | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const dateId = useId();
  const clock = (iso: string) => formatClock(iso, clinic.timezone);

  useEffect(() => {
    if (request.doctor_id === null) return;
    let cancelled = false;
    api.sessions(date, request.doctor_id).then(
      (items) => {
        if (!cancelled) setDay({ date, items });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, date, request.doctor_id, endSession]);

  const isOriginal = (sessionId: string, slotStart?: string) =>
    sessionId === request.session_id && (slotStart ?? null) === (request.mode === "SLOTS" ? request.starts_at : null);

  async function confirm() {
    if (place === undefined || record === undefined) return;
    setSaving(true);
    setError(undefined);
    try {
      await api.proposeTime(request.id, place.sessionId, place.slotStart, record);
      onDone(`Another time offered to ${request.full_name}.`);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSaving(false);
    }
  }

  const sessions = day !== undefined && day.date === date ? day.items : undefined;
  const words = answerError(error);
  return (
    <Drawer title="Propose another time" onClose={onClose}>
      <RequestSummary request={request} />
      <div>
        <label htmlFor={dateId} className="block font-medium">
          Date
        </label>
        <input id={dateId} type="date" value={date} onChange={(e) => e.target.value !== "" && setDate(e.target.value)} className="w-full rounded-lg border border-slate-400 px-2 py-2" />
      </div>
      {sessions === undefined && <p role="status">Loading sessions…</p>}
      {sessions !== undefined && sessions.filter((s) => offerable(s, now)).length === 0 && <p role="status">No time to offer on {formatDay(date)}.</p>}
      {sessions !== undefined && (
        <fieldset className="space-y-2">
          <legend className="font-medium">New time</legend>
          {sessions
            .filter((s) => offerable(s, now))
            .map((s) =>
              s.mode === "TOKENS" ? (
                isOriginal(s.id) ? null : (
                  <label key={s.id} className="flex items-center gap-2">
                    <input type="radio" name="place" checked={place?.sessionId === s.id} onChange={() => setPlace({ sessionId: s.id })} />
                    {clock(s.starts_at)}–{clock(s.ends_at)} · {s.available} left
                  </label>
                )
              ) : (
                <div key={s.id} className="flex flex-wrap gap-2">
                  {freeSlots(s, now)
                    .filter((slot) => !isOriginal(s.id, slot.starts_at))
                    .map((slot) => (
                      <label key={slot.starts_at} className="flex items-center gap-1 rounded-lg border border-slate-300 px-2 py-1 has-[:checked]:border-brand-700 has-[:checked]:bg-brand-50">
                        <input type="radio" name="place" checked={place?.slotStart === slot.starts_at} onChange={() => setPlace({ sessionId: s.id, slotStart: slot.starts_at })} />
                        {clock(slot.starts_at)}
                      </label>
                    ))}
                </div>
              ),
            )}
        </fieldset>
      )}
      <RecordPicker request={request} onChange={setRecord} />
      {error !== undefined && <ErrorNotice error={error} {...(words === undefined ? {} : { message: words })} />}
      <button
        type="button"
        disabled={saving || place === undefined || record === undefined}
        onClick={() => void confirm()}
        className="w-full rounded bg-brand-700 px-4 py-2 font-semibold text-white hover:bg-brand-800 disabled:bg-slate-400"
      >
        {saving ? "Sending…" : "Offer this time"}
      </button>
    </Drawer>
  );
}

const STAFF_REASONS = Object.keys(DECLINE_LABELS) as StaffDeclineReason[];

/** R39: the patient sees the reason in their language; the note stays with the clinic. */
export function DeclineDialog({ request, onDone, onClose }: { request: StaffBookingRequest; onDone: (message: string) => void; onClose: () => void }) {
  const api = useAppointmentApi();
  const { endSession } = useSession();
  const [reason, setReason] = useState<StaffDeclineReason | undefined>(undefined);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const noteId = useId();

  async function submit() {
    if (reason === undefined) return;
    setSaving(true);
    setError(undefined);
    try {
      await api.declineRequest(request.id, reason, note);
      onDone(`${request.full_name}'s request declined.`);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSaving(false);
    }
  }

  const words = answerError(error);
  return (
    <Dialog title={`Decline ${request.full_name}'s request`} onClose={onClose}>
      <fieldset className="space-y-1">
        <legend className="font-medium">What should the patient be told?</legend>
        {STAFF_REASONS.map((r) => (
          <label key={r} className="flex items-center gap-2">
            <input type="radio" name="decline-reason" checked={reason === r} onChange={() => setReason(r)} />
            {DECLINE_LABELS[r]}
          </label>
        ))}
      </fieldset>
      <div>
        <label htmlFor={noteId} className="block font-medium">
          Note for the clinic (optional)
        </label>
        <input id={noteId} maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} className="min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2" />
        <p className="text-sm text-slate-700">Only staff see this note. Not medical details.</p>
      </div>
      {error !== undefined && <ErrorNotice error={error} {...(words === undefined ? {} : { message: words })} />}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose} className="min-h-10 rounded-lg border border-slate-400 bg-white px-4 py-2 font-medium">
          Keep request
        </button>
        <button type="button" disabled={saving || reason === undefined} onClick={() => void submit()} className="rounded-lg bg-red-800 px-4 py-2 font-semibold text-white disabled:bg-slate-400">
          {saving ? "Declining…" : "Decline request"}
        </button>
      </div>
    </Dialog>
  );
}

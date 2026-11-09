"use client";

import { Search } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { Dialog } from "@/components/Dialog";
import { Drawer } from "@/components/Drawer";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { CHOICE_CARD, CHOICE_INPUT, DateField, ERROR, SelectField, TextField } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
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

export const NEED_RECORD = "Choose which record this is, or create a new one.";
export const NEED_NEW_RECORD = "Fill in the new record's name, sex and age.";

/**
 * R36-R38: the clinic record this request is for. Candidates share the request's phone (with
 * their no-show count); search finds any other record; *Create new* is prefilled from the request.
 * Phone only suggests: nothing is chosen until the desk chooses. An account already linked here
 * has exactly one possible record.
 *
 * M7c-P7 (M4): choices are choice cards; the new record uses the shared fields. `checked` (after
 * a submit) says under the choice what is still missing, as the forms rule asks.
 */
function RecordPicker({
  request,
  onChange,
  checked = false,
}: {
  request: StaffBookingRequest;
  onChange: (record: RecordChoice | undefined) => void;
  checked?: boolean;
}) {
  const api = useAppointmentApi();
  const { endSession } = useSession();
  const [candidates, setCandidates] = useState<RequestCandidates | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [attempt, setAttempt] = useState(0);
  const [choice, setChoice] = useState<Choice | undefined>(undefined);
  const [searching, setSearching] = useState(false);
  const ids = { name: useId(), sex: useId(), age: useId(), missing: useId() };

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
  }, [api, request.id, endSession, attempt]);

  function choose(next: Choice) {
    setChoice(next);
    onChange(toRecord(next));
  }

  function pickSearched(patient: Pick<Patient, "id" | "full_name" | "code">) {
    setSearching(false);
    choose({ kind: "existing", id: patient.id, label: `${patient.full_name} · ${patient.code}` });
  }

  if (error !== undefined)
    return (
      <ErrorNotice
        error={error}
        onRetry={() => {
          setError(undefined);
          setAttempt((n) => n + 1);
        }}
      />
    );
  if (candidates === undefined)
    return (
      <p role="status" className="inline-flex items-center gap-2 text-slate-700">
        <Spinner /> Looking for this patient&apos;s record…
      </p>
    );

  const fresh = (): Choice => ({
    kind: "new",
    name: candidates.suggested.full_name,
    sex: candidates.suggested.sex ?? "",
    age: candidates.suggested.age_years === null ? "" : String(candidates.suggested.age_years),
  });

  if (candidates.linked) {
    return (
      <Alert tone="info">
        Already linked to this patient&apos;s app: <span className="font-semibold">{choice?.kind === "existing" ? choice.label : ""}</span>
      </Alert>
    );
  }

  const missing = checked && toRecord(choice) === undefined ? (choice?.kind === "new" ? NEED_NEW_RECORD : NEED_RECORD) : undefined;
  const ageNumber = choice?.kind === "new" ? Number.parseInt(choice.age, 10) : 0;

  return (
    <fieldset className="space-y-2" aria-describedby={missing === undefined ? undefined : ids.missing}>
      <legend className="mb-1 text-sm font-semibold text-slate-900">
        Which record is this? <span className="font-normal text-slate-700">(required)</span>
      </legend>
      {candidates.items.length > 0 && <p className="text-sm text-slate-700">Records with the same phone. Choose only if it is the same person.</p>}
      {candidates.items.map((c) => (
        <label key={c.id} className={cx(CHOICE_CARD, "items-start")}>
          <input
            type="radio"
            name="record"
            checked={choice?.kind === "existing" && choice.id === c.id}
            onChange={() => choose({ kind: "existing", id: c.id, label: `${c.full_name} · ${c.code}` })}
            className={cx(CHOICE_INPUT, "mt-1")}
          />
          <span>
            <span className="font-semibold">{c.full_name}</span> · <span className="tabular-nums">{c.code}</span> · {c.age_years} years
            {c.no_shows > 0 && <span className="block text-sm font-medium text-warning">{c.no_shows} no-show{c.no_shows === 1 ? "" : "s"} in 12 months</span>}
          </span>
        </label>
      ))}
      {choice?.kind === "existing" && !candidates.items.some((c) => c.id === choice.id) && (
        <Alert tone="info">
          Chosen: <span className="font-semibold">{choice.label}</span>
        </Alert>
      )}
      {searching ? (
        <PatientPicker onPick={pickSearched} />
      ) : (
        <Button size="sm" variant="ghost" icon={<Search className="size-4" />} onClick={() => setSearching(true)}>
          Search for another record
        </Button>
      )}
      <label className={CHOICE_CARD}>
        <input type="radio" name="record" checked={choice?.kind === "new"} onChange={() => choose(fresh())} className={CHOICE_INPUT} />
        <span className="font-semibold">Create new record</span>
      </label>
      {choice?.kind === "new" && (
        <div className="grid gap-3 rounded-lg border border-line bg-surface-muted p-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <TextField
              id={ids.name}
              label="Full name"
              value={choice.name}
              maxLength={200}
              onChange={(name) => choose({ ...choice, name })}
              error={checked && choice.name.trim() === "" ? "Enter the patient's full name." : undefined}
            />
          </div>
          <SelectField
            id={ids.sex}
            label="Sex"
            required
            value={choice.sex}
            onChange={(sex) => choose({ ...choice, sex: sex as Sex | "" })}
            options={[{ value: "", label: "Choose" }, ...SEXES.map((s) => ({ value: s, label: SEX_LABELS[s] }))]}
            error={checked && choice.sex === "" ? "Choose the patient's sex." : undefined}
          />
          <TextField
            id={ids.age}
            label="Age in years"
            required
            inputMode="numeric"
            maxLength={3}
            value={choice.age}
            onChange={(age) => choose({ ...choice, age })}
            error={checked && Number.isNaN(ageNumber) ? "Enter the age in whole years." : undefined}
          />
        </div>
      )}
      {missing !== undefined && (
        <p id={ids.missing} className={ERROR}>
          {missing}
        </p>
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
    <div className="rounded-lg border border-line bg-surface-muted px-3 py-2.5">
      <p className="font-semibold text-slate-900">{request.full_name}</p>
      <p className="text-sm tabular-nums text-slate-700">
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
  const [checked, setChecked] = useState(false);

  async function confirm() {
    setChecked(true);
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
      <RecordPicker request={request} onChange={setRecord} checked={checked} />
      {error !== undefined && <ErrorNotice error={error} {...(words === undefined ? {} : { message: words })} />}
      <Button variant="primary" className="w-full" loading={saving} onClick={() => void confirm()}>
        Accept and book
      </Button>
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
  const [checked, setChecked] = useState(false);
  const dateId = useId();
  const placeId = useId();
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
    setChecked(true);
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
      <DateField id={dateId} label="Date" value={date} onChange={(value) => value !== "" && setDate(value)} />
      {sessions === undefined && (
        <p role="status" className="inline-flex items-center gap-2 text-slate-700">
          <Spinner /> Loading sessions…
        </p>
      )}
      {sessions !== undefined && sessions.filter((s) => offerable(s, now)).length === 0 && (
        <p role="status" className="text-slate-700">
          No time to offer on {formatDay(date)}.
        </p>
      )}
      {sessions !== undefined && (
        <fieldset className="space-y-2" aria-describedby={checked && place === undefined ? placeId : undefined}>
          <legend className="mb-1 text-sm font-semibold text-slate-900">
            New time <span className="font-normal text-slate-700">(required)</span>
          </legend>
          {sessions
            .filter((s) => offerable(s, now))
            .map((s) =>
              s.mode === "TOKENS" ? (
                isOriginal(s.id) ? null : (
                  <label key={s.id} className={CHOICE_CARD}>
                    <input type="radio" name="place" checked={place?.sessionId === s.id} onChange={() => setPlace({ sessionId: s.id })} className={CHOICE_INPUT} />
                    <span className="tabular-nums">
                      {clock(s.starts_at)}–{clock(s.ends_at)} · {s.available} left
                    </span>
                  </label>
                )
              ) : (
                <div key={s.id} className="flex flex-wrap gap-2">
                  {freeSlots(s, now)
                    .filter((slot) => !isOriginal(s.id, slot.starts_at))
                    .map((slot) => (
                      <label key={slot.starts_at} className={cx(CHOICE_CARD, "min-h-9 gap-2 px-2.5 py-1 tabular-nums")}>
                        <input type="radio" name="place" checked={place?.slotStart === slot.starts_at} onChange={() => setPlace({ sessionId: s.id, slotStart: slot.starts_at })} className={CHOICE_INPUT} />
                        {clock(slot.starts_at)}
                      </label>
                    ))}
                </div>
              ),
            )}
          {checked && place === undefined && (
            <p id={placeId} className={ERROR}>
              Choose the time to offer.
            </p>
          )}
        </fieldset>
      )}
      <RecordPicker request={request} onChange={setRecord} checked={checked} />
      {error !== undefined && <ErrorNotice error={error} {...(words === undefined ? {} : { message: words })} />}
      <Button variant="primary" className="w-full" loading={saving} onClick={() => void confirm()}>
        Offer this time
      </Button>
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
  const [checked, setChecked] = useState(false);
  const noteId = useId();
  const reasonId = useId();
  const firstReason = useRef<HTMLInputElement>(null);

  async function submit() {
    setChecked(true);
    if (reason === undefined) {
      firstReason.current?.focus();
      return;
    }
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
      <fieldset className="space-y-1" aria-describedby={checked && reason === undefined ? reasonId : undefined}>
        <legend className="mb-1 text-sm font-semibold text-slate-900">
          What should the patient be told? <span className="font-normal text-slate-700">(required)</span>
        </legend>
        {STAFF_REASONS.map((r, index) => (
          <label key={r} className={CHOICE_CARD}>
            <input
              ref={index === 0 ? firstReason : undefined}
              type="radio"
              name="decline-reason"
              checked={reason === r}
              onChange={() => setReason(r)}
              className={CHOICE_INPUT}
            />
            {DECLINE_LABELS[r]}
          </label>
        ))}
        {checked && reason === undefined && (
          <p id={reasonId} className={cx(ERROR, "pt-1")}>
            Choose what the patient should be told.
          </p>
        )}
      </fieldset>
      <TextField
        id={noteId}
        label="Note for the clinic (optional)"
        value={note}
        onChange={setNote}
        maxLength={200}
        counter
        hint="Only staff see this note. Not medical details."
      />
      {error !== undefined && <ErrorNotice error={error} {...(words === undefined ? {} : { message: words })} />}
      <div className="flex flex-wrap justify-end gap-2">
        <Button onClick={onClose} disabled={saving}>
          Keep request
        </Button>
        <Button variant="danger" loading={saving} onClick={() => void submit()}>
          Decline request
        </Button>
      </div>
    </Dialog>
  );
}

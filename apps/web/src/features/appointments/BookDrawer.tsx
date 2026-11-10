"use client";

import { ChevronLeft, ChevronRight, Clock, TriangleAlert } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";

import { Drawer } from "@/components/Drawer";
import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { CHOICE_CARD, CHOICE_INPUT, ERROR, INPUT_BASE, LABEL, SelectField } from "@/components/ui/Field";
import { RowsSkeleton } from "@/components/ui/Skeleton";
import { useNow } from "@/components/useNow";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { clinicToday, type Patient } from "@/features/patients/fields";
import { useClinic } from "@/features/shell/ClinicGate";
import { ApiError } from "@/lib/api/client";
import { addDays, formatClock, formatDay } from "@/lib/format/time";

import { useAppointmentApi, type Appointment, type Doctor, type DoctorSession } from "./api";
import { PatientPicker } from "./PatientPicker";

/** Who is being booked: a patient (new booking) or an existing appointment (reschedule). */
export type BookingTarget =
  | { readonly kind: "book"; readonly patient?: Pick<Patient, "id" | "full_name" | "code"> }
  | {
      readonly kind: "reschedule";
      // Only the ID is read: the bookings-to-move list (M6a-P8) reschedules from its own rows too.
      readonly appointment: Pick<Appointment, "id">;
      readonly patientName: string;
    };

type Choice = { readonly sessionId: string; readonly slotStart?: string };

/** Staff asked to book over an online request: shown until they confirm or back out (R18a). */
type Override = { readonly until: string };

function bookable(session: DoctorSession, now: number): boolean {
  return session.status === "OPEN" && new Date(session.ends_at).getTime() > now && session.available > 0;
}

/** M6b-P4 (ADR-0018): the online requests still holding this session's places at `now`. */
function liveHolds(session: DoctorSession, now: number) {
  return session.held.filter((h) => new Date(h.until).getTime() > now);
}

/** When the hold on the chosen place ends, or undefined if nothing holds it (R18). */
export function heldUntil(session: DoctorSession, choice: Choice, now: number): string | undefined {
  const holds = liveHolds(session, now);
  if (choice.slotStart !== undefined) return holds.find((h) => h.slot_start === choice.slotStart)?.until;
  if (holds.length === 0 || session.available - holds.length > 0) return undefined;
  return holds.map((h) => h.until).sort()[0];
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
  const [override, setOverride] = useState<Override | undefined>(undefined);
  const [checked, setChecked] = useState(false);
  const ids = { doctor: useId(), date: useId() };
  const pickerFocus = useId();
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

  async function confirm(overrideHold = false) {
    if (choice === undefined || (target.kind === "book" && patient === undefined)) return;
    const holdEnds = chosen === undefined ? undefined : heldUntil(chosen, choice, Date.now());
    if (holdEnds !== undefined && !overrideHold) {
      setOverride({ until: holdEnds }); // ask first; nothing is sent (R18a)
      return;
    }
    setSaving(true);
    setError(undefined);
    setOverride(undefined);
    try {
      const done =
        target.kind === "book"
          ? await api.book({
              session_id: choice.sessionId,
              patient_id: patient?.id ?? "",
              source: "FRONT_DESK",
              ...(choice.slotStart === undefined ? {} : { slot_start: choice.slotStart }),
              ...(overrideHold ? { override_hold: true } : {}),
            })
          : await api.reschedule(target.appointment.id, choice.sessionId, choice.slotStart, overrideHold);
      const place = done.token_number !== null ? `token ${done.token_number}` : clock(done.slot_start ?? "");
      const verb = target.kind === "book" ? "booked" : "moved";
      onDone(done, `${who ?? "Patient"} ${verb}: ${formatDay(done.on_date)}, ${place}.`);
    } catch (failure) {
      if (endSession(failure)) return;
      if (failure instanceof ApiError && failure.code === "APT_SLOT_HELD") {
        // A request arrived while the drawer was open: same question as above.
        const until = failure.details["held_until"];
        setOverride({ until: typeof until === "string" ? until : new Date().toISOString() });
      } else {
        setError(failure);
      }
      setReload((n) => n + 1); // someone may have taken the place: show the day as it is now
    } finally {
      setSaving(false);
    }
  }

  const needPatient = target.kind === "book" && patient === undefined;
  const missing = !checked ? undefined : needPatient ? NEED_PATIENT : choice === undefined || chosen === undefined ? NEED_TIME : undefined;
  const today = clinicToday(clinic.timezone);

  function pressConfirm() {
    setChecked(true);
    if (needPatient) {
      document.getElementById(pickerFocus)?.focus();
      return;
    }
    if (choice === undefined || chosen === undefined) return;
    void confirm();
  }

  return (
    <Drawer title={target.kind === "book" ? "Book appointment" : `Reschedule ${target.patientName}`} onClose={onClose}>
      {/* M7c-P7 (M6): 1 who, 2 which doctor and day, 3 which time, then one confirm. */}
      <Step n={1} title="Patient">
        {needPatient ? (
          <PatientPicker onPick={setPatient} inputId={pickerFocus} hideLabel />
        ) : (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface-muted px-3 py-2.5">
            <Avatar name={who ?? ""} size="sm" />
            <span className="min-w-0 flex-1">
              <span className="block break-words font-semibold text-slate-900">{who}</span>
              {patient !== undefined && (
                <>
                  <span className="sr-only"> · </span>
                  <span className="block text-sm tabular-nums text-slate-700">{patient.code}</span>
                </>
              )}
            </span>
            {target.kind === "book" && (
              <Button size="sm" variant="ghost" onClick={() => setPatient(undefined)}>
                Change patient
              </Button>
            )}
          </div>
        )}
      </Step>

      <Step n={2} title="Doctor and day">
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectField
            id={ids.doctor}
            label="Doctor"
            value={doctorId}
            onChange={setDoctorId}
            options={doctors.map((d) => ({ value: d.id, label: d.display_name }))}
          />
          <div>
            <label htmlFor={ids.date} className={LABEL}>
              Date
            </label>
            <div className="mt-1.5 flex gap-1.5">
              <Button
                size="sm"
                className="min-h-10 px-2.5"
                disabled={date <= today}
                onClick={() => setDate(addDays(date, -1))}
                aria-label="Day before"
                icon={<ChevronLeft className="size-4" />}
              />
              <input
                id={ids.date}
                type="date"
                min={today}
                value={date}
                onChange={(event) => event.target.value !== "" && setDate(event.target.value)}
                className={cx(INPUT_BASE, "min-w-0 flex-1 cursor-pointer tabular-nums")}
              />
              <Button size="sm" className="min-h-10 px-2.5" onClick={() => setDate(addDays(date, 1))} aria-label="Day after" icon={<ChevronRight className="size-4" />} />
            </div>
          </div>
        </div>
        <p className="text-sm text-slate-700">{formatDay(date)}</p>
      </Step>

      <Step n={3} title="Time">
        {loadError !== undefined && <ErrorNotice error={loadError} onRetry={() => setReload((n) => n + 1)} />}
        {day === null && loadError === undefined && <RowsSkeleton label="Loading sessions…" rows={3} />}
        {day !== null && day.length === 0 && (
          <p role="status" className="rounded-lg border border-dashed border-slate-300 px-3 py-5 text-center text-sm text-slate-700">
            The doctor has no sessions on {formatDay(date)}. Try the next day.
          </p>
        )}
        {day !== null && day.length > 0 && (
          <fieldset className="space-y-4" aria-describedby={missing === NEED_TIME ? `${ids.date}-missing` : undefined}>
            <legend className="sr-only">When</legend>
            {day.map((session) => {
              const open = bookable(session, now);
              const label = `${clock(session.starts_at)}–${clock(session.ends_at)}`;
              const holds = liveHolds(session, now).length;
              if (session.mode === "TOKENS") {
                return (
                  <label key={session.id} className={cx(CHOICE_CARD, "items-start", !open && "cursor-not-allowed opacity-60 hover:bg-transparent")}>
                    <input
                      type="radio"
                      name="place"
                      disabled={!open}
                      checked={choice?.sessionId === session.id}
                      onChange={() => {
                        setChoice({ sessionId: session.id });
                        setOverride(undefined);
                      }}
                      className={cx(CHOICE_INPUT, "mt-1")}
                    />
                    <span className="min-w-0">
                      <span className="block font-semibold tabular-nums text-slate-900">{label}</span>
                      <span className="block text-sm text-slate-700">
                        <span className="sr-only"> · </span>
                        {open ? `next token ${session.next_token ?? ""}, ${session.available} left` : "not taking bookings"}
                        {open && holds > 0 && ` · ${holds} held for online requests`}
                      </span>
                    </span>
                  </label>
                );
              }
              const slots = freeSlots(session, now);
              return (
                <div key={session.id} className="space-y-2">
                  <p className="flex items-center gap-2 text-sm font-semibold tabular-nums text-slate-800">
                    <Clock aria-hidden="true" className="size-4 text-slate-500" />
                    {label}
                    {!open && <span className="font-normal text-slate-600"> · not taking bookings</span>}
                  </p>
                  {open && slots.length > 0 && (
                    <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                      {slots.map((slot) => {
                        const held = liveHolds(session, now).some((h) => h.slot_start === slot.starts_at);
                        return (
                          <label key={slot.starts_at} className={cx(CHOICE_CARD, "min-h-11 justify-center gap-1.5 px-2 text-sm font-semibold tabular-nums", held && "border-warning-line")}>
                            <input
                              type="radio"
                              name="place"
                              checked={choice?.slotStart === slot.starts_at}
                              onChange={() => {
                                setChoice({ sessionId: session.id, slotStart: slot.starts_at });
                                setOverride(undefined);
                              }}
                              className="sr-only"
                            />
                            {clock(slot.starts_at)}
                            {held && <span className="text-xs font-medium text-warning"> Held</span>}
                          </label>
                        );
                      })}
                    </div>
                  )}
                  {open && slots.length === 0 && <p className="text-sm text-slate-700">No free slots</p>}
                </div>
              );
            })}
          </fieldset>
        )}
      </Step>

      {error !== undefined && <ErrorNotice error={error} />}
      {override !== undefined && (
        <div role="alertdialog" aria-labelledby="override-title" className="space-y-3 rounded-xl border border-warning-line bg-warning-soft p-4 text-slate-900">
          <p id="override-title" className="flex items-center gap-2 font-semibold">
            <TriangleAlert aria-hidden="true" className="size-5 shrink-0 text-warning" />A patient asked for this time online
          </p>
          <p className="text-slate-800">
            The clinic is holding it until {clock(override.until)}. Book anyway only if you have agreed this with the patient: the request stays open, but it no
            longer holds the time, and this is recorded in the audit log.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setOverride(undefined)} data-autofocus>
              Choose another time
            </Button>
            <Button variant="danger" loading={saving} onClick={() => void confirm(true)}>
              Book anyway (override the patient&apos;s request)
            </Button>
          </div>
        </div>
      )}
      <div className="sticky bottom-0 -mx-5 -mb-5 space-y-2 border-t border-line bg-surface/95 px-5 py-4 backdrop-blur">
        {missing !== undefined && (
          <p id={`${ids.date}-missing`} role="alert" className={ERROR}>
            {missing}
          </p>
        )}
        {chosen !== undefined && choice !== undefined && (
          <p className="text-sm text-slate-700">
            {who ?? "Patient"} · {formatDay(chosen.on_date)}, {choice.slotStart === undefined ? `next token ${chosen.next_token ?? ""}` : clock(choice.slotStart)}
          </p>
        )}
        <Button variant="primary" size="lg" className="w-full" loading={saving} onClick={pressConfirm}>
          {saving ? "Saving…" : target.kind === "book" ? "Confirm booking" : "Confirm new time"}
        </Button>
      </div>
    </Drawer>
  );
}

export const NEED_PATIENT = "Choose the patient first.";
export const NEED_TIME = "Choose a time.";

/** A numbered part of the booking: who, then when. */
function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <span aria-hidden="true" className="grid size-6 place-items-center rounded-full bg-brand-50 text-xs font-bold text-brand-800 ring-1 ring-inset ring-brand-200">
          {n}
        </span>
        {title}
      </h3>
      {children}
    </div>
  );
}
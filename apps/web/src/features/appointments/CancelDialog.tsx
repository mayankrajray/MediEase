"use client";

import { useId, useRef, useState } from "react";

import { Dialog } from "@/components/Dialog";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { CHOICE_CARD, CHOICE_INPUT, ERROR, TextField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { CANCEL_REASON_LABELS, useAppointmentApi, type Appointment, type CancelReason } from "./api";

const REASONS = Object.keys(CANCEL_REASON_LABELS) as CancelReason[];
export const NEED_REASON = "Choose why the appointment is cancelled.";
export const NEED_NOTE = "Say why in the note.";

/**
 * Cancel with a reason (R7, D14); `OTHER` needs a note. The note is for staff only.
 *
 * M7c-P7 (M4): the cancel button stays enabled (DESIGN.md §8a, a disabled button never hides
 * why). Pressing it without a reason, or with "Other" and no note, says what is missing under
 * the field, moves focus there and sends nothing. The note counts to its 200 characters.
 */
export function CancelDialog({
  appointmentId,
  patientName,
  initialReason,
  onDone,
  onClose,
}: {
  appointmentId: string;
  patientName: string;
  /** M6a-P8: the bookings-to-move list preselects "Doctor unavailable" (decision 6A). */
  initialReason?: CancelReason;
  onDone: (appointment: Appointment, message: string) => void;
  onClose: () => void;
}) {
  const api = useAppointmentApi();
  const { endSession } = useSession();
  const [reason, setReason] = useState<CancelReason | undefined>(initialReason);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const [checked, setChecked] = useState(false);
  const noteId = useId();
  const reasonId = useId();
  const firstReason = useRef<HTMLInputElement>(null);
  const noteRef = useRef<HTMLInputElement>(null);

  const reasonError = checked && reason === undefined ? NEED_REASON : undefined;
  const noteError = checked && reason === "OTHER" && note.trim() === "" ? NEED_NOTE : undefined;

  async function submit() {
    setChecked(true);
    if (reason === undefined) {
      firstReason.current?.focus();
      return;
    }
    if (reason === "OTHER" && note.trim() === "") {
      noteRef.current?.focus();
      return;
    }
    setSaving(true);
    setError(undefined);
    try {
      const done = await api.cancel(appointmentId, reason, note);
      onDone(done, `${patientName}'s appointment cancelled.`);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog title={`Cancel ${patientName}'s appointment`} onClose={onClose}>
      <fieldset
        className="space-y-1"
        aria-invalid={reasonError !== undefined ? true : undefined}
        aria-describedby={reasonError !== undefined ? `${reasonId}-error` : undefined}
      >
        <legend className="mb-1 text-sm font-semibold text-slate-900">
          Why? <span className="font-normal text-slate-700">(required)</span>
        </legend>
        {REASONS.map((r, index) => (
          <label key={r} className={CHOICE_CARD}>
            <input
              ref={index === 0 ? firstReason : undefined}
              type="radio"
              name="reason"
              checked={reason === r}
              onChange={() => setReason(r)}
              className={CHOICE_INPUT}
            />
            {CANCEL_REASON_LABELS[r]}
          </label>
        ))}
        {reasonError !== undefined && (
          <p id={`${reasonId}-error`} className={cx(ERROR, "pt-1")}>
            {reasonError}
          </p>
        )}
      </fieldset>
      <TextField
        id={noteId}
        label={`Note ${reason === "OTHER" ? "(needed)" : "(optional)"}`}
        value={note}
        onChange={setNote}
        maxLength={200}
        counter
        hint="Not medical details: this note is not for clinical notes."
        error={noteError}
        inputRef={noteRef}
      />
      {error !== undefined && <ErrorNotice error={error} />}
      <div className="flex flex-wrap justify-end gap-2">
        <Button onClick={onClose} disabled={saving}>
          Keep appointment
        </Button>
        <Button variant="danger" loading={saving} onClick={() => void submit()}>
          Cancel appointment
        </Button>
      </div>
    </Dialog>
  );
}

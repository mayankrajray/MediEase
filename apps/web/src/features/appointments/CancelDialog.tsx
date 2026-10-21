"use client";

import { useId, useState } from "react";

import { Dialog } from "@/components/Dialog";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { CANCEL_REASON_LABELS, useAppointmentApi, type Appointment, type CancelReason } from "./api";

const REASONS = Object.keys(CANCEL_REASON_LABELS) as CancelReason[];

/** Cancel with a reason (R7, D14); `OTHER` needs a note. The note is for staff only. */
export function CancelDialog({
  appointmentId,
  patientName,
  onDone,
  onClose,
}: {
  appointmentId: string;
  patientName: string;
  onDone: (appointment: Appointment, message: string) => void;
  onClose: () => void;
}) {
  const api = useAppointmentApi();
  const { endSession } = useSession();
  const [reason, setReason] = useState<CancelReason | undefined>(undefined);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const noteId = useId();
  const needsNote = reason === "OTHER" && note.trim() === "";

  async function submit() {
    if (reason === undefined || needsNote) return;
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
      <fieldset className="space-y-1">
        <legend className="font-medium">Why?</legend>
        {REASONS.map((r) => (
          <label key={r} className="flex items-center gap-2">
            <input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} />
            {CANCEL_REASON_LABELS[r]}
          </label>
        ))}
      </fieldset>
      <div>
        <label htmlFor={noteId} className="block font-medium">
          Note {reason === "OTHER" ? "(needed)" : "(optional)"}
        </label>
        <input
          id={noteId}
          maxLength={200}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          className="min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 hover:border-slate-500 aria-[invalid=true]:border-red-700 disabled:bg-slate-100 disabled:text-slate-600"
        />
        <p className="text-sm text-slate-700">Not medical details: this note is not for clinical notes.</p>
      </div>
      {error !== undefined && <ErrorNotice error={error} />}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-400 bg-white px-4 py-2 font-medium text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500 motion-reduce:transition-none">
          Keep appointment
        </button>
        <button
          type="button"
          disabled={saving || reason === undefined || needsNote}
          onClick={() => void submit()}
          className="rounded-lg bg-red-800 px-4 py-2 font-semibold text-white disabled:bg-slate-400"
        >
          {saving ? "Cancelling…" : "Cancel appointment"}
        </button>
      </div>
    </Dialog>
  );
}

"use client";

import { useRef, useState, type FormEvent } from "react";

import { useFocusOnError } from "@/components/useFocusOnError";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { usePatientApi } from "./api";
import { draftFromPatient, patientChanges, patientFieldErrors, type Patient, type PatientDraft } from "./fields";
import { PatientFields } from "./PatientFields";

/**
 * Correct a patient's demographics in place (decision 2A; FR-PAT-01, spec R3, R7).
 * Only the fields that changed are sent, and the code is not a field at all.
 */
export function EditPatientForm({
  patient,
  today,
  onSaved,
  onCancel,
}: {
  patient: Patient;
  today: string;
  onSaved: (patient: Patient) => void;
  onCancel: () => void;
}) {
  const { endSession } = useSession();
  const api = usePatientApi();
  const [before] = useState<PatientDraft>(() => draftFromPatient(patient));
  const [draft, setDraft] = useState<PatientDraft>(before);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const container = useRef<HTMLDivElement>(null);
  useFocusOnError(error, container);

  const problems = patientFieldErrors(error);
  const alertError = error !== null && Object.keys(problems).length === 0;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const changes = patientChanges(before, draft);
    if (Object.keys(changes).length === 0) {
      onCancel();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      onSaved(await api.update(patient.id, changes));
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
      setSubmitting(false);
    }
  }

  return (
    <div ref={container} className="space-y-4">
      {alertError && <ErrorNotice error={error} />}
      <form onSubmit={(event) => void onSubmit(event)} noValidate className="space-y-4">
        <PatientFields idPrefix="edit" draft={draft} onChange={setDraft} today={today} problems={problems} />
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={submitting}
            className="rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900 disabled:cursor-not-allowed disabled:bg-slate-500"
          >
            {submitting ? "Saving…" : "Save changes"}
          </button>
          <button type="button" onClick={onCancel} className="rounded border border-slate-500 px-4 py-2 hover:bg-slate-100">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

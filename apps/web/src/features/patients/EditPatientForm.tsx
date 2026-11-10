"use client";

import { useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorSummary } from "@/components/ui/Field";
import { useFocusOnError } from "@/components/useFocusOnError";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { usePatientApi } from "./api";
import { draftFromPatient, patientChanges, patientFieldErrors, type Patient, type PatientDraft } from "./fields";
import { PatientFields, usePatientForm } from "./PatientFields";

/**
 * Correct a patient's demographics in place (decision 2A; FR-PAT-01, spec R3, R7).
 * Only the fields that changed are sent, and the code is not a field at all.
 * M7c-P7 (M5): the same inline checks as registration; "Saving…" while the call runs.
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
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const container = useRef<HTMLDivElement>(null);
  useFocusOnError(error, container);

  const apiProblems = patientFieldErrors(error);
  const alertError = error !== null && Object.keys(apiProblems).length === 0;
  const form = usePatientForm(before, today, "edit", apiProblems);
  const change = (next: PatientDraft) => {
    form.setDraft(next);
    if (error !== null) setError(null);
  };

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const changes = patientChanges(before, form.draft);
    if (Object.keys(changes).length === 0) {
      onCancel();
      return;
    }
    if (!form.check()) return;
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
      <ErrorSummary title="Check these before saving" errors={form.summary.length > 1 ? form.summary : []} />
      <form onSubmit={(event) => void onSubmit(event)} noValidate className="space-y-5">
        <PatientFields idPrefix="edit" form={{ ...form, setDraft: change }} today={today} />
        <div className="flex flex-wrap gap-2 border-t border-line pt-4">
          <Button type="submit" variant="primary" loading={submitting}>
            {submitting ? "Saving…" : "Save changes"}
          </Button>
          <Button onClick={onCancel} disabled={submitting}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}
